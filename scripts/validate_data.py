"""Validate data mirrors, source-aware curation rules, and package metadata."""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
from collections import Counter


BASE = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DATA = BASE / "data"

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


def load_inputs(data_dir: pathlib.Path):
    with (data_dir / "soybean_resistance_qtl_collation.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        csv_rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    json_rows = json.loads(
        (data_dir / "soybean_resistance_qtl_collation.json").read_text(encoding="utf-8")
    )
    jsonl_rows = [
        json.loads(line)
        for line in (data_dir / "soybean_resistance_qtl_collation.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    schema = json.loads((data_dir / "schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((data_dir / "curation_audit.json").read_text(encoding="utf-8"))
    return fieldnames, csv_rows, json_rows, jsonl_rows, schema, manifest, audit


def validate_prr_data(data_dir: pathlib.Path, qtl_ids: set[str]) -> list[str]:
    filenames = {
        "genes": "wm82_gene_calls.jsonl",
        "prrs": "prr_gene_calls.json",
        "overlaps": "qtl_prr_overlaps.json",
        "manifest": "wm82_gene_manifest.json",
    }
    present = {key for key, filename in filenames.items() if (data_dir / filename).exists()}
    if not present:
        # The curation rebuild validates an isolated staging directory that
        # intentionally contains only the canonical collation mirrors.
        return []
    if present != set(filenames):
        return [f"incomplete Wm82/PRR data set; found {sorted(present)}"]

    errors: list[str] = []
    manifest = json.loads((data_dir / filenames["manifest"]).read_text(encoding="utf-8"))
    prrs = json.loads((data_dir / filenames["prrs"]).read_text(encoding="utf-8"))
    overlaps = json.loads((data_dir / filenames["overlaps"]).read_text(encoding="utf-8"))

    gene_counts = Counter()
    with (data_dir / filenames["genes"]).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            gene = json.loads(line)
            gene_counts[gene["assembly"]] += 1
            chromosome = gene["chromosome"]
            if chromosome and chromosome not in {str(number) for number in range(1, 21)}:
                errors.append(f"Wm82 gene line {line_number}: invalid chromosome")
            if gene["start"] > gene["end"]:
                errors.append(f"Wm82 gene line {line_number}: start exceeds end")

    expected_gene_counts = {
        assembly: item["gene_count"]
        for assembly, item in manifest.get("assemblies", {}).items()
    }
    if dict(gene_counts) != expected_gene_counts:
        errors.append(f"Wm82 gene counts differ: {dict(gene_counts)}")
    if sum(gene_counts.values()) != manifest.get("total_gene_calls"):
        errors.append("Wm82 total_gene_calls does not match JSONL")

    prr_genes = prrs.get("genes", [])
    prr_ids = [item["gene_id_a6"] for item in prr_genes]
    family_counts = Counter(item["family"] for item in prr_genes)
    mapping_counts = Counter(item["a2_mapping_method"] for item in prr_genes)
    if len(prr_ids) != 240 or len(set(prr_ids)) != 240:
        errors.append("expected 240 unique a6 PRR genes")
    if family_counts != Counter({"RLP": 81, "XI": 129, "XII": 30}):
        errors.append(f"unexpected PRR family counts: {family_counts}")
    if mapping_counts != Counter(
        {"exact_stable_id": 202, "annotation_ancestor_chain": 3, "unmapped_to_a2": 35}
    ):
        errors.append(f"unexpected PRR a2 mapping counts: {mapping_counts}")
    if any(item["assembly_calls"]["a6"] is None for item in prr_genes):
        errors.append("every PRR must have an a6 gene call")

    overlap_rows = overlaps.get("overlaps", [])
    valid_prr_ids = set(prr_ids)
    for item in overlap_rows:
        if item["entry_id"] not in qtl_ids:
            errors.append(f"unknown QTL entry in PRR overlap: {item['entry_id']}")
        if item["gene_id_a6"] not in valid_prr_ids:
            errors.append(f"unknown PRR gene in overlap: {item['gene_id_a6']}")
        if item["distance_bp"] < 0 or item["distance_bp"] > 1_000_000:
            errors.append(f"invalid PRR distance: {item}")
        expected_relationship = "overlap" if item["distance_bp"] == 0 else "proximal"
        if item["relationship"] != expected_relationship:
            errors.append(f"invalid PRR relationship: {item}")

    if overlaps.get("parsed_qtl_count") != 339:
        errors.append("expected 339 QTL rows with explicit parseable a2 coordinates")
    exact = [item for item in overlap_rows if item["distance_bp"] == 0]
    if len(exact) != 45 or len({item["entry_id"] for item in exact}) != 8:
        errors.append("expected 45 exact PRR pairs across 8 QTL rows")

    for threshold in overlaps.get("distance_thresholds_bp", []):
        selected = [item for item in overlap_rows if item["distance_bp"] <= threshold]
        observed = overlaps["threshold_summaries"][str(threshold)]
        expected = {
            "overlap_pair_count": len(selected),
            "qtl_count": len({item["entry_id"] for item in selected}),
            "prr_gene_count": len({item["gene_id_a6"] for item in selected}),
            "family_pair_counts": dict(
                sorted(Counter(item["family"] for item in selected).items())
            ),
        }
        if observed != expected:
            errors.append(f"PRR threshold summary {threshold} does not match overlaps")
    return errors


def validate(data_dir: pathlib.Path = DEFAULT_DATA) -> list[str]:
    (
        fieldnames,
        rows,
        json_rows,
        jsonl_rows,
        schema,
        manifest,
        audit,
    ) = load_inputs(data_dir)
    errors: list[str] = []

    if not rows:
        errors.append("no rows found")
        return errors

    if rows != json_rows:
        errors.append("CSV and JSON records differ")
    if rows != jsonl_rows:
        errors.append("CSV and JSONL records differ")

    schema_fields = list(schema.get("properties", {}))
    if fieldnames != schema_fields:
        errors.append("CSV field order differs from schema property order")

    if manifest.get("record_count") != len(rows):
        errors.append("manifest record_count does not match CSV")
    if manifest.get("field_count") != len(fieldnames):
        errors.append("manifest field_count does not match CSV")

    ids = [row.get("entry_id", "") for row in rows]
    if len(ids) != len(set(ids)):
        errors.append("entry_id values are not unique")
    for row_number, entry_id in enumerate(ids, start=2):
        if not re.fullmatch(r"SOYRES-[0-9]{4}", entry_id):
            errors.append(f"row {row_number}: invalid entry_id {entry_id!r}")

    valid_chromosomes = {str(number) for number in range(1, 21)}
    for row in rows:
        chromosome = row["chromosome"]
        if chromosome and chromosome not in valid_chromosomes:
            errors.append(
                f"{row['entry_id']}: invalid chromosome value {chromosome!r}"
            )

        legacy = re.search(
            r"(?i)\bMLG\s+(D1a|D1b|A1|A2|B1|B2|C1|C2|D2|E|F|G|H|I|J|K|L|M|N|O)\b",
            row["MLG_chr"],
        )
        if legacy:
            expected = MLG_TO_CHROMOSOME[legacy.group(1).upper()]
            if chromosome != expected:
                errors.append(
                    f"{row['entry_id']}: {row['MLG_chr']!r} should map to "
                    f"chromosome {expected}, found {chromosome!r}"
                )

    expected_supplement_counts = {
        "Supplementary Table 1": 134,
        "Supplementary Table 2": 90,
        "Supplementary Table 3": 202,
    }
    observed_supplement_counts = Counter(row["source_table"] for row in rows)
    for table, expected in expected_supplement_counts.items():
        if observed_supplement_counts[table] != expected:
            errors.append(
                f"{table}: expected {expected} rows, found "
                f"{observed_supplement_counts[table]}"
            )

    # Supplementary Table 1 has a unique 10-column schema. These assertions
    # prevent regression to the prior three-column shift.
    for row in (item for item in rows if item["source_table"] == "Supplementary Table 1"):
        expected_candidate = (
            "" if row["source_col_08"] in {"", "-", "–", "—"} else row["source_col_08"]
        )
        if row["candidate_genes"] != expected_candidate:
            errors.append(f"{row['entry_id']}: candidate gene mapping regressed")
        if row["donor_source"] != row["source_col_09"]:
            errors.append(f"{row['entry_id']}: donor mapping regressed")
        if row["source_reference"] != row["source_col_10"]:
            errors.append(f"{row['entry_id']}: reference mapping regressed")

    for field, entries in manifest.get("facet_counts", {}).items():
        expected = Counter(row.get(field, "") for row in rows if row.get(field, ""))
        observed = {item["value"]: item["count"] for item in entries}
        if observed != dict(expected):
            errors.append(f"manifest facet_counts[{field!r}] does not match CSV")

    changes = audit.get("changes", [])
    if audit.get("record_count") != len(rows):
        errors.append("curation audit record_count does not match CSV")
    if audit.get("field_change_count") != len(changes):
        errors.append("curation audit field_change_count does not match changes")
    if audit.get("chromosomes_filled_from_legacy_mlg") != 130:
        errors.append("expected exactly 130 legacy MLG chromosome assignments")

    errors.extend(validate_prr_data(data_dir, set(ids)))

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=pathlib.Path,
        default=DEFAULT_DATA,
        help="Directory containing the complete data mirror set.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fieldnames, rows, *_ = load_inputs(args.data_dir)
    errors = validate(args.data_dir)
    print(f"records={len(rows)} fields={len(fieldnames)}")
    print(
        "target_groups="
        + repr(sorted({row["target_group"] for row in rows if row["target_group"]}))
    )
    if errors:
        print("VALIDATION FAILED")
        for error in errors[:50]:
            print("-", error)
        sys.exit(1)
    print("VALIDATION OK")


if __name__ == "__main__":
    main()
