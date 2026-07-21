const DATA_URL = "../data/soybean_resistance_qtl_collation.json";
const MANIFEST_URL = "../data/manifest.json";
const SCHEMA_URL = "../data/schema.json";
const PRR_URL = "../data/prr_gene_calls.json";
const PRR_OVERLAPS_URL = "../data/qtl_prr_overlaps.json";
const GENE_MANIFEST_URL = "../data/wm82_gene_manifest.json";
const EMBEDDED_DATA = globalThis.SOYBEAN_QTL_BROWSER_DATA || null;

const DEFAULT_SORT = { field: "entry_id", direction: "asc" };
const PRR_VIRTUAL_FIELD = "prr_hits";
const FALLBACK_COLUMNS = [
  "entry_id",
  "target_group",
  "disease_or_pest",
  "causal_agent_or_species",
  "locus_or_allele",
  "MLG_chr",
  "chromosome",
  "linked_flanking_markers",
  "marker_position",
  "resistance_spectrum_or_testing_method",
  "PVE_or_effect",
  "population_type_size",
  "screening_environment",
  "donor_source",
  "evidence_status",
  "row_quality_flag",
  "source_reference"
];

const FILTER_CONFIG = [
  { field: "target_group", id: "targetGroupFilter", label: "Target group" },
  { field: "disease_or_pest", id: "diseaseFilter", label: "Disease or pest" },
  { field: "chromosome", id: "chromosomeFilter", label: "Chromosome" },
  { field: "source_category", id: "sourceCategoryFilter", label: "Source category" },
  { field: "evidence_status", id: "evidenceFilter", label: "Evidence status" },
  { field: "row_quality_flag", id: "qualityFilter", label: "Quality flag" }
];

const IMPORTANT_FIELDS = new Set([
  "entry_id",
  "target_group",
  "disease_or_pest",
  "causal_agent_or_species",
  "locus_or_allele",
  "MLG_chr",
  "chromosome",
  "linked_flanking_markers",
  "marker_position",
  "assembly_or_coordinate_system",
  "donor_source",
  "evidence_status",
  "row_quality_flag",
  "source_reference",
  "source_url_or_doi",
  "raw_row_text"
]);

const DETAIL_HIGHLIGHT_FIELDS = [
  "entry_id",
  "target_group",
  "disease_or_pest",
  "causal_agent_or_species",
  "locus_or_allele",
  "chromosome",
  "donor_source",
  "evidence_status",
  "row_quality_flag",
  "source_reference"
];

const DEFAULT_QUALITY_NOTES = [
  "Rows flagged sparse_or_continuation or multi_line_extraction should be reviewed before biological interpretation.",
  "The soybean gall midge row is intentionally included and marked as preliminary evidence.",
  "raw_row_text and source_col_01 through source_col_14 remain available for audit and manual correction.",
  "Coordinates remain as source text; mixed cM and assembly-specific positions are not silently converted."
];

const state = {
  rows: [],
  visibleRows: [],
  fieldOrder: [],
  fieldDescriptions: {},
  manifest: null,
  geneManifest: null,
  prrCatalog: [],
  prrByGene: new Map(),
  prrByEntry: new Map(),
  defaultColumns: [...FALLBACK_COLUMNS],
  sort: { ...DEFAULT_SORT },
  selectedRowIndex: null
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  init().catch(handleInitError);
});

function cacheElements() {
  const ids = [
    "summaryCards",
    "qualityBreakdown",
    "sourceBreakdown",
    "targetBreakdown",
    "diseaseBreakdown",
    "searchInput",
    "targetGroupFilter",
    "diseaseFilter",
    "chromosomeFilter",
    "sourceCategoryFilter",
    "evidenceFilter",
    "qualityFilter",
    "prrFamilyFilter",
    "prrDistanceFilter",
    "prrSummary",
    "prrFamilyBreakdown",
    "prrMethodNote",
    "activeFilters",
    "visibleCount",
    "resultSummary",
    "manualReviewCount",
    "preliminaryCount",
    "downloadCsv",
    "resetFilters",
    "qualityNotes",
    "datasetMeta",
    "detailPanel",
    "detailContent",
    "closePanel",
    "drawerBackdrop"
  ];

  for (const id of ids) {
    elements[id] = document.getElementById(id);
  }

  elements.tableHead = document.querySelector("#dataTable thead");
  elements.tableBody = document.querySelector("#dataTable tbody");
}

