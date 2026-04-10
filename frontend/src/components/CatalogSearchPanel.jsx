import React, { useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";

import {
  autocompleteCatalog,
  getCatalogItemDetail,
  listRequirements,
} from "../api/catalogClient";
import { api } from "../api/client";
import { useApp } from "../context/AppContext";

const PAGE_SIZE = 5;
const REQUIREMENTS_PAGE_LIMIT = 200;
const TOP_SEARCH_STORAGE_KEY = "aigov.topRequirementSearches";
const DEFAULT_TOP_SEARCHES = [
  "human oversight",
  "transparency",
  "incident response",
  "data quality",
  "risk assessment",
];
const GOVERNANCE_CATEGORIES = [
  "Corporate Oversight",
  "Risk & Compliance",
  "Technical Architecture",
  "Data Readiness",
  "Data Integration",
  "Security",
  "Infrastructure",
  "Solution Design",
  "System Performance",
];

const STEP_BY_CATEGORY = {
  "Corporate Oversight": 1,
  "Risk & Compliance": 2,
  "Technical Architecture": 3,
  "Data Readiness": 4,
  "Data Integration": 5,
  Security: 6,
  Infrastructure: 7,
  "Solution Design": 8,
  "System Performance": 9,
};

function uniqueValues(items, key) {
  return Array.from(
    new Set(
      (items || [])
        .map((item) => String(item?.[key] ?? "").trim())
        .filter(Boolean),
    ),
  ).sort((a, b) => a.localeCompare(b));
}

function normalizeText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function readStoredTopSearches() {
  if (typeof window === "undefined") return DEFAULT_TOP_SEARCHES;
  try {
    const raw = window.localStorage.getItem(TOP_SEARCH_STORAGE_KEY);
    if (!raw) return DEFAULT_TOP_SEARCHES;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DEFAULT_TOP_SEARCHES;
    const cleaned = parsed
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .slice(0, 5);
    return cleaned.length > 0 ? cleaned : DEFAULT_TOP_SEARCHES;
  } catch {
    return DEFAULT_TOP_SEARCHES;
  }
}

function writeStoredTopSearches(items) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOP_SEARCH_STORAGE_KEY, JSON.stringify(items));
  } catch {
    // Ignore localStorage failures.
  }
}

