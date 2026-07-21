# Build notes

Generated package from the canonical CSV and source material in
`inputs/Lin_paper/`.

- Records written: 1,996
- Fields written: 40
- Static browser scaffold: `browser/index.html`, `browser/app.js`, `browser/styles.css`
- Self-contained offline browser: `browser/soybean_qtl_browser.html`
- Machine-readable files: CSV, JSON, JSONL, schema, manifest
- Native DOCX source reconstruction: Supplementary Tables 1–3
- Transactional output replacement with pre-commit validation and rollback
- Coordinate-aware, non-canonical PDF prototype: Table 5
- Wm82 gene calls: 56,044 a2; 52,872 a4; 48,387 a6
- PRR families: 129 XI; 30 XII; 81 RLP (`inputs/soy_prr_v2.csv`)
- PRR-to-a2 mapping: 202 exact IDs; 3 annotation-ancestor mappings; 35 a6-only
- Exact reported-coordinate overlaps: 45 QTL–gene pairs across 8 QTL rows

Rebuild and validation commands:

```bash
python scripts/rebuild_curated_data.py
python scripts/build_wm82_prr_overlaps.py
python scripts/validate_data.py
python scripts/extract_lin_pdf_tables.py
python scripts/build_standalone_browser.py
```
