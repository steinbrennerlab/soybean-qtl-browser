"""Build assembly-aware Wm82 gene calls and QTL/PRR overlap data.

The input archive is streamed in place; FASTA files are not extracted. QTL
coordinates are compared only with Wm82.a2 gene coordinates because the Lin
collation labels those source coordinates as a2. Newer PRR calls are mapped to
a2 only by an exact stable ID or an explicit annotation-ancestor chain.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import shutil
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from zipfile import ZipFile


BASE = Path(__file__).resolve().parents[1]
INPUTS = BASE / "inputs"
DATA = BASE / "data"
QTL_CSV = DATA / "soybean_resistance_qtl_collation.csv"
PRR_CSV = INPUTS / "soy_prr_v2.csv"
GENE_CALLS_PATH = DATA / "wm82_gene_calls.jsonl"
PRR_CALLS_PATH = DATA / "prr_gene_calls.json"
OVERLAPS_PATH = DATA / "qtl_prr_overlaps.json"
GENE_MANIFEST_PATH = DATA / "wm82_gene_manifest.json"

ASSEMBLY_LABELS = {
    "a2": "Wm82.a2.v1",
    "a4": "Wm82.a4.v1",
    "a6": "Wm82.a6.v1",
}
FAMILIES = ("XI", "XII", "RLP")
DISTANCE_THRESHOLDS = (0, 100_000, 250_000, 500_000, 1_000_000)

RANGE_A2_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*[–—-]\s*"
    r"(\d[\d,]*(?:\.\d+)?)\s*(Mb)?\s*a2\b",
    re.IGNORECASE,
)
POINT_A2_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(Mb)?\s*a2\b", re.IGNORECASE
)


@dataclass(frozen=True)
class GeneCall:
    assembly: str
    assembly_label: str
    seqid: str
    chromosome: str
    start: int
    end: int
    strand: str
    gene_id: str
    model_id: str
    ancestor_identifier: str
    source: str


def find_archive() -> Path:
    candidates = []
    for path in INPUTS.glob("*.zip"):
        with ZipFile(path) as archive:
            if len([name for name in archive.namelist() if name.endswith(".gene.gff3.gz")]) >= 3:
                candidates.append(path)
    if len(candidates) != 1:
        raise ValueError(f"Expected one Wm82 annotation archive; found {candidates}")
    return candidates[0]


def parse_attributes(value: str) -> dict[str, str]:
    return {
        key: item
        for part in value.split(";")
        if "=" in part
        for key, item in [part.split("=", 1)]
    }


def chromosome_from_seqid(seqid: str) -> str:
    match = re.fullmatch(r"(?:Chr|Gm)(\d{1,2})", seqid)
    if not match:
        return ""
    chromosome = int(match.group(1))
    return str(chromosome) if 1 <= chromosome <= 20 else ""


def assembly_from_filename(filename: str) -> str:
    for assembly in ASSEMBLY_LABELS:
        if f".{assembly}." in filename:
            return assembly
    raise ValueError(f"Could not determine assembly from {filename}")


def read_gene_calls(archive_path: Path) -> tuple[dict[str, list[GeneCall]], dict[str, str]]:
    calls: dict[str, list[GeneCall]] = {}
    sources: dict[str, str] = {}
    with ZipFile(archive_path) as archive:
        names = sorted(name for name in archive.namelist() if name.endswith(".gene.gff3.gz"))
        for filename in names:
            assembly = assembly_from_filename(filename)
            assembly_calls = []
            with (
                archive.open(filename) as compressed,
                gzip.GzipFile(fileobj=compressed) as uncompressed,
                io.TextIOWrapper(uncompressed, encoding="utf-8") as handle,
            ):
                for line in handle:
                    if line.startswith("#"):
                        continue
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) != 9 or parts[2] != "gene":
                        continue
                    attributes = parse_attributes(parts[8])
                    assembly_calls.append(
                        GeneCall(
                            assembly=assembly,
                            assembly_label=ASSEMBLY_LABELS[assembly],
                            seqid=parts[0],
                            chromosome=chromosome_from_seqid(parts[0]),
                            start=int(parts[3]),
                            end=int(parts[4]),
                            strand=parts[6],
                            gene_id=attributes.get("Name", ""),
                            model_id=attributes.get("ID", ""),
                            ancestor_identifier=attributes.get("ancestorIdentifier", ""),
                            source=parts[1],
                        )
                    )
            calls[assembly] = assembly_calls
            sources[assembly] = filename
    if set(calls) != set(ASSEMBLY_LABELS):
        raise ValueError(f"Expected a2, a4, and a6 GFFs; found {sorted(calls)}")
    return calls, sources


def read_prr_calls() -> dict[str, str]:
    calls: dict[str, str] = {}
    with PRR_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.reader(handle), start=1):
            if not row:
                continue
            if len(row) != 2:
                raise ValueError(f"{PRR_CSV.name} row {row_number} does not have two columns")
            gene_id, family = (item.strip() for item in row)
            family = family.upper()
            if family not in FAMILIES:
                raise ValueError(f"Unknown PRR family {family!r} on row {row_number}")
            if gene_id in calls and calls[gene_id] != family:
                raise ValueError(f"Conflicting families for {gene_id}")
            calls[gene_id] = family
    return calls


def index_calls(calls: list[GeneCall]) -> tuple[dict[str, GeneCall], dict[str, GeneCall]]:
    by_name = {call.gene_id: call for call in calls}
    by_model = {call.model_id: call for call in calls}
    if len(by_name) != len(calls) or len(by_model) != len(calls):
        raise ValueError("Gene IDs and model IDs must be unique within each assembly")
    return by_name, by_model


def build_prr_catalog(
    prr_families: dict[str, str], calls: dict[str, list[GeneCall]]
) -> list[dict]:
    indexes = {assembly: index_calls(items) for assembly, items in calls.items()}
    catalog = []
    for gene_id_a6, family in sorted(prr_families.items()):
        direct_calls = {
            assembly: indexes[assembly][0].get(gene_id_a6)
            for assembly in ASSEMBLY_LABELS
        }
        a6_call = direct_calls["a6"]
        if a6_call is None:
            raise ValueError(f"a6 PRR call not found in a6 GFF: {gene_id_a6}")

        mapped_a2 = direct_calls["a2"]
        mapping_method = "exact_stable_id" if mapped_a2 else ""
        a4_ancestor_call = None
        if mapped_a2 is None:
            a4_ancestor_call = direct_calls["a4"] or indexes["a4"][1].get(
                a6_call.ancestor_identifier
            )
            if a4_ancestor_call:
                mapped_a2 = indexes["a2"][1].get(
                    a4_ancestor_call.ancestor_identifier
                ) or indexes["a2"][0].get(a4_ancestor_call.gene_id)
                if mapped_a2:
                    mapping_method = "annotation_ancestor_chain"

        catalog.append(
            {
                "gene_id_a6": gene_id_a6,
                "family": family,
                "assembly_calls": {
                    assembly: asdict(call) if call else None
                    for assembly, call in direct_calls.items()
                },
                "a4_ancestor_call": asdict(a4_ancestor_call) if a4_ancestor_call else None,
                "mapped_a2_call": asdict(mapped_a2) if mapped_a2 else None,
                "a2_mapping_method": mapping_method or "unmapped_to_a2",
            }
        )
    return catalog


def coordinate_value(value: str, unit: str | None) -> int:
    number = float(value.replace(",", ""))
    return round(number * 1_000_000) if unit else round(number)


def parse_a2_coordinate(value: str) -> tuple[int, int, str] | None:
    range_match = RANGE_A2_RE.search(value)
    if range_match:
        start = coordinate_value(range_match.group(1), range_match.group(3))
        end = coordinate_value(range_match.group(2), range_match.group(3))
        return min(start, end), max(start, end), "reported_interval"
    for point_match in POINT_A2_RE.finditer(value):
        point = coordinate_value(point_match.group(1), point_match.group(2))
        if point >= 1_000:
            return point, point, "reported_marker"
    return None


def interval_distance(qtl_start: int, qtl_end: int, gene_start: int, gene_end: int) -> int:
    return max(qtl_start - gene_end, gene_start - qtl_end, 0)


def build_overlaps(prr_catalog: list[dict]) -> tuple[list[dict], list[dict]]:
    mapped_prrs = [item for item in prr_catalog if item["mapped_a2_call"]]
    parsed_qtls = []
    overlaps = []
    with QTL_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            parsed = parse_a2_coordinate(row["marker_position"])
            chromosome = row["chromosome"].strip()
            if parsed is None or not chromosome:
                continue
            qtl_start, qtl_end, coordinate_type = parsed
            parsed_qtls.append(
                {
                    "entry_id": row["entry_id"],
                    "chromosome": chromosome,
                    "start": qtl_start,
                    "end": qtl_end,
                    "coordinate_type": coordinate_type,
                    "source_coordinate": row["marker_position"],
                }
            )
            for prr in mapped_prrs:
                gene = prr["mapped_a2_call"]
                if gene["chromosome"] != chromosome:
                    continue
                distance = interval_distance(qtl_start, qtl_end, gene["start"], gene["end"])
                if distance > max(DISTANCE_THRESHOLDS):
                    continue
                overlaps.append(
                    {
                        "entry_id": row["entry_id"],
                        "family": prr["family"],
                        "gene_id_a6": prr["gene_id_a6"],
                        "mapped_a2_gene_id": gene["gene_id"],
                        "a2_mapping_method": prr["a2_mapping_method"],
                        "chromosome": chromosome,
                        "qtl_start": qtl_start,
                        "qtl_end": qtl_end,
                        "qtl_coordinate_type": coordinate_type,
                        "source_coordinate": row["marker_position"],
                        "gene_start": gene["start"],
                        "gene_end": gene["end"],
                        "distance_bp": distance,
                        "relationship": "overlap" if distance == 0 else "proximal",
                    }
                )
    overlaps.sort(key=lambda item: (item["entry_id"], item["distance_bp"], item["gene_id_a6"]))
    return parsed_qtls, overlaps


def threshold_summary(overlaps: list[dict]) -> dict[str, dict]:
    summaries = {}
    for threshold in DISTANCE_THRESHOLDS:
        selected = [item for item in overlaps if item["distance_bp"] <= threshold]
        summaries[str(threshold)] = {
            "overlap_pair_count": len(selected),
            "qtl_count": len({item["entry_id"] for item in selected}),
            "prr_gene_count": len({item["gene_id_a6"] for item in selected}),
            "family_pair_counts": dict(sorted(Counter(item["family"] for item in selected).items())),
        }
    return summaries


def json_text(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def replace_with_retry(source: Path, target: Path, attempts: int = 8) -> None:
    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt + 1 == attempts:
                raise
            time.sleep(0.25 * (attempt + 1))


def validate_staged(staging: Path, expected_counts: dict[str, int]) -> None:
    gene_counts = Counter()
    with (staging / GENE_CALLS_PATH.name).open(encoding="utf-8") as handle:
        for line in handle:
            gene = json.loads(line)
            gene_counts[gene["assembly"]] += 1
            if gene["chromosome"] and not 1 <= int(gene["chromosome"]) <= 20:
                raise ValueError(f"Invalid gene chromosome: {gene}")
            if gene["start"] > gene["end"]:
                raise ValueError(f"Invalid gene coordinates: {gene}")
    if dict(gene_counts) != expected_counts:
        raise ValueError(f"Staged gene counts differ: {gene_counts} != {expected_counts}")

    prr_payload = json.loads((staging / PRR_CALLS_PATH.name).read_text(encoding="utf-8"))
    if len(prr_payload["genes"]) != 240:
        raise ValueError("Expected 240 PRR genes")
    if Counter(item["family"] for item in prr_payload["genes"]) != Counter(
        {"RLP": 81, "XI": 129, "XII": 30}
    ):
        raise ValueError("Unexpected PRR family counts")

    overlap_payload = json.loads((staging / OVERLAPS_PATH.name).read_text(encoding="utf-8"))
    gene_ids = {item["gene_id_a6"] for item in prr_payload["genes"]}
    for item in overlap_payload["overlaps"]:
        if item["gene_id_a6"] not in gene_ids or item["distance_bp"] < 0:
            raise ValueError(f"Invalid overlap: {item}")


def write_transactionally(outputs: dict[Path, str], expected_counts: dict[str, int]) -> None:
    staging = Path(tempfile.mkdtemp(prefix=".wm82-staging-", dir=DATA))
    backups = staging / "backups"
    backups.mkdir()
    staged = {}
    for target, content in outputs.items():
        path = staging / target.name
        path.write_text(content, encoding="utf-8", newline="\n")
        staged[target] = path
    validate_staged(staging, expected_counts)

    committed = []
    try:
        for target in outputs:
            if target.exists():
                shutil.copy2(target, backups / target.name)
        for target, source in staged.items():
            replace_with_retry(source, target)
            committed.append(target)
    except Exception:
        for target in reversed(committed):
            backup = backups / target.name
            if backup.exists():
                replace_with_retry(backup, target)
        raise
    try:
        shutil.rmtree(staging)
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=None)
    args = parser.parse_args()
    archive_path = args.archive or find_archive()

    calls, sources = read_gene_calls(archive_path)
    prr_families = read_prr_calls()
    prr_catalog = build_prr_catalog(prr_families, calls)
    parsed_qtls, overlaps = build_overlaps(prr_catalog)
    gene_counts = {assembly: len(calls[assembly]) for assembly in sorted(calls)}

    gene_lines = "".join(
        json.dumps(asdict(call), ensure_ascii=False, separators=(",", ":")) + "\n"
        for assembly in sorted(calls)
        for call in calls[assembly]
    )
    family_counts = dict(sorted(Counter(prr_families.values()).items()))
    mapping_counts = dict(
        sorted(Counter(item["a2_mapping_method"] for item in prr_catalog).items())
    )
    threshold_counts = threshold_summary(overlaps)
    prr_payload = {
        "source": "inputs/soy_prr_v2.csv",
        "primary_assembly": "Wm82.a6.v1",
        "family_counts": family_counts,
        "a2_mapping_counts": mapping_counts,
        "genes": prr_catalog,
    }
    overlap_payload = {
        "coordinate_assembly": "Wm82.a2.v1",
        "coordinate_rule": (
            "Only marker_position values explicitly labeled a2 are parsed. "
            "Exact overlap is distance 0; proximity distances are interval-to-gene gaps."
        ),
        "distance_thresholds_bp": list(DISTANCE_THRESHOLDS),
        "parsed_qtl_count": len(parsed_qtls),
        "parsed_qtls": parsed_qtls,
        "threshold_summaries": threshold_counts,
        "overlaps": overlaps,
    }
    manifest = {
        "source_archive": str(archive_path.relative_to(BASE)),
        "assemblies": {
            assembly: {
                "label": ASSEMBLY_LABELS[assembly],
                "gene_count": gene_counts[assembly],
                "gff_member": sources[assembly],
            }
            for assembly in sorted(calls)
        },
        "total_gene_calls": sum(gene_counts.values()),
        "prr_gene_count": len(prr_catalog),
        "prr_family_counts": family_counts,
        "prr_a2_mapping_counts": mapping_counts,
        "qtl_a2_coordinate_count": len(parsed_qtls),
        "qtl_coordinate_type_counts": dict(
            sorted(Counter(item["coordinate_type"] for item in parsed_qtls).items())
        ),
        "overlap_threshold_summaries": threshold_counts,
    }
    outputs = {
        GENE_CALLS_PATH: gene_lines,
        PRR_CALLS_PATH: json_text(prr_payload),
        OVERLAPS_PATH: json_text(overlap_payload),
        GENE_MANIFEST_PATH: json_text(manifest),
    }
    write_transactionally(outputs, gene_counts)

    print(f"gene_calls={sum(gene_counts.values())} assemblies={gene_counts}")
    print(f"prr_genes={len(prr_catalog)} families={family_counts} a2_mapping={mapping_counts}")
    print(f"parsed_a2_qtls={len(parsed_qtls)} exact_pairs={threshold_counts['0']['overlap_pair_count']}")


if __name__ == "__main__":
    main()