async function init() {
  const [rows, manifest, schema, prrData, prrOverlapData, geneManifest] = EMBEDDED_DATA
    ? [
        EMBEDDED_DATA.rows,
        EMBEDDED_DATA.manifest,
        EMBEDDED_DATA.schema,
        EMBEDDED_DATA.prr,
        EMBEDDED_DATA.qtlPrrOverlaps,
        EMBEDDED_DATA.geneManifest
      ]
    : await Promise.all([
        fetchJson(DATA_URL),
        fetchJson(MANIFEST_URL).catch(() => null),
        fetchJson(SCHEMA_URL).catch(() => null),
        fetchJson(PRR_URL).catch(() => null),
        fetchJson(PRR_OVERLAPS_URL).catch(() => null),
        fetchJson(GENE_MANIFEST_URL).catch(() => null)
      ]);

  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("The browser dataset did not contain any rows.");
  }

  state.manifest = manifest;
  state.geneManifest = geneManifest;
  state.fieldOrder = getFieldOrder(schema, rows[0]);
  state.fieldDescriptions = getFieldDescriptions(schema);
  state.defaultColumns = getDefaultColumns(manifest, state.fieldOrder);
  addPrrVirtualColumn();
  initializePrrData(prrData, prrOverlapData);
  state.rows = decorateRows(rows);

  populateAllFacets();
  applyUrlState();
  bindEvents();
  renderStaticUi();
  refreshView();
}

function bindEvents() {
  elements.searchInput.addEventListener("input", refreshView);
  elements.prrFamilyFilter.addEventListener("change", refreshView);
  elements.prrDistanceFilter.addEventListener("change", refreshView);

  for (const { id } of FILTER_CONFIG) {
    elements[id].addEventListener("change", refreshView);
  }

  elements.resetFilters.addEventListener("click", resetFilters);
  elements.downloadCsv.addEventListener("click", downloadVisibleCsv);
  elements.closePanel.addEventListener("click", closeDetail);
  elements.drawerBackdrop.addEventListener("click", closeDetail);

  elements.tableHead.addEventListener("click", event => {
    const button = event.target.closest("[data-sort-field]");
    if (!button) {
      return;
    }
    updateSort(button.dataset.sortField);
  });

  elements.tableBody.addEventListener("click", event => {
    const row = event.target.closest("tr[data-row-index]");
    if (!row) {
      return;
    }
    openDetail(Number(row.dataset.rowIndex));
  });

  elements.tableBody.addEventListener("keydown", event => {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    const row = event.target.closest("tr[data-row-index]");
    if (!row) {
      return;
    }
    event.preventDefault();
    openDetail(Number(row.dataset.rowIndex));
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && elements.detailPanel.classList.contains("open")) {
      closeDetail();
    }
  });
}

function fetchJson(url) {
  return fetch(url).then(response => {
    if (!response.ok) {
      throw new Error(`Could not load ${url} (${response.status})`);
    }
    return response.json();
  });
}

function getFieldOrder(schema, sampleRow) {
  const fromSchema = Object.keys(schema?.properties || {});
  if (fromSchema.length > 0) {
    return fromSchema;
  }
  return Object.keys(sampleRow || {});
}

function getFieldDescriptions(schema) {
  const properties = schema?.properties || {};
  return Object.fromEntries(
    Object.entries(properties).map(([field, definition]) => [field, text(definition?.description).trim()])
  );
}

function getDefaultColumns(manifest, fieldOrder) {
  const recommended = manifest?.recommended_default_columns;
  const source = Array.isArray(recommended) && recommended.length > 0 ? recommended : FALLBACK_COLUMNS;
  return source.filter(field => fieldOrder.includes(field));
}

function addPrrVirtualColumn() {
  const markerIndex = state.defaultColumns.indexOf("marker_position");
  const insertionIndex = markerIndex >= 0 ? markerIndex + 1 : state.defaultColumns.length;
  state.defaultColumns.splice(insertionIndex, 0, PRR_VIRTUAL_FIELD);
  state.fieldDescriptions[PRR_VIRTUAL_FIELD] =
    "PRR genes whose mapped Wm82.a2 coordinates overlap or fall within the selected distance of the reported QTL coordinate.";
}

function initializePrrData(prrData, overlapData) {
  state.prrCatalog = Array.isArray(prrData?.genes) ? prrData.genes : [];
  state.prrByGene = new Map(state.prrCatalog.map(item => [item.gene_id_a6, item]));
  state.prrByEntry = new Map();
  for (const overlap of overlapData?.overlaps || []) {
    if (!state.prrByEntry.has(overlap.entry_id)) {
      state.prrByEntry.set(overlap.entry_id, []);
    }
    state.prrByEntry.get(overlap.entry_id).push(overlap);
  }
}

function decorateRows(rows) {
  return rows.map((row, index) => {
    const searchText = Object.values(row).map(value => normalizeSearch(value)).join(" ");
    const manualReview = isManualReview(row);
    const preliminary = isPreliminary(row);
    return {
      ...row,
      __index: index,
      __searchText: searchText,
      __manualReview: manualReview,
      __preliminary: preliminary,
      __prrHits: state.prrByEntry.get(row.entry_id) || []
    };
  });
}

function renderStaticUi() {
  renderDatasetMeta();
  renderSummaryCards();
  renderQualityNotes();
}

function renderDatasetMeta() {
  const chips = [
    `${formatCount(state.rows.length)} rows`,
    `${formatCount(state.fieldOrder.length)} fields`,
    state.geneManifest ? `${formatCount(state.geneManifest.total_gene_calls)} Wm82 gene calls` : "",
    state.prrCatalog.length ? `${formatCount(state.prrCatalog.length)} a6 PRRs` : "",
    "Primary key: entry_id",
    "Static browser"
  ].filter(Boolean);

  elements.datasetMeta.innerHTML = chips
    .map(label => `<span class="meta-chip">${escapeHtml(label)}</span>`)
    .join("");
}

