# Lin et al. source review and curation status

## Safe deterministic changes now applied

The three supplementary Word tables are structurally clean and suitable as
authoritative sources. Their native OOXML cells are now parsed directly,
including vertically merged cells:

| Source | Data rows | Result |
|---|---:|---|
| Supplementary Table 1 | 134 | Reconstructed from 10 native columns |
| Supplementary Table 2 | 90 | Reconstructed from 10 native columns |
| Supplementary Table 3 | 202 | Reconstructed from 9 native columns |

This repaired a systematic shift in all 134 Supplementary Table 1 records. The
candidate-gene, donor, and reference columns are now assigned to their intended
fields; 21 of those records contain a named candidate gene. The rebuild also
filled 130 blank numeric chromosome values from unambiguous legacy soybean MLG
labels. The original MLG text remains intact for provenance.

The field-level changes are recorded in `data/curation_audit.json`. CSV, JSON,
and JSONL mirrors, schema field order, manifest counts, record IDs, source-table
row counts, MLG/chromosome mappings, and the repaired supplement columns are
checked by `scripts/validate_data.py`.

## Main PDF tables

The PDF has a usable vector text layer, but the tables are rotated and many
records wrap across physical lines and pages. The original extraction treated
too many physical lines as records. Table 5 currently occupies 299 canonical
rows, including 86 rows flagged as sparse/continuation and 114 with a multiline
flag.

The coordinate-aware prototype uses each printed header's physical x-position
as a column boundary, then attaches wrapped lines and page-leading
continuations to a visual record. It reconstructs 139 provisional Table 5
record blocks from PDF pages 16–25. For example, the `RpsZS18` block correctly
keeps `Glyma.02g245700`, `Glyma.02g245800`, and `Glyma.02g246300` together with
the locus, Zaoshu18 donor, and citations.

This output remains non-canonical. Before replacement, the row-boundary rules
need spot-checking against rendered pages, especially entries represented in
the paper's “Other name” column and records that span page breaks. Parsers for
the other main tables should be configured per table because their printed
schemas differ.

## Useful next inputs for candidate-gene discovery

The Wm82 GFF is the highest-value next input, provided its assembly/version is
known. The matching genome FASTA, gene/transcript annotation release, and gene
ID alias mapping are also useful. They enable interval overlap, nearest-gene
searches, consistent coordinate conversion, and normalization of old `Glyma`
identifiers.

Beyond genes already named in the review, candidate ranking can combine:

- genes inside or nearest each mapped interval;
- resistance-gene domains and defense/pathogen-response annotations;
- expression after infection or in relevant root/leaf/tissue datasets;
- variants and predicted functional effects in resistant versus susceptible
  parents;
- haplotypes, local LD, fine-mapping, GWAS, and eQTL evidence;
- soybean paralogs and orthologs of validated resistance genes in other crops;
- syntenic candidates when source coordinates use another soybean assembly.

These evidence types should be stored separately from source-reported candidate
genes so that reported evidence and computed prioritization remain auditable.
