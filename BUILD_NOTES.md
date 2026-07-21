# Build notes

Generated package from `/mnt/data/soybean_resistance_qtl_collation.csv`.

- Records written: 1,996
- Fields written: 40
- Static browser scaffold: `browser/index.html`, `browser/app.js`, `browser/styles.css`
- Self-contained offline browser: `browser/soybean_qtl_browser.html`
- Machine-readable files: CSV, JSON, JSONL, schema, manifest

Validation command:

```bash
python scripts/validate_data.py
python scripts/build_standalone_browser.py
```