function renderSummaryCards() {
  const largestTargetGroup = getCountEntries(state.rows, "target_group", { limit: 1 })[0];
  const topDisease = getCountEntries(state.rows, "disease_or_pest", { limit: 1 })[0];
  const herbivoreCount = state.rows.filter(row => text(row.target_group).trim() === "Herbivore/insect").length;

  const cards = [
    {
      label: "Total records",
      value: formatCount(state.rows.length),
      meta: `${formatCount(state.fieldOrder.length)} fields available for detail view and CSV export.`
    },
    {
      label: "Distinct diseases or pests",
      value: formatCount(countDistinct(state.rows, "disease_or_pest")),
      meta: topDisease ? `Largest category: ${topDisease.value} (${formatCount(topDisease.count)} rows).` : ""
    },
    {
      label: "Distinct target groups",
      value: formatCount(countDistinct(state.rows, "target_group")),
      meta: largestTargetGroup ? `Largest group: ${largestTargetGroup.value} (${formatCount(largestTargetGroup.count)} rows).` : ""
    },
    {
      label: "Herbivore or insect rows",
      value: formatCount(herbivoreCount),
      meta: "Includes the preliminary soybean gall midge entry."
    }
  ];

  elements.summaryCards.innerHTML = cards.map(card => `
    <article class="summary-card">
      <div class="summary-label">${escapeHtml(card.label)}</div>
      <div class="summary-value">${escapeHtml(card.value)}</div>
      <div class="summary-meta">${escapeHtml(card.meta)}</div>
    </article>
  `).join("");
}

function renderQualityNotes() {
  const notes = Array.isArray(state.manifest?.quality_notes) && state.manifest.quality_notes.length > 0
    ? state.manifest.quality_notes
    : DEFAULT_QUALITY_NOTES;

  elements.qualityNotes.innerHTML = notes
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("");
}

function populateAllFacets() {
  for (const config of FILTER_CONFIG) {
    populateFacet(config);
  }
}

function populateFacet({ field, id }) {
  const select = elements[id];
  const counts = getCountEntries(state.rows, field, { sortByCount: false });
  const selected = select.value;
  const options = ['<option value="">All</option>'];

  for (const { value, count } of counts) {
    options.push(
      `<option value="${escapeHtml(value)}">${escapeHtml(value)} (${formatCount(count)})</option>`
    );
  }

  select.innerHTML = options.join("");

  if ([...select.options].some(option => option.value === selected)) {
    select.value = selected;
  }
}

function applyUrlState() {
  const params = new URLSearchParams(window.location.search);
  const query = params.get("q");
  const sortField = params.get("sort");
  const sortDirection = params.get("dir");

  if (query) {
    elements.searchInput.value = query;
  }

  for (const { field, id } of FILTER_CONFIG) {
    const value = params.get(field);
    if (!value) {
      continue;
    }
    const select = elements[id];
    if ([...select.options].some(option => option.value === value)) {
      select.value = value;
    }
  }

  if (state.defaultColumns.includes(sortField)) {
    state.sort.field = sortField;
  }

  if (sortDirection === "desc") {
    state.sort.direction = "desc";
  }

  const prrFamily = params.get("prr_family");
  const prrDistance = params.get("prr_distance");
  if ([...elements.prrFamilyFilter.options].some(option => option.value === prrFamily)) {
    elements.prrFamilyFilter.value = prrFamily;
  }
  if ([...elements.prrDistanceFilter.options].some(option => option.value === prrDistance)) {
    elements.prrDistanceFilter.value = prrDistance;
  }
}

function refreshView() {
  state.visibleRows = sortRows(getFilteredRows());
  renderActiveFilters();
  renderDashboardBreakdowns();
  renderPrrPanel();
  renderToolbar();
  renderTable();
  updateUrlState();
}

function getFilteredRows(ignorePrrFilter = false) {
  const query = normalizeSearch(elements.searchInput.value.trim());
  const selectedFamily = elements.prrFamilyFilter.value;

  return state.rows.filter(row => {
    for (const { field, id } of FILTER_CONFIG) {
      const selected = elements[id].value;
      if (selected && text(row[field]).trim() !== selected) {
        return false;
      }
    }

    if (!ignorePrrFilter && selectedFamily && getPrrHits(row, selectedFamily).length === 0) {
      return false;
    }

    if (!query) {
      return true;
    }

    return row.__searchText.includes(query);
  });
}

function sortRows(rows) {
  const { field, direction } = state.sort;
  const multiplier = direction === "asc" ? 1 : -1;

  return [...rows].sort((left, right) => {
    const leftValue = field === PRR_VIRTUAL_FIELD ? getPrrHits(left).length : left[field];
    const rightValue = field === PRR_VIRTUAL_FIELD ? getPrrHits(right).length : right[field];
    const comparison = compareValues(leftValue, rightValue);
    if (comparison !== 0) {
      return comparison * multiplier;
    }
    return compareValues(left.entry_id, right.entry_id);
  });
}

