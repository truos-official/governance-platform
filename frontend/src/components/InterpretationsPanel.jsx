import { useState } from "react";

import { getInterpretationTree } from "../api/catalogClient";

function InterpretationsPanel() {
  const [requirementId, setRequirementId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [treeData, setTreeData] = useState(null);

  async function loadTree(event) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const payload = await getInterpretationTree({
        requirementId: requirementId.trim() || undefined,
        limit: 20,
      });
      setTreeData(payload);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to load interpretation tree");
      setTreeData(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section
      style={{
        marginTop: "2rem",
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: "1rem",
        background: "#fafafa",
      }}
    >
      <h2 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.5rem" }}>Interpretation Tree</h2>
      <p style={{ marginTop: 0, marginBottom: "1rem", color: "#555" }}>
        Calls <code>GET /catalog/interpretations?view=tree</code>.
      </p>

      <form onSubmit={loadTree} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <input
          type="text"
          value={requirementId}
          onChange={(event) => setRequirementId(event.target.value)}
          placeholder="Optional requirement UUID"
          style={{
            minWidth: 280,
            flex: "1 1 320px",
            padding: "0.5rem",
            borderRadius: 6,
            border: "1px solid #d1d5db",
          }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: "0.5rem 0.9rem",
            borderRadius: 6,
            border: "1px solid #0f62fe",
            background: loading ? "#9bbcf9" : "#0f62fe",
            color: "#fff",
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Loading..." : "Load Tree"}
        </button>
      </form>

      {error ? (
        <p style={{ color: "#b91c1c", marginTop: "0.75rem", marginBottom: 0 }}>{error}</p>
      ) : null}

      {treeData ? (
        <div style={{ marginTop: "1rem" }}>
          <p style={{ marginTop: 0 }}>
            Requirements returned: <strong>{treeData.total_requirements}</strong>
          </p>
          <ul style={{ margin: 0, paddingLeft: "1.25rem" }}>
            {treeData.items.map((node) => (
              <li key={node.requirement_id} style={{ marginBottom: "0.4rem" }}>
                <code>{node.requirement_id}</code> ({node.layers.length} layers)
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export default InterpretationsPanel;