function humanizeMetricName(metricName) {
  if (!metricName) return "No metric bound";
  return metricName
    .replace(/^ai\./i, "")
    .replace(/[._]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatMetricValue(value, threshold) {
  if (typeof value !== "number" || Number.isNaN(value)) return "No live value";
  const unit = String(threshold?.unit || "").trim();
  if (unit === "%") return `${Math.round(value)}%`;
  if (unit === "ratio") return `${Number(value.toFixed(3))}`;
  if (unit === "score") return `${Number(value.toFixed(3))}`;
  if (unit) return `${Number(value.toFixed(3))} ${unit}`;
  return `${Number(value.toFixed(3))}`;
}

function formulaToPlainEnglish(metricName, threshold) {
  const formula = String(threshold?.formula || "").trim();
  const period = String(threshold?.delta_period || "").trim();
  if (formula) {
    return `Calculated using formula \"${formula}\"${period ? ` over ${period}` : ""}.`;
  }
  return `Calculated from telemetry metric ${metricName || "selected metric"}${period ? ` over ${period}` : ""}.`;
}

function makeLegendIcon(label) {
  return (
    <span
      title={label}
      style={{
        width: 16,
        height: 16,
        borderRadius: "50%",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        border: "1px solid var(--border)",
        color: "var(--text-tertiary)",
        fontSize: 10,
        cursor: "help",
      }}
    >
      i
    </span>
  );
}

function FilterGlyph({ type, title }) {
  if (type === "search") {
    return (
      <span className="catalog-filter-icon" title={title}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      </span>
    );
  }
  if (type === "sort") {
    return (
      <span className="catalog-filter-icon" title={title}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M8 6h11" />
          <path d="M8 12h8" />
          <path d="M8 18h5" />
          <path d="m3 8 2-2 2 2" />
          <path d="M5 6v12" />
        </svg>
      </span>
    );
  }
  if (type === "jurisdiction") {
    return (
      <span className="catalog-filter-icon" title={title}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18" />
          <path d="M12 3a14 14 0 0 1 0 18" />
          <path d="M12 3a14 14 0 0 0 0 18" />
        </svg>
      </span>
    );
  }
  if (type === "category") {
    return (
      <span className="catalog-filter-icon" title={title}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="4" y="4" width="16" height="6" rx="1.5" />
          <rect x="4" y="14" width="16" height="6" rx="1.5" />
        </svg>
      </span>
    );
  }
  return (
    <span className="catalog-filter-icon" title={title}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M8 3.5h7l4 4V20a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1z" />
        <path d="M15 3.5V8h4" />
      </svg>
    </span>
  );
}
FilterGlyph.propTypes = {
  type: PropTypes.string.isRequired,
  title: PropTypes.string,
};

function CatalogSearchPanel() {
  const { selectedApp, currentUser } = useApp();

  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [sortBy, setSortBy] = useState("code");
  const [jurisdictionFilter, setJurisdictionFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [regulationFilter, setRegulationFilter] = useState("");

  const [topSearches, setTopSearches] = useState(() => readStoredTopSearches());
  const [suggestions, setSuggestions] = useState([]);

  const [allRequirements, setAllRequirements] = useState([]);
  const [loadingRequirements, setLoadingRequirements] = useState(false);
  const [requirementsError, setRequirementsError] = useState("");

  const [page, setPage] = useState(1);
  const [selectedItem, setSelectedItem] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");

  const [showInterpretForm, setShowInterpretForm] = useState(false);
  const [interpretAppId, setInterpretAppId] = useState(selectedApp?.id || "");
  const [interpretText, setInterpretText] = useState("");
  const [savingInterpretation, setSavingInterpretation] = useState(false);
  const [interpretError, setInterpretError] = useState("");
  const [interpretNotice, setInterpretNotice] = useState("");
  const [connectedApps, setConnectedApps] = useState([]);

  const queryTrimmed = useMemo(() => query.trim(), [query]);

  useEffect(() => {
    let active = true;

    async function loadAllRequirements() {
      setLoadingRequirements(true);
      setRequirementsError("");
      try {
        let skip = 0;
        let total = Infinity;
        const merged = [];

        while (merged.length < total) {
          const response = await listRequirements({
            skip,
            limit: REQUIREMENTS_PAGE_LIMIT,
          });
          const items = Array.isArray(response?.items) ? response.items : [];
          total = Number(response?.total ?? items.length);
          merged.push(...items);
          if (items.length === 0) break;
          skip += items.length;
        }

        if (active) setAllRequirements(merged);
      } catch (err) {
        if (active) {
          const detail = err?.response?.data?.detail;
          setRequirementsError(
            typeof detail === "string" ? detail : "Failed to load requirements",
          );
        }
      } finally {
        if (active) setLoadingRequirements(false);
      }
    }

    loadAllRequirements();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    async function loadSuggestions() {
      if (!queryTrimmed) {
        setSuggestions([]);
        return;
      }

      try {
        const response = await autocompleteCatalog({
          q: queryTrimmed,
          type: "requirement",
          limit: 6,
        });
        if (active) setSuggestions(response.items ?? []);
      } catch {
        if (active) setSuggestions([]);
      }
    }

    const id = setTimeout(loadSuggestions, 180);
    return () => {
      active = false;
      clearTimeout(id);
    };
  }, [queryTrimmed]);

  const jurisdictions = useMemo(
    () => uniqueValues(allRequirements, "jurisdiction"),
    [allRequirements],
  );
  const categories = GOVERNANCE_CATEGORIES;
  const regulations = useMemo(
    () => uniqueValues(allRequirements, "regulation_title"),
    [allRequirements],
  );

  const filteredResults = useMemo(() => {
    const q = activeQuery.toLowerCase();
    const rows = allRequirements.filter((item) => {
      if (q) {
        const haystack = [
          item.code,
          item.title,
          item.description,
          item.regulation_title,
          item.jurisdiction,
          item.category,
        ]
          .map((value) => String(value || "").toLowerCase())
          .join(" ");
        if (!haystack.includes(q)) return false;
      }

      if (jurisdictionFilter && item.jurisdiction !== jurisdictionFilter) return false;
      if (categoryFilter && item.category !== categoryFilter) return false;
      if (regulationFilter && item.regulation_title !== regulationFilter) return false;

      return true;
    });

    return rows.sort((a, b) => {
      if (sortBy === "title") return (a.title || "").localeCompare(b.title || "");
      if (sortBy === "jurisdiction") {
        return (a.jurisdiction || "").localeCompare(b.jurisdiction || "");
      }
      if (sortBy === "regulation") {
        return (a.regulation_title || "").localeCompare(b.regulation_title || "");
      }
      return (a.code || "").localeCompare(b.code || "");
    });
  }, [
    activeQuery,
    allRequirements,
    jurisdictionFilter,
    categoryFilter,
    regulationFilter,
    sortBy,
  ]);

  useEffect(() => {
    setPage(1);
    setSelectedItem(null);
    setSelectedDetail(null);
    setSelectedRecord(null);
    setDetailError("");
    setShowInterpretForm(false);
    setInterpretText("");
    setInterpretError("");
    setInterpretNotice("");
  }, [activeQuery, jurisdictionFilter, categoryFilter, regulationFilter, sortBy]);

  function pushTopSearch(term) {
    const cleanTerm = String(term || "").trim();
    if (!cleanTerm) return;
    const next = [cleanTerm, ...topSearches.filter((entry) => entry.toLowerCase() !== cleanTerm.toLowerCase())]
      .slice(0, 5);
    setTopSearches(next);
    writeStoredTopSearches(next);
  }

  useEffect(() => {
    let active = true;

    async function loadApps() {
      try {
        const apps = await api.listApplications();
        if (!active) return;
        const activeApps = Array.isArray(apps)
          ? apps.filter((app) => app.status === "active")
          : [];
        setConnectedApps(activeApps);
        setInterpretAppId((prev) => {
          if (prev) return prev;
          if (selectedApp?.id) return selectedApp.id;
          return activeApps[0]?.id || "";
        });
      } catch {
        if (active) setConnectedApps([]);
      }
    }

    loadApps();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedApp?.id) return;
    setInterpretAppId((prev) => {
      if (prev && connectedApps.some((app) => app.id === prev)) return prev;
      return selectedApp.id;
    });
  }, [selectedApp?.id, connectedApps]);

  function runSearch(event) {
    event.preventDefault();
    setActiveQuery(queryTrimmed);
    if (queryTrimmed) pushTopSearch(queryTrimmed);
  }

  function clearSearchAndFilters() {
    setQuery("");
    setActiveQuery("");
    setJurisdictionFilter("");
    setCategoryFilter("");
    setRegulationFilter("");
    setSortBy("code");
  }

  function applySuggestion(suggestion) {
    const label = suggestion?.label || "";
    setQuery(label);
    setActiveQuery(label);
    if (label) pushTopSearch(label);
  }

  function applyTopSearch(term) {
    setQuery(term);
    setActiveQuery(term);
    pushTopSearch(term);
  }

  function pickScopeItem(scopeItems, item, detail) {
    if (!Array.isArray(scopeItems) || scopeItems.length === 0) return null;
    return (
      scopeItems.find((entry) => entry.requirement_id === item?.id)
      || scopeItems.find((entry) => entry.code === detail?.code)
      || null
    );
  }

  async function loadScopeItemForApp(appId, item, detail) {
    if (!appId || !item?.id) return null;

    const terms = [detail?.code, item?.code, detail?.title, item?.title]
      .map((value) => String(value || "").trim())
      .filter(Boolean);

    for (const term of terms) {
      const requirementScope = await api.getApplicationRequirements(
        appId,
        `q=${encodeURIComponent(term)}&limit=200`,
      );
      const scopeItems = Array.isArray(requirementScope?.items) ? requirementScope.items : [];
      const matched = pickScopeItem(scopeItems, item, detail);
      if (matched) return matched;
    }

    const fallbackScope = await api.getApplicationRequirements(appId, "limit=200");
    const fallbackItems = Array.isArray(fallbackScope?.items) ? fallbackScope.items : [];
    return pickScopeItem(fallbackItems, item, detail);
  }

  async function selectResult(item) {
    setSelectedItem(item);
    setSelectedDetail(null);
    setSelectedRecord(null);
    setDetailError("");
    setInterpretNotice("");
    setInterpretError("");
    setShowInterpretForm(false);
    setInterpretText("");

    if (!item?.id) {
      setDetailError("Selected result does not have a resolvable id");
      return;
    }

    setLoadingDetail(true);
    try {
      const detail = await getCatalogItemDetail({ ...item, type: "requirement" });
      setSelectedDetail(detail);

      let scopeItem = null;
      let measureRows = [];
      const appIdForContext = interpretAppId || selectedApp?.id;
      if (appIdForContext) {
        scopeItem = await loadScopeItemForApp(appIdForContext, item, detail);

        const category = scopeItem?.category || detail?.category || item?.category;
        const step = STEP_BY_CATEGORY[category];
        if (step) {
          const dashboardStep = await api.getApplicationDashboardStep(appIdForContext, step);
          const rows = Array.isArray(dashboardStep?.rows) ? dashboardStep.rows : [];
          measureRows = rows.filter((row) => row?.requirement_id === item.id);
        }
      }

      const normalizedTitle = normalizeText(detail?.title || item?.title);
      const relatedRows = allRequirements.filter(
        (row) => normalizeText(row?.title) === normalizedTitle,
      );

      const regulationSet = new Set(
        [
          detail?.regulation_title,
          ...relatedRows.map((row) => row?.regulation_title),
        ]
          .map((value) => String(value || "").trim())
          .filter(Boolean),
      );
      const jurisdictionSet = new Set(
        [
          detail?.jurisdiction,
          ...relatedRows.map((row) => row?.jurisdiction),
        ]
          .map((value) => String(value || "").trim())
          .filter(Boolean),
      );

      const controls = Array.isArray(scopeItem?.linked_controls)
        ? scopeItem.linked_controls.filter((control) => Boolean(control?.id))
        : [];

      setSelectedRecord({
        controls,
        measureRows,
        regulations: Array.from(regulationSet).sort((a, b) => a.localeCompare(b)),
        jurisdictions: Array.from(jurisdictionSet).sort((a, b) => a.localeCompare(b)),
      });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setDetailError(typeof detail === "string" ? detail : err?.message || "Failed to load detail");
    } finally {
      setLoadingDetail(false);
    }
  }

  async function saveInterpretation(event) {
    event.preventDefault();
    setInterpretError("");
    setInterpretNotice("");

    const targetAppId = interpretAppId || selectedApp?.id;
    if (!targetAppId) {
      setInterpretError("Select a connected application first to create interpretation.");
      return;
    }
    if (!selectedItem?.id) {
      setInterpretError("Select a requirement first.");
      return;
    }
    let linkedControls = (selectedRecord?.controls || []).filter((control) => Boolean(control?.id));
    if (!linkedControls.length && selectedItem?.id) {
      try {
        const scopeItem = await loadScopeItemForApp(targetAppId, selectedItem, selectedDetail);
        const resolved = Array.isArray(scopeItem?.linked_controls)
          ? scopeItem.linked_controls.filter((control) => Boolean(control?.id))
          : [];
        if (resolved.length) {
          linkedControls = resolved;
          setSelectedRecord((prev) => (
            prev
              ? { ...prev, controls: resolved }
              : {
                controls: resolved,
                measureRows: [],
                regulations: [],
                jurisdictions: [],
              }
          ));
        }
      } catch {
        // Keep the original validation message if fallback lookup fails.
      }
    }
    if (!linkedControls.length) {
      setInterpretError("This requirement has no linked controls, so interpretation cannot be applied.");
      return;
    }
    if (!interpretText.trim()) {
      setInterpretError("Interpretation text is required.");
      return;
    }

    setSavingInterpretation(true);
    try {
      const payloadBase = {
        requirement_id: selectedItem.id,
        interpretation_text: interpretText.trim(),
        set_by: currentUser?.email || "application_owner",
      };

      const writes = await Promise.allSettled(
        linkedControls.map((control) => api.createApplicationInterpretation(targetAppId, {
          ...payloadBase,
          control_id: control.id,
        })),
      );

      const failed = writes.filter((result) => result.status === "rejected");
      if (failed.length > 0) {
        setInterpretError(`Interpretation saved partially (${linkedControls.length - failed.length}/${linkedControls.length} controls).`);
      } else {
        setInterpretNotice(`Interpretation saved across ${linkedControls.length} linked control(s) for this requirement.`);
      }
      setShowInterpretForm(false);
      setInterpretText("");
    } catch (err) {
      setInterpretError(err?.message || "Failed to create interpretation");
    } finally {
      setSavingInterpretation(false);
    }
  }

  const total = filteredResults.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE;
  const pageEnd = Math.min(pageStart + PAGE_SIZE, total);
  const pageItems = filteredResults.slice(pageStart, pageEnd);

  const fallbackMeasureRows = useMemo(() => {
    if (!selectedRecord) return [];
    if (selectedRecord.measureRows.length > 0) return selectedRecord.measureRows;

    return selectedRecord.controls.map((control) => ({
      control_id: control.id,
      control_code: control.code,
      control_title: control.title,
      metric_name: control.metric_name,
      value: null,
      result: "NO_DATA",
      threshold: control.default_threshold,
      interpretation_text: "No live value for this app in the current time window.",
    }));
  }, [selectedRecord]);

  const canCreateInterpretation = Boolean(selectedItem?.id);
  const canSaveInterpretation = Boolean(selectedItem?.id && interpretAppId);
  const hasConnectedApps = connectedApps.length > 0;

  return (
    <section className="card catalog-panel">
      <div className="catalog-header-row">
        <h2 className="card-title" style={{ marginBottom: 0, borderBottom: "none", paddingBottom: 0 }}>
          Governance Requirements
        </h2>
        <span className="chip">{allRequirements.length} total</span>
      </div>
      <p className="section-copy" style={{ marginTop: "0.45rem" }}>
        Browse and search the full regulatory requirements database with compact filters.
      </p>

      <div className="catalog-top-searches">
        <span className="catalog-top-searches-label">Top 5 searches</span>
        {topSearches.map((term) => (
          <button
            key={term}
            type="button"
            className="suggestion-pill"
            onClick={() => applyTopSearch(term)}
          >
            {term}
          </button>
        ))}
      </div>
      <form onSubmit={runSearch} className="catalog-filter-inline">
        <label className="catalog-filter-field" title="Search by requirement title, code, regulation, or jurisdiction.">
          <FilterGlyph type="search" title="Search" />
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search requirements"
            className="query-input catalog-filter-input"
          />
        </label>

        <label className="catalog-filter-field" title="Sort result order.">
          <FilterGlyph type="sort" title="Sort" />
          <select
            className="query-input catalog-filter-input"
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value)}
          >
            <option value="code">Code</option>
            <option value="title">Title</option>
            <option value="regulation">Regulation</option>
            <option value="jurisdiction">Jurisdiction</option>
          </select>
        </label>

        <label className="catalog-filter-field" title="Filter by jurisdiction.">
          <FilterGlyph type="jurisdiction" title="Jurisdiction" />
          <select
            className="query-input catalog-filter-input"
            value={jurisdictionFilter}
            onChange={(event) => setJurisdictionFilter(event.target.value)}
          >
            <option value="">Jurisdiction</option>
            {jurisdictions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>

        <label className="catalog-filter-field" title="Filter by governance category.">
          <FilterGlyph type="category" title="Category" />
          <select
            className="query-input catalog-filter-input"
            value={categoryFilter}
            onChange={(event) => setCategoryFilter(event.target.value)}
          >
            <option value="">Category</option>
            {categories.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>

        <label className="catalog-filter-field" title="Filter by regulation title.">
          <FilterGlyph type="regulation" title="Regulation" />
          <select
            className="query-input catalog-filter-input"
            value={regulationFilter}
            onChange={(event) => setRegulationFilter(event.target.value)}
          >
            <option value="">Regulation</option>
            {regulations.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>

        <button type="submit" className="btn-primary catalog-btn-primary" disabled={loadingRequirements} title="Apply search and filters">
          Apply
        </button>
        <button
          type="button"
          className="btn-secondary catalog-btn-secondary"
          onClick={clearSearchAndFilters}
          disabled={loadingRequirements}
          title="Reset all search filters"
        >
          Reset
        </button>
      </form>

      {suggestions.length > 0 ? (
        <div className="suggestions-wrap">
          {suggestions.map((item) => (
            <button
              key={`${item.id}-${item.label}`}
              type="button"
              className="suggestion-pill"
              onClick={() => applySuggestion(item)}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}

      {requirementsError ? <p className="error-text">{requirementsError}</p> : null}

      <div className="pagination-row" style={{ marginTop: "0.4rem" }}>
        <p className="pagination-meta">
          {loadingRequirements
            ? "Loading requirements..."
            : `Showing ${pageStart + 1}-${pageEnd} of ${total}`}
        </p>
        <div className="pagination-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setPage((prev) => Math.max(1, prev - 1))}
            disabled={safePage <= 1 || loadingRequirements}
          >
            Prev
          </button>
          <span className="chip">Page {safePage} / {pageCount}</span>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setPage((prev) => Math.min(pageCount, prev + 1))}
            disabled={safePage >= pageCount || loadingRequirements}
          >
            Next
          </button>
        </div>
      </div>

      {pageItems.length > 0 ? (
        <div className="catalog-list-wrap">
          <div className="catalog-section-header">
            <span>Requirement List</span>
            <span className="catalog-section-meta">Select a row to open full detail</span>
          </div>
          <ul className="tree-list">
            {pageItems.map((item) => (
              <li key={item.id} className="tree-item search-item">
                <button
                  type="button"
                  className={`search-select-btn catalog-result-btn${selectedItem?.id === item.id ? " active" : ""}`}
                  onClick={() => selectResult(item)}
                >
                  <span className="search-main">
                    <strong>{item.code || item.id}</strong>
                    <span>{item.title || "Untitled"}</span>
                    <span className="catalog-meta-chips">
                      {item.category ? <span className="chip chip-soft">{item.category}</span> : null}
                      {item.regulation_title ? <span className="chip chip-soft">{item.regulation_title}</span> : null}
                      {item.jurisdiction ? <span className="chip chip-soft">{item.jurisdiction}</span> : null}
                    </span>
                  </span>
                  <span className="catalog-view-link" title="Open detailed requirement record">View</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        !loadingRequirements && <p className="section-copy">No matching requirements found.</p>
      )}

      {selectedItem ? (
        <div className="detail-drawer catalog-detail-drawer catalog-animate-enter">
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.7rem", alignItems: "center", marginBottom: "0.45rem" }}>
            <p className="section-copy" style={{ marginBottom: 0 }}>
              Detail: <strong>{selectedItem.code || selectedItem.id}</strong>
            </p>
            <button
              type="button"
              className="btn-primary catalog-action-btn"
              title="Create an app-specific interpretation for this existing requirement. KPI binding and governance category remain inherited from the existing requirement/control."
              disabled={!canCreateInterpretation || !hasConnectedApps}
              onClick={() => {
                setShowInterpretForm((prev) => !prev);
                setInterpretError("");
                setInterpretNotice("");
              }}
              
            >
              Create Interpretation
            </button>
          </div>

          {!hasConnectedApps ? (
            <p className="section-copy" style={{ marginBottom: "0.45rem" }}>
              No connected applications available. Connect an application to enable interpretation actions.
            </p>
          ) : !interpretAppId ? (
            <p className="section-copy" style={{ marginBottom: "0.45rem" }}>
              Select a connected application to enable interpretation actions and live KPI values.
            </p>
          ) : null}

          {loadingDetail ? <p className="section-copy">Loading detail...</p> : null}
          {detailError ? <p className="error-text">{detailError}</p> : null}

          {!loadingDetail && !detailError && selectedDetail ? (
            <>
              <div className="detail-grid" style={{ marginBottom: "0.7rem" }}>
                <div className="detail-row">
                  <span className="detail-label">Title</span>
                  <span className="detail-value">{selectedDetail.title}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Governance Category</span>
                  <span className="detail-value">{selectedDetail.category || "Unassigned"}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Description</span>
                  <span className="detail-value">{selectedDetail.description || "No description"}</span>
                </div>
              </div>

              <div style={{ marginBottom: "0.7rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.35rem", fontSize: "0.75rem", color: "var(--text-tertiary)", fontWeight: 600 }}>
                  Regulations {makeLegendIcon("All regulation references currently linked to this requirement text in the catalog.")}
                </div>
                <div className="suggestions-wrap" style={{ marginBottom: "0.25rem" }}>
                  {(selectedRecord?.regulations || []).length ? (
                    selectedRecord.regulations.map((name) => <span key={name} className="chip">{name}</span>)
                  ) : (
                    <span className="section-copy" style={{ marginBottom: 0 }}>No regulation links found.</span>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: "0.7rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.35rem", fontSize: "0.75rem", color: "var(--text-tertiary)", fontWeight: 600 }}>
                  Jurisdictions {makeLegendIcon("All jurisdictions currently linked to regulation references for this requirement.")}
                </div>
                <div className="suggestions-wrap" style={{ marginBottom: "0.25rem" }}>
                  {(selectedRecord?.jurisdictions || []).length ? (
                    selectedRecord.jurisdictions.map((name) => <span key={name} className="chip">{name}</span>)
                  ) : (
                    <span className="section-copy" style={{ marginBottom: 0 }}>No jurisdiction links found.</span>
                  )}
                </div>
              </div>

              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.35rem", fontSize: "0.75rem", color: "var(--text-tertiary)", fontWeight: 600 }}>
                  Controls, Measures, Values, and Formula {makeLegendIcon("Complete requirement record in app context: linked controls, KPI measure, current value, and formula in plain English.")}
                </div>

                {fallbackMeasureRows.length ? (
                  <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
                    {fallbackMeasureRows.map((row, index) => (
                      <div
                        key={`${row.control_id || "ctrl"}-${row.metric_name || "metric"}-${index}`}
                        style={{
                          padding: "0.55rem 0.65rem",
                          borderTop: index === 0 ? "none" : "1px solid var(--surface-3)",
                          background: "var(--surface)",
                        }}
                      >
                        <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text-primary)" }}>
                          {row.control_code || "Control"} - {row.control_title || "Untitled control"}
                        </div>
                        <div style={{ marginTop: 2, fontSize: "0.76rem", color: "var(--text-secondary)" }}>
                          Measure: {humanizeMetricName(row.metric_name)}
                        </div>
                        <div style={{ marginTop: 2, fontSize: "0.76rem", color: "var(--text-secondary)" }}>
                          Value: {formatMetricValue(row.value, row.threshold)}
                          {row.result ? ` (${row.result})` : ""}
                        </div>
                        <div style={{ marginTop: 2, fontSize: "0.76rem", color: "var(--text-secondary)" }}>
                          Formula: {formulaToPlainEnglish(row.metric_name, row.threshold)}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="section-copy" style={{ marginBottom: 0 }}>
                    No linked controls or KPI bindings found for this requirement.
                  </p>
                )}
              </div>
            </>
          ) : null}

          {showInterpretForm ? (
            <form onSubmit={saveInterpretation} className="catalog-interpret-form catalog-animate-enter">
              <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-primary)" }}>
                New Interpretation {makeLegendIcon("Creates an app-specific interpretation for this requirement using existing KPI and governance category mappings.")}
              </div>

              <p className="section-copy" style={{ marginBottom: 0 }}>
                This interpretation applies at requirement level and is propagated to all linked controls/KPIs for this app.
              </p>

              <label style={{ display: "grid", gap: 4 }}>
                <span className="detail-label">
                  Application {makeLegendIcon("Select the connected application where this interpretation should apply.")}
                </span>
                <select
                  className="query-input"
                  value={interpretAppId}
                  onChange={(event) => setInterpretAppId(event.target.value)}
                  disabled={savingInterpretation}
                >
                  <option value="">Select application</option>
                  {connectedApps.map((app) => (
                    <option key={app.id} value={app.id}>
                      {app.name || app.id}
                    </option>
                  ))}
                </select>
              </label>

              <label style={{ display: "grid", gap: 4 }}>
                <span className="detail-label">Interpretation text</span>
                <textarea
                  className="query-input"
                  value={interpretText}
                  onChange={(event) => setInterpretText(event.target.value)}
                  rows={4}
                  placeholder="Write app-specific interpretation for this requirement..."
                  disabled={savingInterpretation}
                />
              </label>

              {interpretError ? <p className="error-text" style={{ marginBottom: 0 }}>{interpretError}</p> : null}
              {interpretNotice ? <p className="section-copy" style={{ marginBottom: 0, color: "var(--success)" }}>{interpretNotice}</p> : null}

              <div style={{ display: "flex", gap: "0.45rem" }}>
                <button type="submit" className="btn-primary catalog-action-btn" disabled={savingInterpretation || !canCreateInterpretation || !canSaveInterpretation}>
                  {savingInterpretation ? "Saving..." : "Save Interpretation"}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    setShowInterpretForm(false);
                    setInterpretError("");
                  }}
                  disabled={savingInterpretation}
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default CatalogSearchPanel;











