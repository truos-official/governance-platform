import React, { useEffect, useMemo, useState } from "react";

import {
  autocompleteCatalog,
  getCatalogItemDetail,
  searchCatalog,
} from "../api/catalogClient";

const SEARCH_LIMIT = 10;

function detailFields(itemType, detail) {
  if (!detail) return [];

  if (itemType === "control") {
    return [
      ["Code", detail.code],
      ["Title", detail.title],
      ["Domain", detail.domain],
      ["Tier", detail.tier],
      ["Measurement", detail.measurement_mode],
      ["Foundation", detail.is_foundation === true ? "Yes" : detail.is_foundation === false ? "No" : undefined],
      ["Description", detail.description],
    ];
  }

  if (itemType === "requirement") {
    return [
      ["Code", detail.code],
      ["Title", detail.title],
      ["Regulation", detail.regulation_title],
      ["Jurisdiction", detail.jurisdiction],
      ["Category", detail.category],
      ["Description", detail.description],
    ];
  }

  return Object.entries(detail)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => [key, String(value)]);
}

function CatalogSearchPanel() {
  const [query, setQuery] = useState("");
  const [resultType, setResultType] = useState("");
  const [sortBy, setSortBy] = useState("relevance");
  const [suggestions, setSuggestions] = useState([]);
  const [results, setResults] = useState([]);
  const [facets, setFacets] = useState({});
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [error, setError] = useState("");

  const [activeQuery, setActiveQuery] = useState("");
  const [activeType, setActiveType] = useState("");
  const [activeSort, setActiveSort] = useState("relevance");
  const [searchSkip, setSearchSkip] = useState(0);
  const [searchTotal, setSearchTotal] = useState(0);

  const [selectedItem, setSelectedItem] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");

  const queryTrimmed = useMemo(() => query.trim(), [query]);

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
          type: resultType || undefined,
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
  }, [queryTrimmed, resultType]);

  async function executeSearch({ q, type, sort, skip }) {
    setLoadingSearch(true);
    setError("");

    try {
      const response = await searchCatalog({
        q,
        type: type || undefined,
        sort,
        skip,
        limit: SEARCH_LIMIT,
      });
      setResults(response.items ?? []);
      setFacets(response.facets ?? {});
      setSearchSkip(skip);
      setSearchTotal(response.total ?? 0);
      setSelectedItem(null);
      setSelectedDetail(null);
      setDetailError("");
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Search failed");
      setResults([]);
      setFacets({});
      setSearchTotal(0);
      setSearchSkip(0);
      setSelectedItem(null);
      setSelectedDetail(null);
      setDetailError("");
    } finally {
      setLoadingSearch(false);
    }
  }

  async function runSearch(event) {
    event.preventDefault();
    if (!queryTrimmed) return;

    setActiveQuery(queryTrimmed);
    setActiveType(resultType);
    setActiveSort(sortBy);
    await executeSearch({ q: queryTrimmed, type: resultType, sort: sortBy, skip: 0 });
  }

  async function changeSearchPage(direction) {
    if (!activeQuery || loadingSearch) return;
    const nextSkip = Math.max(0, searchSkip + direction * SEARCH_LIMIT);
    if (nextSkip === searchSkip) return;
    await executeSearch({ q: activeQuery, type: activeType, sort: activeSort, skip: nextSkip });
  }

  function applySuggestion(suggestion) {
    setQuery(suggestion.label ?? "");
  }

  async function selectResult(item) {
    setSelectedItem(item);
    setSelectedDetail(null);
    setDetailError("");

    if (!item?.id || !item?.type) {
      setDetailError("Selected result does not have a resolvable type/id");
      return;
    }

    setLoadingDetail(true);
    try {
      const detail = await getCatalogItemDetail(item);
      setSelectedDetail(detail);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setDetailError(typeof detail === "string" ? detail : "Failed to load detail");
    } finally {
      setLoadingDetail(false);
    }
  }

  const fields = detailFields(selectedItem?.type, selectedDetail).filter(([, value]) => value);
  const canPrev = searchSkip > 0;
  const canNext = searchSkip + SEARCH_LIMIT < searchTotal;
  const resultStart = searchTotal > 0 ? searchSkip + 1 : 0;
  const resultEnd = searchTotal > 0 ? Math.min(searchSkip + (results.length || 0), searchTotal) : 0;

  return (
    <section className="card">
      <h2 className="card-title">Catalog Search</h2>
      <p className="section-copy">
        Uses <code className="inline-code">/catalog/search</code>, <code className="inline-code">/catalog/autocomplete</code>, and detail endpoints.
      </p>

      <form onSubmit={runSearch} className="controls-row">
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search controls or requirements"
          className="query-input"
        />
        <select
          className="query-input type-select"
          value={resultType}
          onChange={(event) => setResultType(event.target.value)}
        >
          <option value="">All Types</option>
          <option value="control">Control</option>
          <option value="requirement">Requirement</option>
        </select>
        <select
          className="query-input sort-select"
          value={sortBy}
          onChange={(event) => setSortBy(event.target.value)}
        >
          <option value="relevance">Sort: Relevance</option>
          <option value="code">Sort: Code</option>
          <option value="title">Sort: Title</option>
        </select>
        <button type="submit" className="btn-primary" disabled={loadingSearch || !queryTrimmed}>
          {loadingSearch ? "Searching..." : "Search"}
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

      {error ? <p className="error-text">{error}</p> : null}

      {Object.keys(facets).length > 0 ? (
        <div className="facet-wrap">
          {Object.entries(facets).map(([name, values]) => {
            const count = Object.keys(values ?? {}).length;
            if (!count) return null;
            return (
              <span key={name} className="chip">
                {name}: {count}
              </span>
            );
          })}
        </div>
      ) : null}

      {searchTotal > 0 ? (
        <div className="pagination-row">
          <p className="pagination-meta">
            Showing {resultStart}-{resultEnd} of {searchTotal}
          </p>
          <div className="pagination-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => changeSearchPage(-1)}
              disabled={!canPrev || loadingSearch}
            >
              Prev
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => changeSearchPage(1)}
              disabled={!canNext || loadingSearch}
            >
              Next
            </button>
          </div>
        </div>
      ) : null}

      {results.length > 0 ? (
        <ul className="tree-list">
          {results.map((item) => (
            <li key={item.id} className="tree-item search-item">
              <button
                type="button"
                className={`search-select-btn${selectedItem?.id === item.id ? " active" : ""}`}
                onClick={() => selectResult(item)}
              >
                <span className="search-main">
                  <strong>{item.code || item.id}</strong>
                  <span>{item.title || "Untitled"}</span>
                </span>
                <span className="chip">{item.type || "unknown"}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {selectedItem ? (
        <div className="detail-drawer">
          <p className="section-copy">
            Detail: <strong>{selectedItem.code || selectedItem.id}</strong>
          </p>

          {loadingDetail ? <p className="section-copy">Loading detail...</p> : null}
          {detailError ? <p className="error-text">{detailError}</p> : null}

          {!loadingDetail && !detailError && fields.length > 0 ? (
            <div className="detail-grid">
              {fields.map(([label, value]) => (
                <div key={label} className="detail-row">
                  <span className="detail-label">{label}</span>
                  <span className="detail-value">{value}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default CatalogSearchPanel;
