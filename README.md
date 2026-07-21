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

## How the dataset was created from Lin et al.

The principal source is [Lin et al. (2022), *Breeding for disease resistance
in soybean: a global perspective*](https://doi.org/10.1007/s00122-022-04101-3).
The review describes more than 800 resistance loci or alleles for 28 soybean
diseases and consolidates their markers, mapping populations, effects, donor
sources, candidate genes, and references across its main and supplementary
tables.

The repository retains the source PDF and three supplementary Word documents
under `inputs/Lin_paper/`. Lin-derived material accounts for 1,976 of the 1,996
browser records:

| Source category | Records | How it was handled |
|---|---:|---|
| Review main tables | 1,512 | Extracted from the paper's vector PDF and retained with raw text and quality flags |
| Review supplementary tables | 426 | Reconstructed directly from native DOCX table cells |
| Review disease-scope rows | 38 | Retained as overview/context records rather than mapped loci |
| Additional herbivore/insect source | 20 | Added separately; not attributed to the Lin disease review |

### 1. Normalize the review into a common row schema

The heterogeneous source tables were mapped into 40 string-valued fields. The
common fields include disease or pest, causal agent, locus or allele, linkage
group and chromosome, markers and positions, resistance phenotype, mapping
population, phenotypic variance or effect, candidate genes, donor source, and
the cited reference. Values such as positions and effects remain strings
because the paper mixes base-pair intervals, centimorgan positions, percentages,
free text, and source-specific notation.

Each record receives a stable `SOYRES-####` identifier. The original extracted
row is retained in `raw_row_text`, and `source_col_01` through `source_col_14`
preserve the source columns. These fields make it possible to audit the
normalized values without treating the browser display as a replacement for
the publication.

### 2. Reconstruct the supplementary Word tables from OOXML

The three supplementary files contain native Word tables, so
`scripts/rebuild_curated_data.py` reads their OOXML cells directly instead of
extracting rendered text. It resolves vertical cell merges, skips the one
intentional blank separator row, and applies a separate column map to each
table:

| Lin supplement | Repository file | Rows | Source columns |
|---|---|---:|---:|
| Supplementary Table 1 | `122_2022_4101_MOESM2_ESM.docx` | 134 | 10 |
| Supplementary Table 2 | `122_2022_4101_MOESM3_ESM.docx` | 90 | 10 |
| Supplementary Table 3 | `122_2022_4101_MOESM1_ESM.docx` | 202 | 9 |

This reconstruction corrected a systematic column shift in all 134
Supplementary Table 1 records. Candidate-gene, donor, and reference values now
come from their intended cells; 21 of those records contain a named candidate
gene.

### 3. Standardize chromosome labels conservatively

The review uses both numeric chromosomes and historical soybean molecular
linkage-group labels. The rebuild fills a blank numeric chromosome only when
the MLG has an unambiguous standard crosswalk (`D1a` to chromosome 1 through
`I` to chromosome 20). This supplied 130 previously blank chromosome values.
The source MLG text remains unchanged in `MLG_chr`, and coordinates are never
silently translated between genome assemblies.

### 4. Preserve uncertainty in the main-paper PDF tables

The main-paper tables have a vector text layer, but many are rotated, wrap one
biological record across multiple printed lines, or continue across pages. The
canonical dataset therefore retains extraction warnings rather than pretending
all row boundaries are certain:

- `ok_extracted` identifies uncomplicated extracted rows;
- `multi_line_extraction` identifies records assembled from multiple lines;
- `sparse_or_continuation` marks rows that may be fragments or continuations.

`scripts/extract_lin_pdf_tables.py` provides a coordinate-aware prototype for
Table 5. It uses the printed header positions as column boundaries and groups
wrapped/page-leading lines into 139 provisional record blocks. That prototype
is intentionally stored in `reports/lin_table5_extraction_prototype.json` and
has **not** replaced the 299 canonical Table 5 rows; the remaining row-boundary
decisions require visual checking against the rendered paper.

### 5. Regenerate mirrors and audit every deterministic repair

The rebuild writes a staging set, validates it, and only then replaces the CSV,
JSON, JSONL, schema, manifest, and field dictionaries. Deterministic source
repairs are recorded field by field in `data/curation_audit.json`.
`scripts/validate_data.py` checks record IDs, field order, cross-format equality,
source-table row counts, supplement mappings, MLG/chromosome mappings, and the
repaired Supplementary Table 1 columns. The review's underlying primary studies
have not been independently revalidated; the corresponding evidence-status
field explicitly describes the records as reported by the review.

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
