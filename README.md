# Soybean QTL Browser Package

This package contains browser-ready files for a soybean resistance QTL/locus/GWAS data browser.

## Contents

- `spec.md` — handoff spec for the next agent or developer.
- `data/soybean_resistance_qtl_collation.csv` — canonical flat dataset, 1,996 rows and 40 fields.
- `data/soybean_resistance_qtl_collation.json` — same records as JSON for a static/browser app.
- `data/soybean_resistance_qtl_collation.jsonl` — newline-delimited JSON for streaming or backend ingestion.
- `data/field_dictionary.md` and `.csv` — field descriptions and basic completeness stats.
- `data/schema.json` — JSON Schema for row shape.
- `data/manifest.json` — dataset summary, recommended facets, counts, and quality notes.
- `browser/` — a working static HTML/JS/CSS browser scaffold.
- `scripts/validate_data.py` — lightweight validation script.

## Open the browser locally (no server required)

Double-click or otherwise open:

```text
browser/soybean_qtl_browser.html
```

It is a self-contained HTML file with the stylesheet, application, dataset,
manifest, and schema embedded. It can be copied elsewhere and opened directly;
no web server or network connection is required.

`browser/index.html`, `browser/app.js`, and `browser/styles.css` remain the
editable source version. To rebuild the standalone file after changing the
browser or data, run:

```bash
python scripts/build_standalone_browser.py
```

The source version can still be served for development with
`python -m http.server 8000` and opened at
`http://localhost:8000/browser/`.

## Data caveats

The source CSV was generated from long PDF and DOCX tables. The columns `row_quality_flag`, `raw_row_text`, and `source_col_01` through `source_col_14` are intentionally retained so a downstream curator can validate wrapped or sparse extraction rows. Treat rows flagged `sparse_or_continuation` or `multi_line_extraction` as needing manual review before biological interpretation.