function updateSort(field) {
  if (!field) {
    return;
  }

  if (state.sort.field === field) {
    state.sort.direction = state.sort.direction === "asc" ? "desc" : "asc";
  } else {
    state.sort = { field, direction: "asc" };
  }

  refreshView();
}

function renderActiveFilters() {
  const chips = [];
  const query = elements.searchInput.value.trim();

  if (query) {
    chips.push(
      `<span class="filter-chip"><strong>Search</strong>${escapeHtml(query)}</span>`
    );
  }

  for (const { field, id, label } of FILTER_CONFIG) {
    const value = elements[id].value;
    if (!value) {
      continue;
    }
    chips.push(
      `<span class="filter-chip"><strong>${escapeHtml(label)}</strong>${escapeHtml(value)}</span>`
    );
  }

  const prrFamily = elements.prrFamilyFilter.value;
  if (prrFamily) {
    chips.push(
      `<span class="filter-chip"><strong>PRR family</strong>${escapeHtml(prrFamily === "ANY" ? "Any" : prrFamily)}</span>`,
      `<span class="filter-chip"><strong>PRR distance</strong>${escapeHtml(getPrrDistanceLabel())}</span>`
    );
  }

  if (chips.length === 0) {
    chips.push('<span class="meta-chip">No filters applied. Showing the full dataset.</span>');
  }

  elements.activeFilters.innerHTML = chips.join("");
}

function renderDashboardBreakdowns() {
  const rowsForBreakdowns = hasActiveCriteria() ? state.visibleRows : state.rows;

  renderBreakdownList(
    elements.qualityBreakdown,
    getCountEntries(rowsForBreakdowns, "row_quality_flag", { includeBlank: true }),
    { emptyLabel: "No rows match the current search or filters." }
  );

  renderBreakdownList(
    elements.sourceBreakdown,
    getCountEntries(rowsForBreakdowns, "source_category"),
    { emptyLabel: "No rows match the current search or filters." }
  );

  renderBreakdownList(
    elements.targetBreakdown,
    getCountEntries(rowsForBreakdowns, "target_group"),
    { emptyLabel: "No rows match the current search or filters." }
  );

  renderBreakdownList(
    elements.diseaseBreakdown,
    getCountEntries(rowsForBreakdowns, "disease_or_pest", { limit: 15 }),
    { emptyLabel: "No rows match the current search or filters." }
  );
}

function getPrrDistance() {
  return Number(elements.prrDistanceFilter.value || 0);
}

function getPrrDistanceLabel() {
  const option = elements.prrDistanceFilter.selectedOptions[0];
  return option ? option.textContent : "Inside reported coordinate";
}

function getPrrHits(row, family = "") {
  const threshold = getPrrDistance();
  return (row.__prrHits || []).filter(hit => {
    if (hit.distance_bp > threshold) {
      return false;
    }
    return !family || family === "ANY" || hit.family === family;
  });
}

function renderPrrPanel() {
  if (state.prrCatalog.length === 0) {
    elements.prrSummary.innerHTML = '<div class="empty-state">PRR gene calls are not available.</div>';
    elements.prrFamilyBreakdown.innerHTML = "";
    elements.prrMethodNote.textContent = "";
    return;
  }

  const baseRows = getFilteredRows(true);
  const selectedFamily = elements.prrFamilyFilter.value;
  const allHits = baseRows.flatMap(row => getPrrHits(row));
  const selectedHits = selectedFamily
    ? baseRows.flatMap(row => getPrrHits(row, selectedFamily))
    : allHits;
  const selectedQtlCount = new Set(selectedHits.map(hit => hit.entry_id)).size;
  const selectedGeneCount = new Set(selectedHits.map(hit => hit.gene_id_a6)).size;
  const mappedCount = state.prrCatalog.filter(item => item.mapped_a2_call).length;
  const selectedLabel = selectedFamily
    ? (selectedFamily === "ANY" ? "Any family" : selectedFamily)
    : "All families";

  elements.prrSummary.innerHTML = [
    { value: selectedQtlCount, label: `${selectedLabel} QTLs` },
    { value: selectedGeneCount, label: "Distinct PRR hits" },
    { value: selectedHits.length, label: "QTL–gene pairs" },
    { value: mappedCount, label: "a6 PRRs mapped to a2" }
  ].map(item => `
    <div class="prr-stat">
      <strong>${escapeHtml(formatCount(item.value))}</strong>
      <span>${escapeHtml(item.label)}</span>
    </div>
  `).join("");

  elements.prrFamilyBreakdown.innerHTML = ["XI", "XII", "RLP"].map(family => {
    const hits = baseRows.flatMap(row => getPrrHits(row, family));
    const qtls = new Set(hits.map(hit => hit.entry_id)).size;
    const genes = new Set(hits.map(hit => hit.gene_id_a6)).size;
    const active = selectedFamily === family;
    return `
      <article class="prr-family-card ${active ? "is-active" : ""}">
        <span class="prr-family-name">${escapeHtml(family)}</span>
        <strong>${escapeHtml(formatCount(qtls))} QTLs</strong>
        <span>${escapeHtml(formatCount(genes))} genes · ${escapeHtml(formatCount(hits.length))} pairs</span>
      </article>
    `;
  }).join("");

  const totalGenes = state.geneManifest?.total_gene_calls || 0;
  elements.prrMethodNote.textContent =
    `${getPrrDistanceLabel()}. ${formatCount(totalGenes)} Wm82 gene calls across a2, a4, and a6; ` +
    `${formatCount(state.prrCatalog.length)} a6 PRRs supplied, ${formatCount(mappedCount)} mapped to a2 without coordinate guessing.`;
}

