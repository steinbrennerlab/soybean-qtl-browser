"""Rebuild curated data mirrors from the canonical CSV and original sources.

The source PDF tables still require record reconstruction, so this first pass
only applies transformations that can be validated exactly:

* re-extract the three native DOCX supplementary tables, honoring vertical
  merges;
* map each supplement with its own column schema;
* repair the shifted candidate/donor/reference fields in Supplementary Table 1;
* fill blank chromosome values from unambiguous legacy MLG labels; and
* regenerate all data mirrors, metadata, and a field-level curation audit.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


BASE = Path(__file__).resolve().parents[1]
DATA_DIR = BASE / "data"
INPUT_DIR = BASE / "inputs" / "Lin_paper"

CSV_PATH = DATA_DIR / "soybean_resistance_qtl_collation.csv"
JSON_PATH = DATA_DIR / "soybean_resistance_qtl_collation.json"
JSONL_PATH = DATA_DIR / "soybean_resistance_qtl_collation.jsonl"
SCHEMA_PATH = DATA_DIR / "schema.json"
MANIFEST_PATH = DATA_DIR / "manifest.json"
DICTIONARY_CSV_PATH = DATA_DIR / "field_dictionary.csv"
DICTIONARY_MD_PATH = DATA_DIR / "field_dictionary.md"
AUDIT_PATH = DATA_DIR / "curation_audit.json"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

MISSING_TOKENS = {"", "-", "–", "—"}

MLG_TO_CHROMOSOME = {
    "D1A": "1",
    "D1B": "2",
    "N": "3",
    "C1": "4",
    "A1": "5",
    "C2": "6",
    "M": "7",
    "A2": "8",
    "K": "9",
    "O": "10",
    "B1": "11",
    "H": "12",
    "F": "13",
    "B2": "14",
    "E": "15",
    "J": "16",
    "D2": "17",
    "G": "18",
    "L": "19",
    "I": "20",
}


@dataclass(frozen=True)
class SupplementConfig:
    source_table: str
    filename: str
    column_count: int
    mapping: dict[str, int]


SUPPLEMENTS = (
    SupplementConfig(
        source_table="Supplementary Table 1",
        filename="122_2022_4101_MOESM2_ESM.docx",
        column_count=10,
        mapping={
            "MLG_chr": 1,
            "locus_or_allele": 2,
            "linked_flanking_markers": 3,
            "marker_position": 4,
            "resistance_spectrum_or_testing_method": 5,
            "population_type_size": 6,
            "PVE_or_effect": 7,
            "candidate_genes": 8,
            "donor_source": 9,
            "source_reference": 10,
        },
    ),
    SupplementConfig(
        source_table="Supplementary Table 2",
        filename="122_2022_4101_MOESM3_ESM.docx",
        column_count=10,
        mapping={
            "causal_agent_or_species": 1,
            "MLG_chr": 2,
            "locus_or_allele": 3,
            "linked_flanking_markers": 4,
            "marker_position": 5,
            "resistance_spectrum_or_testing_method": 6,
            "population_type_size": 7,
            "PVE_or_effect": 8,
            "donor_source": 9,
            "source_reference": 10,
        },
    ),
    SupplementConfig(
        source_table="Supplementary Table 3",
        filename="122_2022_4101_MOESM1_ESM.docx",
        column_count=9,
        mapping={
            "MLG_chr": 1,
            "locus_or_allele": 2,
            "linked_flanking_markers": 3,
            "marker_position": 4,
            "resistance_spectrum_or_testing_method": 5,
            "population_type_size": 6,
            "PVE_or_effect": 7,
            "donor_source": 8,
            "source_reference": 9,
        },
    ),
)


def clean_text(value: str | None) -> str:
    """Normalize invisible Word whitespace without changing punctuation."""
    if not value:
        return ""
    return re.sub(r"[\t\r\n ]+", " ", value.replace("\u00a0", " ")).strip()


def semantic_value(value: str) -> str:
    """Convert source placeholders to an empty value in semantic-only fields."""
    value = clean_text(value)
    return "" if value in MISSING_TOKENS else value


def cell_text(cell: ET.Element) -> str:
    return clean_text("".join(node.text or "" for node in cell.iter(f"{W}t")))


def extract_docx_table(path: Path, expected_columns: int) -> list[list[str]]:
    """Extract the first Word table and forward-fill vertically merged cells."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))

    table = root.find(f".//{W}tbl")
    if table is None:
        raise ValueError(f"No table found in {path}")

    source_rows = table.findall(f"{W}tr")
    if len(source_rows) < 2:
        raise ValueError(f"No data rows found in {path}")

    merged_values: dict[int, str] = {}
    rows: list[list[str]] = []

    # The first table row contains headers.
    for source_row_number, row_element in enumerate(source_rows[1:], start=2):
        values: list[str] = []
        for column_index, cell in enumerate(row_element.findall(f"{W}tc")):
            value = cell_text(cell)
            cell_properties = cell.find(f"{W}tcPr")
            vertical_merge = (
                cell_properties.find(f"{W}vMerge")
                if cell_properties is not None
                else None
            )

            if vertical_merge is not None:
                merge_type = vertical_merge.get(f"{W}val", "continue")
                if merge_type == "restart":
                    merged_values[column_index] = value
                elif column_index in merged_values:
                    value = merged_values[column_index]
            else:
                merged_values.pop(column_index, None)

            values.append(value)

        # Supplementary Table 2 contains one intentional blank separator row.
        if not any(values):
            continue

        if len(values) != expected_columns:
            raise ValueError(
                f"{path.name} row {source_row_number}: expected "
                f"{expected_columns} cells, found {len(values)}"
            )
        rows.append(values)

    return rows


