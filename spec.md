# Spec: Soybean Resistance QTL Browser

## Purpose

Build a searchable, filterable browser for a combined soybean resistance collation containing disease, nematode, viral, bacterial, oomycete, fungal, and herbivore/insect resistance entries. The canonical dataset is `data/soybean_resistance_qtl_collation.csv`, with browser-ready mirrors in JSON and JSONL.

The browser should help a user explore resistance loci/QTLs/genes/GWAS signals, inspect the source evidence, identify rows needing manual curation, and export filtered subsets.

## Dataset

- Records: **1,996**
- Fields: **40**
- Primary key: `entry_id`
- Canonical file: `data/soybean_resistance_qtl_collation.csv`
- Browser file: `data/soybean_resistance_qtl_collation.json`
- Streaming/backend file: `data/soybean_resistance_qtl_collation.jsonl`
- Field definitions: `data/field_dictionary.md`
- Machine-readable schema: `data/schema.json`
- Dataset manifest: `data/manifest.json`

## Primary user stories

1. As a soybean breeder or researcher, I can search across disease/pest names, loci, markers, donor sources, candidate genes, and references.
2. As a curator, I can filter to extraction-quality flags such as `sparse_or_continuation` or `multi_line_extraction` and correct questionable rows.
3. As a resistance-genetics user, I can filter by target group, disease/pest, chromosome, source category, evidence status, and quality flag.
4. As a reviewer, I can open a row-detail panel showing every field, including raw extraction text and source columns.
5. As a data user, I can export the currently filtered rows as CSV.
6. As a downstream developer, I can ingest the data from CSV, JSON, or JSONL without relying on spreadsheet-specific formatting.

## Required views

### 1. Overview dashboard

Show at least these summary cards:

- Total records.
- Distinct diseases/pests.
- Distinct target groups.
- Herbivore/insect row count.
- Rows by `row_quality_flag`.
- Rows by `source_category`.

Optional charts:

- Bar chart: records by `target_group`.
- Bar chart: top 15 `disease_or_pest` values.
- Stacked bar: `target_group` by `row_quality_flag`.

### 2. Search and filter table

Default visible columns:

- `entry_id`
- `target_group`
- `disease_or_pest`
- `causal_agent_or_species`
- `locus_or_allele`
- `MLG_chr`
- `chromosome`
- `linked_flanking_markers`
- `marker_position`
- `resistance_spectrum_or_testing_method`
- `PVE_or_effect`
- `population_type_size`
- `screening_environment`
- `donor_source`
- `evidence_status`
- `row_quality_flag`
- `source_reference`

All rows should remain accessible in the detail view, even when not displayed in the table.

Required filters:

- `target_group`
- `disease_or_pest`
- `chromosome`
- `source_category`
- `evidence_status`
- `row_quality_flag`

The global search should search all fields case-insensitively.

### 3. Row detail drawer/modal

Show all fields in source order. Important fields should be visually emphasized:

- `entry_id`
- `target_group`
- `disease_or_pest`
- `causal_agent_or_species`
- `locus_or_allele`
- `MLG_chr`
- `chromosome`
- `linked_flanking_markers`
- `marker_position`
- `assembly_or_coordinate_system`
- `donor_source`
- `evidence_status`
- `row_quality_flag`
- `source_reference`
- `source_url_or_doi`
- `raw_row_text`

If `source_url_or_doi` begins with `http`, render it as an external link. If it is a DOI string rather than a URL, display as plain text unless the application implements DOI expansion.

### 4. Export

Export visible rows as CSV. Include all fields, not just visible table columns.

## Data model notes

All fields are strings. Do not coerce `chromosome`, `PVE_or_effect`, `marker_position`, or `source_col_*` values into numeric types without preserving the original string, because these fields often contain ranges, linkage-group labels, percentages, or mixed annotations.

Preferred coordinate handling:

- Treat Gmax2.0 as the default when available in `assembly_or_coordinate_system` or implied by source rows.
- Do not silently convert older cM or assembly coordinates.
- A future enhancement can add parsed numeric interval columns such as `position_start_bp`, `position_end_bp`, and `coordinate_parse_status`.

## Quality and curation rules

1. Rows with `row_quality_flag` containing `ok_extracted` or `ok_docx_supplement_extract` can be treated as normal source-derived rows.
2. Rows with `row_quality_flag` containing `multi_line_extraction`, `sparse_or_continuation`, or a blank value should be visually flagged as needing manual validation.
3. Rows with `evidence_status` containing `preliminary`, `grey literature`, or `needs primary publication` should be visually marked as preliminary evidence, not removed.
4. Preserve `raw_row_text` and `source_col_01` through `source_col_14` in the detail view for auditability.
5. Do not deduplicate rows automatically unless the curator approves a deduplication policy; many rows represent distinct race/isolate/population contexts for the same locus.

## Recommended implementation approach

### Static implementation

A static version can load `data/soybean_resistance_qtl_collation.json` with `fetch()`. This is already scaffolded in `browser/`.

Local development:

```bash
python -m http.server 8000
```

Open:

```text
http://localhost:8000/browser/
```

### React implementation

Recommended stack:

- Vite or Next.js.
- TanStack Table for sortable/filterable table.
- Fuse.js or MiniSearch for client-side search.
- Recharts for summary charts.
- Zod or JSON Schema validation against `data/schema.json`.
- URL query parameters for shareable filters.

Suggested components:

- `DatasetProvider`
- `SummaryCards`
- `FacetFilters`
- `GlobalSearch`
- `QtlTable`
- `RowDetailDrawer`
- `ExportButton`
- `QualityBadge`

### Backend implementation, if needed

For larger future versions, load JSONL into SQLite or DuckDB. Suggested tables:

- `entries(entry_id primary key, ...all columns as text...)`
- Optional `facets(field, value, count)` materialized table.
- Optional FTS5 virtual table over all fields.

## Acceptance criteria

- The browser loads all 1,996 records.
- Global search works across all fields.
- Filters work for target group, disease/pest, chromosome, evidence status, source category, and quality flag.
- Sorting works on visible columns.
- Row detail displays all fields and preserves raw text.
- Filtered export produces a valid CSV with all fields.
- Preliminary gall midge data is included and flagged rather than hidden.
- Quality warnings are visible for rows needing manual review.
- The app can run locally with a simple static server.

## Known caveats

- The source dataset is a comprehensive draft and includes raw extraction artifacts from complex tables.
- Some PDF rows may be continuation lines rather than fully independent biological entries.
- Some entries share loci but differ by race, isolate, donor source, population, marker set, or source table.
- `PVE_or_effect` is mixed-format and should be displayed as text unless curated into parsed numeric columns.
- `marker_position` is mixed-format and should be displayed as text unless curated into parsed interval columns.

## Suggested future curation enhancements

- Add `curation_status`, `curator_notes`, and `last_reviewed_by` columns.
- Parse `chromosome` into normalized chromosome IDs `01` through `20` where possible.
- Add `position_start_bp`, `position_end_bp`, and `coordinate_parse_status`.
- Add `is_cloned_gene`, `is_validated_qtl`, `is_gwas`, and `is_preliminary` booleans derived from `evidence_status`.
- Link source rows to DOI metadata and PMID where available.
- Add per-row confidence tiers for marker-assisted-selection usefulness.