function renderBreakdownList(container, entries, { emptyLabel }) {
  if (!entries.length) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(emptyLabel)}</div>`;
    return;
  }

  const max = Math.max(...entries.map(entry => entry.count), 1);

  container.innerHTML = entries.map(entry => {
    const label = entry.value || "(blank)";
    const width = Math.max(6, Math.round((entry.count / max) * 100));
    return `
      <div class="breakdown-item">
        <div class="breakdown-row">
          <div class="breakdown-label"><span title="${escapeHtml(label)}">${escapeHtml(label)}</span></div>
          <div class="breakdown-value">${escapeHtml(formatCount(entry.count))}</div>
        </div>
        <div class="breakdown-bar" aria-hidden="true">
          <div class="breakdown-fill" style="width: ${width}%"></div>
        </div>
      </div>
    `;
  }).join("");
}

function renderToolbar() {
  elements.visibleCount.textContent = formatCount(state.visibleRows.length);

  if (hasActiveCriteria()) {
    elements.resultSummary.textContent = `Showing ${formatCount(state.visibleRows.length)} of ${formatCount(state.rows.length)} rows.`;
  } else {
    elements.resultSummary.textContent = `Showing all ${formatCount(state.rows.length)} rows.`;
  }

  const manualReviewCount = state.visibleRows.filter(row => row.__manualReview).length;
  const preliminaryCount = state.visibleRows.filter(row => row.__preliminary).length;

  elements.manualReviewCount.textContent = `${formatCount(manualReviewCount)} need review`;
  elements.preliminaryCount.textContent = `${formatCount(preliminaryCount)} preliminary evidence`;
}

function renderTable() {
  renderTableHead();

  if (state.visibleRows.length === 0) {
    elements.tableBody.innerHTML = `
      <tr>
        <td colspan="${state.defaultColumns.length}" class="empty-row">
          No rows matched the current search and filters.
        </td>
      </tr>
    `;
    return;
  }

  elements.tableBody.innerHTML = state.visibleRows.map(row => {
    const rowClasses = [
      row.__manualReview ? "is-manual-review" : "",
      row.__preliminary ? "is-preliminary" : "",
      row.__index === state.selectedRowIndex ? "is-selected" : ""
    ].filter(Boolean).join(" ");

    return `
      <tr class="${rowClasses}" data-row-index="${row.__index}" tabindex="0">
        ${state.defaultColumns.map(field => `
          <td class="${escapeHtml(getCellClass(field))}">
            ${renderCell(field, row)}
          </td>
        `).join("")}
      </tr>
    `;
  }).join("");
}

function renderTableHead() {
  elements.tableHead.innerHTML = `
    <tr>
      ${state.defaultColumns.map(field => {
        const label = humanizeField(field);
        const description = state.fieldDescriptions[field] || label;
        const isActive = state.sort.field === field;
        const direction = isActive ? (state.sort.direction === "asc" ? " ^" : " v") : "";
        return `
          <th scope="col">
            <button
              type="button"
              class="sort-button ${isActive ? "is-active" : ""}"
              data-sort-field="${escapeHtml(field)}"
              title="${escapeHtml(description)}"
            >
              <span>${escapeHtml(label)}</span>
              <span class="sort-indicator" aria-hidden="true">${escapeHtml(direction)}</span>
            </button>
          </th>
        `;
      }).join("")}
    </tr>
  `;
}

function getCellClass(field) {
  if (field === PRR_VIRTUAL_FIELD) {
    return "cell-prr";
  }

  if (field === "evidence_status" || field === "row_quality_flag") {
    return "cell-wrap";
  }

  if (field === "source_reference" || field === "resistance_spectrum_or_testing_method") {
    return "cell-reference";
  }

  return "";
}

function renderCell(field, row) {
  if (field === PRR_VIRTUAL_FIELD) {
    return renderPrrCell(row);
  }

  const value = text(row[field]).trim();

  if (field === "entry_id") {
    return `<span class="cell-text cell-id" title="${escapeHtml(value)}">${escapeHtml(value)}</span>`;
  }

  if (field === "target_group") {
    return `<span class="badge badge-group" title="${escapeHtml(value)}">${escapeHtml(value || "Not reported")}</span>`;
  }

  if (field === "evidence_status") {
    return renderEvidenceCell(row);
  }

  if (field === "row_quality_flag") {
    return renderQualityCell(row);
  }

  if (!value) {
    return '<span class="cell-text" title="Not reported"></span>';
  }

  return `<span class="cell-text" title="${escapeHtml(value)}">${escapeHtml(value)}</span>`;
}

function renderPrrCell(row) {
  const selectedFamily = elements.prrFamilyFilter.value;
  const hits = getPrrHits(row, selectedFamily);
  if (hits.length === 0) {
    return '<span class="cell-text" title="No PRR hit at the selected distance"></span>';
  }
  const visible = hits.slice(0, 4);
  const remainder = hits.length - visible.length;
  return `
    <div class="prr-hit-stack">
      ${visible.map(hit => `
        <span class="prr-hit prr-${escapeHtml(hit.family.toLowerCase())}" title="${escapeHtml(formatPrrRelationship(hit))}">
          <strong>${escapeHtml(hit.family)}</strong> ${escapeHtml(hit.gene_id_a6)}
        </span>
      `).join("")}
      ${remainder > 0 ? `<span class="cell-caption">+${escapeHtml(formatCount(remainder))} more</span>` : ""}
    </div>
  `;
}

function formatPrrRelationship(hit) {
  if (hit.distance_bp === 0) {
    return `Overlaps reported ${hit.qtl_coordinate_type === "reported_interval" ? "QTL interval" : "marker coordinate"}`;
  }
  return `${formatDistance(hit.distance_bp)} from reported coordinate`;
}

function formatDistance(distanceBp) {
  if (distanceBp >= 1_000_000) {
    return `${(distanceBp / 1_000_000).toFixed(2)} Mb`;
  }
  return `${Math.round(distanceBp / 1_000)} kb`;
}

function renderEvidenceCell(row) {
  const value = text(row.evidence_status).trim();
  const badge = getEvidenceBadge(row);
  return `
    <div class="cell-stack">
      <span class="badge ${badge.className}">${escapeHtml(badge.label)}</span>
      <span class="cell-caption">${escapeHtml(value || "Not reported")}</span>
    </div>
  `;
}

function renderQualityCell(row) {
  const value = text(row.row_quality_flag).trim();
  const badge = getQualityBadge(row);
  const caption = value || "blank quality flag";
  return `
    <div class="cell-stack">
      <span class="badge ${badge.className}">${escapeHtml(badge.label)}</span>
      <span class="cell-caption">${escapeHtml(caption)}</span>
    </div>
  `;
}

function getEvidenceBadge(row) {
  const evidence = normalizeSearch(row.evidence_status);

  if (row.__preliminary) {
    return { label: "Preliminary", className: "badge-evidence-preliminary" };
  }

  if (evidence.includes("review scope row")) {
    return { label: "Scope row", className: "badge-evidence-scope" };
  }

  if (evidence.includes("supplementary") || evidence.includes("additional locus")) {
    return { label: "Supplement", className: "badge-evidence-supplement" };
  }

  if (evidence.includes("gwas")) {
    return { label: "GWAS", className: "badge-evidence-gwas" };
  }

  if (evidence.includes("review")) {
    return { label: "Review reported", className: "badge-evidence-review" };
  }

  return { label: "Reported", className: "badge-evidence-reported" };
}

function getQualityBadge(row) {
  const flag = text(row.row_quality_flag).trim();
  const normalized = normalizeSearch(flag);

  if (!flag) {
    return { label: "Blank flag", className: "badge-quality-blank" };
  }

  if (normalized.includes("manual_preliminary_grey_literature_entry")) {
    return { label: "Manual entry", className: "badge-quality-manual" };
  }

  if (normalized.includes("sparse_or_continuation") || normalized.includes("multi_line_extraction")) {
    return { label: "Needs review", className: "badge-quality-review" };
  }

  if (normalized.includes("ok_docx_supplement_extract")) {
    return { label: "Supplement extract", className: "badge-quality-supplement" };
  }

  if (normalized.includes("ok_extracted")) {
    return { label: "OK extracted", className: "badge-quality-ok" };
  }

  return { label: "Flagged", className: "badge-quality-manual" };
}

function openDetail(rowIndex) {
  const row = state.rows.find(candidate => candidate.__index === rowIndex);
  if (!row) {
    return;
  }

  state.selectedRowIndex = rowIndex;
  elements.detailContent.innerHTML = renderDetail(row);
  elements.detailPanel.classList.add("open");
  elements.drawerBackdrop.hidden = false;
  document.body.classList.add("drawer-open");
  renderTable();
}

function closeDetail() {
  state.selectedRowIndex = null;
  elements.detailPanel.classList.remove("open");
  elements.drawerBackdrop.hidden = true;
  document.body.classList.remove("drawer-open");
  renderTable();
}

function renderDetail(row) {
  const title = text(row.locus_or_allele).trim() || text(row.disease_or_pest).trim() || text(row.entry_id).trim();
  const sourceReference = text(row.source_reference).trim();
  const metaParts = [
    row.entry_id,
    row.disease_or_pest,
    sourceReference
  ].map(value => text(value).trim()).filter(Boolean);

  const callouts = [];

  if (row.__manualReview) {
    callouts.push(`
      <div class="callout callout-warning">
        <strong>Manual validation recommended</strong>
        This row is flagged by row_quality_flag and should be reviewed alongside raw_row_text and source_col_01 through source_col_14.
      </div>
    `);
  }

  if (row.__preliminary) {
    callouts.push(`
      <div class="callout callout-info">
        <strong>Preliminary evidence retained</strong>
        This row remains visible by design even though the evidence status indicates preliminary or grey-literature support.
      </div>
    `);
  }

  return `
    <section class="detail-hero">
      <div class="detail-badge-row">
        <span class="badge badge-group">${escapeHtml(text(row.target_group).trim() || "Not reported")}</span>
        <span class="badge ${getEvidenceBadge(row).className}">${escapeHtml(getEvidenceBadge(row).label)}</span>
        <span class="badge ${getQualityBadge(row).className}">${escapeHtml(getQualityBadge(row).label)}</span>
        <span class="badge badge-group">${escapeHtml(text(row.source_category).trim() || "Not reported")}</span>
      </div>
      <h2 class="detail-title">${escapeHtml(title)}</h2>
      <div class="detail-meta">${escapeHtml(metaParts.join(" | "))}</div>
      ${callouts.length ? `<div class="callout-stack">${callouts.join("")}</div>` : ""}
      ${renderPrrDetail(row)}
      <div class="detail-highlight-grid">
        ${DETAIL_HIGHLIGHT_FIELDS.map(field => `
          <div class="detail-highlight-card">
            <strong>${escapeHtml(humanizeField(field))}</strong>
            <span>${renderDetailValue(field, row[field])}</span>
          </div>
        `).join("")}
      </div>
      <div class="record-grid">
        ${state.fieldOrder.map(field => `
          <div class="record-row ${IMPORTANT_FIELDS.has(field) ? "is-important" : ""}">
            <div class="record-key" title="${escapeHtml(state.fieldDescriptions[field] || humanizeField(field))}">
              ${escapeHtml(humanizeField(field))}
            </div>
            <div class="record-value">${renderDetailValue(field, row[field])}</div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function renderPrrDetail(row) {
  const selectedFamily = elements.prrFamilyFilter.value;
  const hits = getPrrHits(row, selectedFamily);
  if (hits.length === 0) {
    return "";
  }
  return `
    <section class="prr-detail-section">
      <div class="prr-detail-heading">
        <div>
          <p class="panel-kicker">Assembly-aware candidate genes</p>
          <h3>PRR hits at ${escapeHtml(getPrrDistanceLabel().toLowerCase())}</h3>
        </div>
        <span class="meta-chip">${escapeHtml(formatCount(hits.length))} QTL–gene pairs</span>
      </div>
      <div class="prr-detail-list">
        ${hits.map(hit => {
          const catalog = state.prrByGene.get(hit.gene_id_a6);
          const a6 = catalog?.assembly_calls?.a6;
          return `
            <article class="prr-detail-card">
              <div class="prr-detail-card-heading">
                <span class="prr-hit prr-${escapeHtml(hit.family.toLowerCase())}"><strong>${escapeHtml(hit.family)}</strong></span>
                <strong>${escapeHtml(hit.gene_id_a6)}</strong>
              </div>
              <dl>
                <div><dt>Relationship</dt><dd>${escapeHtml(formatPrrRelationship(hit))}</dd></div>
                <div><dt>Reported QTL coordinate</dt><dd>${escapeHtml(hit.source_coordinate)}</dd></div>
                <div><dt>Mapped a2 call</dt><dd>${escapeHtml(hit.mapped_a2_gene_id)} · Chr ${escapeHtml(hit.chromosome)}:${escapeHtml(formatCount(hit.gene_start))}–${escapeHtml(formatCount(hit.gene_end))}</dd></div>
                <div><dt>a6 call</dt><dd>${a6 ? `Chr ${escapeHtml(a6.chromosome)}:${escapeHtml(formatCount(a6.start))}–${escapeHtml(formatCount(a6.end))}` : "Not available"}</dd></div>
                <div><dt>Mapping</dt><dd>${escapeHtml(humanizeField(hit.a2_mapping_method))}</dd></div>
              </dl>
            </article>
          `;
        }).join("")}
      </div>
    </section>
  `;
}

function renderDetailValue(field, value) {
  const cleanValue = text(value).trim();

  if (!cleanValue) {
    return '<span class="empty-value">Not reported</span>';
  }

  if (field === "source_url_or_doi" && cleanValue.startsWith("http")) {
    return `<a class="detail-link" href="${escapeHtml(cleanValue)}" target="_blank" rel="noreferrer">${escapeHtml(cleanValue)}</a>`;
  }

  return escapeHtml(cleanValue);
}

function downloadVisibleCsv() {
  const csv = toCsv(state.visibleRows);
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "soybean_resistance_qtl_filtered_rows.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

function toCsv(rows) {
  const derivedFields = state.prrCatalog.length
    ? ["prr_hit_families", "prr_hit_genes_a6", "prr_hit_details"]
    : [];
  const fields = [...state.fieldOrder, ...derivedFields];
  const lines = [
    fields.join(","),
    ...rows.map(row => fields.map(field => csvEscape(getCsvValue(row, field))).join(","))
  ];
  return lines.join("\n");
}

function getCsvValue(row, field) {
  if (!field.startsWith("prr_hit_")) {
    return row[field];
  }
  const hits = getPrrHits(row, elements.prrFamilyFilter.value);
  if (field === "prr_hit_families") {
    return [...new Set(hits.map(hit => hit.family))].join("; ");
  }
  if (field === "prr_hit_genes_a6") {
    return hits.map(hit => hit.gene_id_a6).join("; ");
  }
  return hits.map(hit => `${hit.gene_id_a6} (${formatPrrRelationship(hit)})`).join("; ");
}

function csvEscape(value) {
  return `"${text(value).replace(/"/g, '""')}"`;
}