def read_csv_rows() -> tuple[list[str], list[dict[str, str]]]:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def read_git_csv_rows(git_ref: str) -> list[dict[str, str]]:
    """Read a historical canonical CSV for one-time audit reconstruction."""
    result = subprocess.run(
        ["git", "show", f"{git_ref}:data/{CSV_PATH.name}"],
        cwd=BASE,
        check=True,
        capture_output=True,
    )
    text = result.stdout.decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def read_dictionary_metadata() -> dict[str, dict[str, str]]:
    with DICTIONARY_CSV_PATH.open(encoding="utf-8", newline="") as handle:
        return {row["field"]: row for row in csv.DictReader(handle)}


def chromosome_from_mlg(value: str) -> tuple[str, str] | None:
    """Return chromosome and method for explicit Chr text or legacy MLG code."""
    explicit = re.search(r"(?i)\bChr\.?\s*\)?\s*([0-9]{1,2})\b", value)
    if explicit:
        chromosome = str(int(explicit.group(1)))
        if 1 <= int(chromosome) <= 20:
            return chromosome, "source_explicit_chromosome"

    legacy = re.search(
        r"(?i)\bMLG\s+(D1a|D1b|A1|A2|B1|B2|C1|C2|D2|E|F|G|H|I|J|K|L|M|N|O)\b",
        value,
    )
    if legacy:
        code = legacy.group(1).upper()
        return MLG_TO_CHROMOSOME[code], "legacy_mlg_crosswalk"

    return None


def record_change(
    audit_changes: list[dict[str, str]],
    row: dict[str, str],
    field: str,
    new_value: str,
    reason: str,
) -> None:
    old_value = row.get(field, "")
    if old_value == new_value:
        return
    audit_changes.append(
        {
            "entry_id": row["entry_id"],
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason,
        }
    )
    row[field] = new_value


