"""Prototype coordinate-aware extraction of tables from the Lin et al. PDF.

The paper's tables are rotated in the PDF, but Poppler's ``-layout`` mode
projects the text into stable, fixed-width columns.  This script uses the
printed header positions as column boundaries, then joins wrapped lines and
page continuations into visual record blocks.  Prototype output is deliberately
kept outside the canonical data mirrors pending biological review.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
DEFAULT_PDF = BASE / "inputs" / "Lin_paper" / "s00122-022-04101-3-1.pdf"
DEFAULT_OUTPUT = BASE / "reports" / "lin_table5_extraction_prototype.json"

TABLE_PAGES = {
    1: (6, 6),
    2: (7, 9),
    3: (12, 12),
    4: (14, 14),
    5: (16, 25),
    6: (27, 31),
    7: (33, 34),
    8: (35, 46),
    9: (47, 49),
    10: (50, 51),
    11: (53, 56),
    12: (57, 60),
    13: (63, 64),
    14: (66, 68),
    15: (69, 69),
    16: (70, 70),
    17: (71, 72),
    18: (74, 77),
    19: (78, 78),
}

SUPPORTED_TABLES = (5,)

# Header labels are used only to locate physical columns.  The names match the
# canonical dataset wherever possible.
HEADER_LABELS = (
    ("causal_agent", "Causal"),
    ("legacy_mlg", "MLG"),
    ("locus_name", "Locus/"),
    ("other_name", "Other"),
    ("markers", "Tightly"),
    ("marker_position", "Marker position"),
    ("testing_methods", "Testing methods"),
    ("population", "Population"),
    ("pve", "PVE"),
    ("candidate_genes", "Candidate"),
    ("donor_source", "Donor"),
    ("source_reference", "References"),
)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_layout(pdf_path: Path, first_page: int, last_page: int) -> list[str]:
    executable = shutil.which("pdftotext")
    if not executable:
        raise RuntimeError("Poppler pdftotext is required but was not found on PATH")
    with tempfile.TemporaryDirectory(prefix="lin-pdf-layout-") as temp_dir:
        output = Path(temp_dir) / "layout.txt"
        subprocess.run(
            [
                executable,
                "-f",
                str(first_page),
                "-l",
                str(last_page),
                "-layout",
                str(pdf_path),
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        return output.read_text(encoding="utf-8").split("\f")


def find_header(lines: list[str]) -> tuple[int, list[tuple[str, int]]]:
    for index, line in enumerate(lines):
        if "Causal" not in line or "MLG" not in line or "Locus/" not in line:
            continue
        positions = []
        for field, label in HEADER_LABELS:
            position = line.find(label)
            if position >= 0:
                positions.append((field, position))
        # Table headers consistently expose at least the first nine fields on
        # the same physical line.  Later fields may be absent in some tables.
        if len(positions) >= 9:
            return index, sorted(positions, key=lambda item: item[1])
    raise ValueError("could not locate a coordinate-bearing table header")


def split_columns(line: str, positions: list[tuple[str, int]]) -> dict[str, str]:
    cells: dict[str, str] = {}
    for index, (field, start) in enumerate(positions):
        end = positions[index + 1][1] if index + 1 < len(positions) else len(line)
        cells[field] = clean(line[start:end])
    return cells


def looks_like_header_or_footer(line: str) -> bool:
    stripped = line.strip()
    return (
        not stripped
        or stripped == "123"
        or (stripped.startswith("123") and "agent" in stripped)
        or stripped.startswith("Table ")
        or "Theoretical and Applied Genetics" in stripped
        or ("Causal" in line and "MLG" in line and "Locus/" in line)
        or stripped.startswith("agent ")
        or stripped.startswith("(Chr.)")
        or ("allele name" in stripped and "(bp)" in stripped)
    )


def starts_record(cells: dict[str, str]) -> bool:
    locus = cells.get("locus_name", "")
    other = cells.get("other_name", "")
    mlg = cells.get("legacy_mlg", "")
    evidence = any(
        cells.get(field, "")
        for field in ("markers", "marker_position", "testing_methods", "population")
    )
    if locus and locus.lower() not in {"allele", "allele name", "name"}:
        return True
    if other and evidence and other.lower() != "name":
        return True
    return bool(mlg and evidence and not mlg.startswith("(Chr"))


def append_cells(record: dict[str, list[str]], cells: dict[str, str]) -> None:
    for field, value in cells.items():
        if value:
            record.setdefault(field, []).append(value)


def parse_table_pages(pages: list[str], first_page: int) -> tuple[list[dict], list[dict]]:
    records: list[dict[str, list[str]]] = []
    page_diagnostics = []
    current: dict[str, list[str]] | None = None

    for offset, page_text in enumerate(pages):
        if not page_text.strip():
            continue
        pdf_page = first_page + offset
        lines = page_text.splitlines()
        header_index, positions = find_header(lines)
        starts_on_page = 0
        continuation_lines = 0
        for line in lines[header_index + 1 :]:
            if looks_like_header_or_footer(line):
                continue
            cells = split_columns(line, positions)
            if not any(cells.values()):
                continue
            if starts_record(cells):
                current = {
                    "pdf_page_start": [str(pdf_page)],
                    "pdf_page_end": [str(pdf_page)],
                }
                records.append(current)
                starts_on_page += 1
            elif current is None:
                # The selected ranges begin on a table's first page, so text
                # before the first structural anchor is a wrapped header.
                continue
            else:
                continuation_lines += 1
                current["pdf_page_end"] = [str(pdf_page)]
            append_cells(current, cells)
        page_diagnostics.append(
            {
                "pdf_page": pdf_page,
                "column_starts": {field: position for field, position in positions},
                "record_starts": starts_on_page,
                "continuation_lines": continuation_lines,
            }
        )

    flattened = []
    inherited_mlg = ""
    inherited_causal_agent = ""
    for number, record in enumerate(records, start=1):
        item = {field: clean(" ".join(values)) for field, values in record.items()}
        if item.get("legacy_mlg"):
            inherited_mlg = item["legacy_mlg"]
        elif inherited_mlg:
            item["inherited_legacy_mlg"] = inherited_mlg
        if item.get("causal_agent"):
            inherited_causal_agent = item["causal_agent"]
        elif inherited_causal_agent:
            item["inherited_causal_agent"] = inherited_causal_agent
        item["prototype_record_id"] = f"LIN-PROT-{number:04d}"
        flattened.append(item)
    return flattened, page_diagnostics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument(
        "--table",
        type=int,
        choices=SUPPORTED_TABLES,
        default=5,
        help="Table-specific parser currently implemented for Table 5",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    first_page, last_page = TABLE_PAGES[args.table]
    pages = extract_layout(args.pdf, first_page, last_page)
    records, page_diagnostics = parse_table_pages(pages, first_page)
    flags = Counter(record.get("prototype_flag", "") for record in records)
    output = {
        "status": "prototype_not_canonical",
        "method": "Poppler fixed-layout text parsed using per-page header coordinates",
        "source_pdf": str(args.pdf.relative_to(BASE)),
        "source_table": f"Table {args.table}",
        "pdf_page_range": [first_page, last_page],
        "record_count": len(records),
        "flag_counts": {key: value for key, value in sorted(flags.items()) if key},
        "page_diagnostics": page_diagnostics,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"table={args.table} pages={first_page}-{last_page} prototype_records={len(records)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