function resetFilters() {
  elements.searchInput.value = "";

  for (const { id } of FILTER_CONFIG) {
    elements[id].value = "";
  }
  elements.prrFamilyFilter.value = "";
  elements.prrDistanceFilter.value = "0";

  state.sort = { ...DEFAULT_SORT };
  closeDetail();
  refreshView();
}

function updateUrlState() {
  const params = new URLSearchParams();
  const query = elements.searchInput.value.trim();

  if (query) {
    params.set("q", query);
  }

  for (const { field, id } of FILTER_CONFIG) {
    const value = elements[id].value;
    if (value) {
      params.set(field, value);
    }
  }

  if (elements.prrFamilyFilter.value) {
    params.set("prr_family", elements.prrFamilyFilter.value);
  }
  if (elements.prrDistanceFilter.value !== "0") {
    params.set("prr_distance", elements.prrDistanceFilter.value);
  }

  if (state.sort.field !== DEFAULT_SORT.field || state.sort.direction !== DEFAULT_SORT.direction) {
    params.set("sort", state.sort.field);
    params.set("dir", state.sort.direction);
  }

  const nextUrl = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname;

  // Some browsers restrict History API writes for local files. URL state is a
  // convenience, so a file:// restriction should never interrupt the browser.
  try {
    window.history.replaceState(null, "", nextUrl);
  } catch (error) {
    if (window.location.protocol !== "file:") {
      throw error;
    }
  }
}

