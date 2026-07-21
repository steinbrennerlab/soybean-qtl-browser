# Soybean Resistance QTL Browser

A self-contained browser for exploring 1,996 published soybean disease- and
pest-resistance QTL, loci, and GWAS records, with assembly-aware overlaps to
Wm82 pattern-recognition receptor (PRR) gene calls.

## Launch it

No installation or web server is required. Download or clone the repository,
then open:

[`browser/soybean_qtl_browser.html`](browser/soybean_qtl_browser.html)

The standalone file embeds the application, styles, curated dataset, schema,
manifest, and PRR overlap data. It can be copied elsewhere and opened directly
in a modern browser, including through a `file://` URL.

## What the browser provides

- Search and filtering across soybean resistance QTL, loci, and GWAS records.
- Trait, pathogen group, chromosome, study, and mapping-population context.
- PRR family filtering for subfamilies XI, XII, RLP, or all supplied PRRs.
- Exact overlap and clearly labeled 100 kb, 250 kb, 500 kb, and 1 Mb proximity
  searches.
- Source coordinates and record-level quality information for interpretation.
- A browser-ready standalone build with no runtime network dependency.

## Data included

- 1,996 curated resistance records with 40 fields.
- 157,303 Wm82 gene calls across assemblies a2, a4, and a6.
- 240 supplied a6 PRRs: 129 XI, 30 XII, and 81 RLP.
- 339 QTL records with coordinates explicitly reported on Wm82.a2.
- 45 exact QTL–PRR pairs involving 8 QTLs and 45 PRR genes.

Key files:

- `data/soybean_resistance_qtl_collation.csv` — canonical flat dataset.
- `data/soybean_resistance_qtl_collation.json` and `.jsonl` — browser and
  streaming mirrors.
- `data/prr_gene_calls.json` — PRR families and assembly-specific calls.
- `data/qtl_prr_overlaps.json` — exact and proximity relationships.
- `data/wm82_gene_calls.jsonl` — unified a2, a4, and a6 gene calls.
- `data/curation_audit.json` — deterministic source-repair audit trail.
- `data/field_dictionary.md`, `data/schema.json`, and `data/manifest.json` —
  documentation and validation metadata.
- `reports/lin_source_review.md` — review of the Lin paper and supplements.

## Coordinate policy

QTL coordinates are compared with genes only when the source explicitly labels
the QTL coordinate as Wm82.a2. Coordinates are not assumed to be equivalent
between assemblies.

The PRR input is an a6 call set. Of the 240 supplied genes, 202 retain the same
stable ID in a2, 3 map through an explicit annotation-ancestry chain, and 35
remain a6-only. The a6-only calls remain visible in the catalog but are excluded
from a2 overlap calculations.

An exact overlap has a distance of zero. Proximity results use the physical gap
between the reported QTL interval or marker and the a2 gene boundary; they are
not presented as overlaps.

## Rebuild and validate

Python 3 is the only requirement for the repository scripts.

```bash
python scripts/rebuild_curated_data.py
python scripts/build_wm82_prr_overlaps.py
python scripts/validate_data.py
python scripts/build_standalone_browser.py
```

The curation and Wm82 builders write and validate staging outputs before
replacing canonical files. The standalone builder regenerates
`browser/soybean_qtl_browser.html` from the editable files in `browser/` and
the checked-in data products.

The original Wm82 a2/a4/a6 GFF archive is approximately 569 MB and exceeds
GitHub's normal per-file limit, so `inputs/download.*.zip` is intentionally
ignored. Derived gene calls and their source manifest are checked in. To
regenerate them, place the archive under `inputs/` or pass it explicitly:

```bash
python scripts/build_wm82_prr_overlaps.py --archive path/to/wm82-gffs.zip
```

For development, the split browser sources can optionally be served with:

```bash
python -m http.server 8000
```

and opened at `http://localhost:8000/browser/`.

## Interpretation caveats

The source material contains long PDF and DOCX tables. Raw source text and
quality flags are retained so wrapped, sparse, or ambiguous rows can be audited.
Records flagged `sparse_or_continuation` or `multi_line_extraction` should be
reviewed against the cited publication before biological interpretation.

QTL–gene overlap identifies positional candidates; it does not establish that a
gene or haplotype is causal. Broad QTL intervals can contain many linked genes,
and receptor clusters can contain structural variation not represented by a
single Wm82 assembly.
