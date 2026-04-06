import React, { useMemo, useState } from "react";

import { getInterpretationTree } from "../api/catalogClient";

const TREE_LIMIT = 10;

function InterpretationsPanel() {
  const [requirementId, setRequirementId] = useState("");
  const [activeRequirementId, setActiveRequirementId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [treeData, setTreeData] = useState(null);
  const [treeSkip, setTreeSkip] = useState(0);
  const [totalRequirements, setTotalRequirements] = useState(0);

  async function fetchTree({ requirement, skip }) {
    setLoading(true);
    setError("");

    try {
      const payload = await getInterpretationTree({
        requirementId: requirement || undefined,
        skip,
        limit: TREE_LIMIT,
      });
      setTreeData(payload);
      setTreeSkip(skip);
      setTotalRequirements(payload.total_requirements ?? 0);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to load interpretation tree");
      setTreeData(null);
      setTotalRequirements(0);
      setTreeSkip(0);
    } finally {
      setLoading(false);
    }
  }

  async function loadTree(event) {
    event.preventDefault();
    const requirement = requirementId.trim();
    setActiveRequirementId(requirement);
    await fetchTree({ requirement, skip: 0 });
  }

  async function changeTreePage(direction) {
    if (loading) return;
    const nextSkip = Math.max(0, treeSkip + direction * TREE_LIMIT);
    if (nextSkip === treeSkip) return;
    await fetchTree({ requirement: activeRequirementId, skip: nextSkip });
  }

  const canPrev = treeSkip > 0;
  const canNext = treeSkip + TREE_LIMIT < totalRequirements;

  const visibleCount = treeData?.items?.length ?? 0;
  const rangeStart = useMemo(
    () => (totalRequirements > 0 ? treeSkip + 1 : 0),
    [totalRequirements, treeSkip]
  );
  const rangeEnd = useMemo(
    () => (totalRequirements > 0 ? Math.min(treeSkip + visibleCount, totalRequirements) : 0),
    [totalRequirements, treeSkip, visibleCount]
  );

  return (
    <section className="card">
      <h2 className="card-title">Interpretation Tree</h2>
      <p className="section-copy">
        Calls <code className="inline-code">GET /catalog/interpretations?view=tree</code>
      </p>

      <form onSubmit={loadTree} className="controls-row">
        <input
          type="text"
          value={requirementId}
          onChange={(event) => setRequirementId(event.target.value)}
          placeholder="Optional requirement UUID"
          className="query-input"
        />
        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? "Loading..." : "Load Tree"}
        </button>
      </form>

      {error ? <p className="error-text">{error}</p> : null}

      {treeData ? (
        <div className="tree-wrap">
          <div className="pagination-row">
            <p className="pagination-meta">
              Showing {rangeStart}-{rangeEnd} of {totalRequirements}
            </p>
            <div className="pagination-actions">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => changeTreePage(-1)}
                disabled={!canPrev || loading}
              >
                Prev
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => changeTreePage(1)}
                disabled={!canNext || loading}
              >
                Next
              </button>
            </div>
          </div>

          <ul className="tree-list">
            {treeData.items.map((node) => (
              <li key={node.requirement_id} className="tree-item">
                <code className="inline-code">{node.requirement_id}</code>
                <span className="chip">{node.layers.length} layers</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export default InterpretationsPanel;