def apply_supplements(
    rows: list[dict[str, str]], audit_changes: list[dict[str, str]]
) -> dict[str, int]:
    summaries: dict[str, int] = {}

    for config in SUPPLEMENTS:
        source_rows = extract_docx_table(
            INPUT_DIR / config.filename, config.column_count
        )
        target_rows = [row for row in rows if row["source_table"] == config.source_table]
        if len(source_rows) != len(target_rows):
            raise ValueError(
                f"{config.source_table}: source has {len(source_rows)} rows, "
                f"CSV has {len(target_rows)}"
            )

        for target, source_values in zip(target_rows, source_rows, strict=True):
            reason = f"native_docx_reconstruction:{config.source_table}"

            for column_index in range(1, 15):
                field = f"source_col_{column_index:02d}"
                value = (
                    source_values[column_index - 1]
                    if column_index <= config.column_count
                    else ""
                )
                record_change(audit_changes, target, field, value, reason)

            raw_row_text = " | ".join(source_values)
            record_change(audit_changes, target, "raw_row_text", raw_row_text, reason)

            for field, one_based_index in config.mapping.items():
                value = source_values[one_based_index - 1]
                if field == "candidate_genes":
                    value = semantic_value(value)
                record_change(audit_changes, target, field, value, reason)

            parsed = chromosome_from_mlg(target["MLG_chr"])
            if parsed:
                chromosome, method = parsed
                if target["chromosome"] and target["chromosome"] != chromosome:
                    raise ValueError(
                        f"{target['entry_id']}: chromosome {target['chromosome']} "
                        f"conflicts with {target['MLG_chr']} -> {chromosome}"
                    )
                record_change(
                    audit_changes,
                    target,
                    "chromosome",
                    chromosome,
                    f"{reason}:{method}",
                )

        summaries[config.source_table] = len(source_rows)

    return summaries


def normalize_chromosomes(
    rows: list[dict[str, str]], audit_changes: list[dict[str, str]]
) -> int:
    filled = 0
    for row in rows:
        parsed = chromosome_from_mlg(row.get("MLG_chr", ""))
        if not parsed:
            continue
        chromosome, method = parsed
        existing = clean_text(row.get("chromosome", ""))
        if existing and existing != chromosome:
            raise ValueError(
                f"{row['entry_id']}: chromosome {existing} conflicts with "
                f"{row['MLG_chr']} -> {chromosome}"
            )
        if not existing:
            record_change(
                audit_changes,
                row,
                "chromosome",
                chromosome,
                method,
            )
            filled += 1
    return filled