function getCountEntries(rows, field, options = {}) {
  const {
    limit = Infinity,
    includeBlank = false,
    sortByCount = true
  } = options;

  const counts = new Map();

  for (const row of rows) {
    const value = text(row[field]).trim();
    if (!value && !includeBlank) {
      continue;
    }
    const key = value || "";
    counts.set(key, (counts.get(key) || 0) + 1);
  }

  const entries = [...counts.entries()].map(([value, count]) => ({ value, count }));
  entries.sort((left, right) => {
    if (sortByCount && left.count !== right.count) {
      return right.count - left.count;
    }
    return compareValues(left.value, right.value);
  });

  return entries.slice(0, limit);
}

function countDistinct(rows, field) {
  return new Set(
    rows
      .map(row => text(row[field]).trim())
      .filter(Boolean)
  ).size;
}

function compareValues(left, right) {
  const leftText = text(left).trim();
  const rightText = text(right).trim();

  if (!leftText && !rightText) {
    return 0;
  }

  if (!leftText) {
    return 1;
  }

  if (!rightText) {
    return -1;
  }

  return leftText.localeCompare(rightText, undefined, {
    numeric: true,
    sensitivity: "base"
  });
}

function hasActiveCriteria() {
  if (elements.searchInput.value.trim()) {
    return true;
  }

  return (
    FILTER_CONFIG.some(({ id }) => elements[id].value) ||
    Boolean(elements.prrFamilyFilter.value)
  );
}

function isManualReview(row) {
  const flag = normalizeSearch(row.row_quality_flag);
  return (
    !flag ||
    flag.includes("sparse_or_continuation") ||
    flag.includes("multi_line_extraction") ||
    flag.includes("manual_preliminary_grey_literature_entry")
  );
}

function isPreliminary(row) {
  const evidence = normalizeSearch(row.evidence_status);
  return (
    evidence.includes("preliminary") ||
    evidence.includes("grey literature") ||
    evidence.includes("needs primary publication")
  );
}

function normalizeSearch(value) {
  return text(value).toLowerCase();
}

function humanizeField(field) {
  return text(field).replace(/_/g, " ");
}

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function escapeHtml(value) {
  return text(value).replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

function text(value) {
  return value == null ? "" : String(value);
}

function handleInitError(error) {
  document.body.innerHTML = `
    <main class="page-shell">
      <section class="panel">
        <p class="panel-kicker">Browser error</p>
        <h1>Could not load the soybean browser</h1>
        <p class="subtitle">
          Open <code>soybean_qtl_browser.html</code> for the self-contained
          version, or serve this repository when using the source files.
        </p>
        <p>${escapeHtml(error.message)}</p>
      </section>
    </main>
  `;
}