def diff_rows(
    baseline_rows: list[dict[str, str]],
    curated_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Create a deterministic field-level audit against a checkpoint CSV."""
    baseline_by_id = {row["entry_id"]: row for row in baseline_rows}
    changes: list[dict[str, str]] = []
    for row in curated_rows:
        baseline = baseline_by_id.get(row["entry_id"])
        if baseline is None:
            continue
        for field, new_value in row.items():
            old_value = baseline.get(field, "")
            if old_value == new_value:
                continue
            if field == "chromosome" and not old_value:
                reason = "legacy_mlg_crosswalk"
            elif row["source_table"].startswith("Supplementary Table"):
                reason = f"native_docx_reconstruction:{row['source_table']}"
            else:
                reason = "curated_rebuild"
            changes.append(
                {
                    "entry_id": row["entry_id"],
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "reason": reason,
                }
            )
    return changes


def replace_with_retry(source: Path, target: Path) -> None:
    """Atomically replace a file, tolerating short-lived Windows file locks."""
    for attempt in range(10):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.1 * (attempt + 1))


def write_outputs_transactionally(outputs: dict[Path, str]) -> None:
    """Validate a complete staging set, then commit it with rollback support."""
    staging_dir = Path(tempfile.mkdtemp(prefix=".curation-staging-", dir=DATA_DIR))
    backup_dir = staging_dir / "backups"
    backup_dir.mkdir()

    staged_files: dict[Path, Path] = {}
    for target, content in outputs.items():
        staged = staging_dir / target.name
        staged.write_text(content, encoding="utf-8", newline="\n")
        staged_files[target] = staged

    validation = subprocess.run(
        [
            sys.executable,
            str(BASE / "scripts" / "validate_data.py"),
            "--data-dir",
            str(staging_dir),
        ],
        cwd=BASE,
        text=True,
        capture_output=True,
    )
    if validation.returncode:
        raise RuntimeError(
            "Staged outputs failed validation and were not committed.\n"
            + validation.stdout
            + validation.stderr
            + f"\nStaging retained at {staging_dir}"
        )

    backups: dict[Path, Path] = {}
    for target in outputs:
        backup = backup_dir / target.name
        shutil.copy2(target, backup)
        backups[target] = backup

    committed: list[Path] = []
    try:
        for target, staged in staged_files.items():
            replace_with_retry(staged, target)
            committed.append(target)
    except Exception as commit_error:
        rollback_errors: list[str] = []
        for target in reversed(committed):
            try:
                replace_with_retry(backups[target], target)
            except Exception as rollback_error:  # pragma: no cover - emergency path
                rollback_errors.append(f"{target}: {rollback_error}")
        detail = (
            "\nRollback errors: " + "; ".join(rollback_errors)
            if rollback_errors
            else ""
        )
        raise RuntimeError(
            f"Commit failed; prior files were rolled back. Staging retained at "
            f"{staging_dir}.{detail}"
        ) from commit_error

    try:
        shutil.rmtree(staging_dir)
    except OSError:
        # Cleanup is non-critical and the directory is gitignored.
        pass


def csv_text(fieldnames: list[str], rows: Iterable[dict[str, str]]) -> str:
    with tempfile.SpooledTemporaryFile(
        mode="w+", encoding="utf-8", newline="", max_size=8_000_000
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.seek(0)
        return handle.read()


def update_schema() -> dict:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema["properties"]["MLG_chr"]["description"] = (
        "Original molecular linkage group and chromosome text as reported or parsed."
    )
    schema["properties"]["chromosome"]["description"] = (
        "Parsed chromosome number from 1 through 20; values may be taken directly "
        "from the source or deterministically assigned from an explicit legacy MLG."
    )
    return schema


def example_values(rows: list[dict[str, str]], field: str, limit: int = 5) -> list[str]:
    counts = Counter(
        clean_text(row.get(field, "")) for row in rows if clean_text(row.get(field, ""))
    )
    return [value for value, _ in counts.most_common(limit)]


def build_dictionary(
    fieldnames: list[str], rows: list[dict[str, str]], schema: dict
) -> tuple[str, str]:
    old_metadata = read_dictionary_metadata()
    dictionary_rows: list[dict[str, str | int]] = []

    for field in fieldnames:
        values = [row.get(field, "") for row in rows if row.get(field, "")]
        old = old_metadata.get(field, {})
        description = schema["properties"].get(field, {}).get(
            "description", old.get("description", "")
        )
        dictionary_rows.append(
            {
                "field": field,
                "type": old.get("type", "string"),
                "description": description,
                "nonempty_count": len(values),
                "unique_nonempty_count": len(set(values)),
                "example_values": " | ".join(example_values(rows, field)),
            }
        )

    csv_output = csv_text(list(dictionary_rows[0]), dictionary_rows)

    md_lines = [
        "# Field dictionary",
        "",
        "This file describes the browser-ready data fields in "
        "`data/soybean_resistance_qtl_collation.csv` and `.json`.",
        "",
        "| Field | Type | Description | Non-empty | Unique | Example values |",
        "|---|---|---|---:|---:|---|",
    ]
    for item in dictionary_rows:
        escaped = str(item["example_values"]).replace("|", "\\|")
        md_lines.append(
            f"| `{item['field']}` | {item['type']} | {item['description']} | "
            f"{item['nonempty_count']} | {item['unique_nonempty_count']} | {escaped} |"
        )
    md_output = "\n".join(md_lines) + "\n"
    return csv_output, md_output


def build_manifest(rows: list[dict[str, str]], fieldnames: list[str]) -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["record_count"] = len(rows)
    manifest["field_count"] = len(fieldnames)
    manifest["curation_version"] = "source-reconstruction-v1"
    manifest["curation_audit"] = "data/curation_audit.json"
    manifest["curation_notes"] = [
        "All three Lin et al. supplementary tables were reconstructed from native DOCX cells with vertical merges resolved.",
        "Supplementary Table 1 candidate gene, donor, and reference fields were remapped to their source columns.",
        "Blank chromosome values were filled only when an explicit legacy MLG crosswalk was unambiguous.",
        "Main-paper PDF table records remain source-derived and require conceptual row reconstruction.",
    ]

    facet_fields = list(manifest.get("facet_counts", {}))
    manifest["facet_counts"] = {
        field: [
            {"value": value, "count": count}
            for value, count in Counter(
                row.get(field, "") for row in rows if row.get(field, "")
            ).most_common()
        ]
        for field in facet_fields
    }
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit-baseline-git-ref",
        help=(
            "Reconstruct the field-level audit against the canonical CSV at "
            "this git ref. Intended for checkpointed migrations."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fieldnames, rows = read_csv_rows()
    if len(rows) != 1996 or len(fieldnames) != 40:
        raise ValueError(
            f"Unexpected canonical shape: {len(rows)} rows x {len(fieldnames)} fields"
        )

    previous_audit = (
        json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        if AUDIT_PATH.exists()
        else {}
    )
    previous_changes = list(previous_audit.get("changes", []))

    audit_changes: list[dict[str, str]] = []
    supplement_counts = apply_supplements(rows, audit_changes)
    chromosomes_filled = normalize_chromosomes(rows, audit_changes)

    if args.audit_baseline_git_ref:
        audit_changes = diff_rows(
            read_git_csv_rows(args.audit_baseline_git_ref), rows
        )
        chromosomes_filled = sum(
            change["field"] == "chromosome"
            and change["old_value"] == ""
            and change["reason"] == "legacy_mlg_crosswalk"
            for change in audit_changes
        )
    elif previous_changes:
        existing_keys = {
            (
                change["entry_id"],
                change["field"],
                change["old_value"],
                change["new_value"],
                change["reason"],
            )
            for change in previous_changes
        }
        new_changes = [
            change
            for change in audit_changes
            if (
                change["entry_id"],
                change["field"],
                change["old_value"],
                change["new_value"],
                change["reason"],
            )
            not in existing_keys
        ]
        audit_changes = previous_changes + new_changes
        chromosomes_filled += int(
            previous_audit.get("chromosomes_filled_from_legacy_mlg", 0)
        )

    schema = update_schema()
    manifest = build_manifest(rows, fieldnames)
    dictionary_csv, dictionary_md = build_dictionary(fieldnames, rows, schema)

    audit = {
        "curation_version": "source-reconstruction-v1",
        "source": "Lin et al. 2022 paper supplements",
        "record_count": len(rows),
        "supplement_rows_reconstructed": supplement_counts,
        "chromosomes_filled_from_legacy_mlg": chromosomes_filled,
        "field_change_count": len(audit_changes),
        "changes": audit_changes,
    }

    outputs = {
        CSV_PATH: csv_text(fieldnames, rows),
        JSON_PATH: json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        JSONL_PATH: "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in rows
        ),
        SCHEMA_PATH: json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        MANIFEST_PATH: json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        DICTIONARY_CSV_PATH: dictionary_csv,
        DICTIONARY_MD_PATH: dictionary_md,
        AUDIT_PATH: json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
    }
    write_outputs_transactionally(outputs)

    print(f"records={len(rows)} fields={len(fieldnames)}")
    for table, count in supplement_counts.items():
        print(f"{table}: reconstructed_rows={count}")
    print(f"chromosomes_filled_from_legacy_mlg={chromosomes_filled}")
    print(f"field_changes={len(audit_changes)}")


if __name__ == "__main__":
    main()
