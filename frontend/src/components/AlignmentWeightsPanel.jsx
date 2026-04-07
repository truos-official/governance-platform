import React, { useState, useEffect, useCallback } from "react";

const API = "http://localhost:8000/api/v1";

const LEGENDS = {
  peer_adoption_rate: {
    label: "Peer Adoption Rate",
    description:
      "Weight given to how widely this control has been adopted by peer applications in the same risk tier. Higher weight makes your alignment score more sensitive to what peers are doing.",
    color: "#2563eb",
  },
  regulatory_density: {
    label: "Regulatory Density",
    description:
      "Weight given to how many regulatory requirements map to this control. Controls referenced by more regulations carry more compliance weight.",
    color: "#0891b2",
  },
  trend_velocity: {
    label: "Trend Velocity",
    description:
      "Weight given to quarter-over-quarter adoption momentum. Fast-rising controls score higher even if current adoption is still low.",
    color: "#7c3aed",
  },
};

function SliderRow({ field, value, onChange, disabled }) {
  const meta = LEGENDS[field];
  const pct  = Math.round(value * 100);

  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{
            display: "inline-block", width: 10, height: 10,
            borderRadius: "50%", background: meta.color, flexShrink: 0,
          }} />
          <span style={{ fontWeight: 600, fontSize: "0.92rem" }}>{meta.label}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <input
            type="number"
            min={0} max={100} step={1}
            value={pct}
            disabled={disabled}
            onChange={e => onChange(field, Math.min(100, Math.max(0, Number(e.target.value))) / 100)}
            style={{
              width: 54, textAlign: "center", fontWeight: 700,
              border: "1px solid var(--border)", borderRadius: 6,
              padding: "2px 4px", fontSize: "0.92rem",
              background: disabled ? "var(--surface)" : "white",
            }}
          />
          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>%</span>
        </div>
      </div>
      <input
        type="range" min={0} max={100} step={1}
        value={pct}
        disabled={disabled}
        onChange={e => onChange(field, Number(e.target.value) / 100)}
        style={{ width: "100%", accentColor: meta.color }}
      />
      <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", margin: "0.25rem 0 0" }}>
        {meta.description}
      </p>
    </div>
  );
}

function SumIndicator({ sum }) {
  const pct    = Math.round(sum * 100);
  const ok     = Math.abs(sum - 1.0) < 0.001;
  const color  = ok ? "#16a34a" : "#dc2626";
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0.6rem 0.9rem", borderRadius: 8,
      background: ok ? "#f0fdf4" : "#fef2f2",
      border: `1px solid ${ok ? "#bbf7d0" : "#fecaca"}`,
      marginBottom: "1.2rem",
    }}>
      <span style={{ fontSize: "0.85rem", fontWeight: 600, color }}>
        {ok ? "✓ Weights sum to 100%" : `⚠ Weights sum to ${pct}% — must equal 100%`}
      </span>
      <div style={{ display: "flex", gap: 4 }}>
        {Object.entries(LEGENDS).map(([f, m]) => (
          <span key={f} style={{
            width: 8, height: 8, borderRadius: "50%", background: m.color,
          }} />
        ))}
      </div>
    </div>
  );
}

export default function AlignmentWeightsPanel() {
  const [active,   setActive]   = useState(null);
  const [history,  setHistory]  = useState([]);
  const [weights,  setWeights]  = useState({ peer_adoption_rate: 0.5, regulatory_density: 0.3, trend_velocity: 0.2 });
  const [reason,   setReason]   = useState("");
  const [setBy,    setSetBy]    = useState("tristan.gitman@un.org");
  const [saving,   setSaving]   = useState(false);
  const [error,    setError]    = useState(null);
  const [success,  setSuccess]  = useState(false);
  const [editing,  setEditing]  = useState(false);

  const load = useCallback(async () => {
    try {
      const res  = await fetch(`${API}/admin/alignment-weights`);
      const data = await res.json();
      setActive(data.active);
      setHistory(data.history);
      setWeights({
        peer_adoption_rate: data.active.peer_adoption_rate,
        regulatory_density: data.active.regulatory_density,
        trend_velocity:     data.active.trend_velocity,
      });
    } catch (e) {
      setError("Failed to load weights.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const sum = Object.values(weights).reduce((a, b) => a + b, 0);

  // Auto-adjust: when one slider moves, redistribute remainder proportionally
  const handleSliderChange = (field, newVal) => {
    const others  = Object.keys(weights).filter(k => k !== field);
    const remain  = Math.max(0, 1.0 - newVal);
    const oldSum  = others.reduce((a, k) => a + weights[k], 0);
    const updated = { ...weights, [field]: newVal };
    if (oldSum > 0) {
      others.forEach(k => {
        updated[k] = Math.round((weights[k] / oldSum) * remain * 1000) / 1000;
      });
      // Fix floating point: force exact sum
      const diff = 1.0 - Object.values(updated).reduce((a, b) => a + b, 0);
      updated[others[others.length - 1]] = Math.round((updated[others[others.length - 1]] + diff) * 1000) / 1000;
    }
    setWeights(updated);
    setSuccess(false);
  };

  const handleSave = async () => {
    if (Math.abs(sum - 1.0) > 0.001) return;
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const res = await fetch(`${API}/admin/alignment-weights`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ ...weights, set_by: setBy, reason }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Save failed");
      }
      setSuccess(true);
      setEditing(false);
      setReason("");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.2rem" }}>
        <div>
          <h2 className="card-title" style={{ marginBottom: "0.2rem" }}>Alignment Score Weights</h2>
          <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", margin: 0 }}>
            Admin only · Changes are immutable and audited
          </p>
        </div>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="chip"
            style={{ cursor: "pointer", border: "none", background: "var(--accent)", color: "white", padding: "0.35rem 0.9rem" }}
          >
            Edit Weights
          </button>
        )}
      </div>

      {/* Formula legend */}
      <div style={{
        background: "var(--surface)", borderRadius: 8, padding: "0.8rem 1rem",
        marginBottom: "1.4rem", fontSize: "0.82rem", color: "var(--text-muted)",
        borderLeft: "3px solid var(--accent)",
      }}>
        <strong style={{ color: "var(--text)", display: "block", marginBottom: "0.3rem" }}>
          Alignment Score Formula
        </strong>
        control_weight = (peer_adoption × <span style={{ color: LEGENDS.peer_adoption_rate.color, fontWeight: 700 }}>W₁</span>)
        + (reg_density × <span style={{ color: LEGENDS.regulatory_density.color, fontWeight: 700 }}>W₂</span>)
        + (trend_velocity × <span style={{ color: LEGENDS.trend_velocity.color, fontWeight: 700 }}>W₃</span>)
        <br />
        alignment_score = Σ(adopted × weight) / Σ(applicable × weight) × 100
      </div>

      {/* Sliders */}
      <SumIndicator sum={sum} />
      {Object.keys(LEGENDS).map(field => (
        <SliderRow
          key={field}
          field={field}
          value={weights[field]}
          onChange={handleSliderChange}
          disabled={!editing}
        />
      ))}

      {/* Reason + set_by */}
      {editing && (
        <div style={{ marginTop: "0.5rem", marginBottom: "1rem" }}>
          <label style={{ fontSize: "0.82rem", fontWeight: 600, display: "block", marginBottom: "0.3rem" }}>
            Set by (email)
          </label>
          <input
            value={setBy}
            onChange={e => setSetBy(e.target.value)}
            style={{ width: "100%", marginBottom: "0.7rem", padding: "0.4rem 0.6rem", border: "1px solid var(--border)", borderRadius: 6, fontSize: "0.88rem" }}
          />
          <label style={{ fontSize: "0.82rem", fontWeight: 600, display: "block", marginBottom: "0.3rem" }}>
            Reason for change <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(audit log)</span>
          </label>
          <textarea
            value={reason}
            onChange={e => setReason(e.target.value)}
            rows={2}
            placeholder="e.g. Increasing peer signal weight for Q2 governance review"
            style={{ width: "100%", padding: "0.4rem 0.6rem", border: "1px solid var(--border)", borderRadius: 6, fontSize: "0.88rem", resize: "vertical" }}
          />
        </div>
      )}

      {error   && <p style={{ color: "#dc2626", fontSize: "0.85rem", marginBottom: "0.7rem" }}>{error}</p>}
      {success && <p style={{ color: "#16a34a", fontSize: "0.85rem", marginBottom: "0.7rem" }}>✓ Weights saved successfully.</p>}

      {editing && (
        <div style={{ display: "flex", gap: "0.7rem", marginBottom: "1.5rem" }}>
          <button
            onClick={handleSave}
            disabled={saving || Math.abs(sum - 1.0) > 0.001}
            style={{
              padding: "0.45rem 1.2rem", borderRadius: 7, border: "none",
              background: Math.abs(sum - 1.0) > 0.001 ? "#e5e7eb" : "var(--accent)",
              color: Math.abs(sum - 1.0) > 0.001 ? "#9ca3af" : "white",
              fontWeight: 600, cursor: saving ? "wait" : "pointer", fontSize: "0.88rem",
            }}
          >
            {saving ? "Saving…" : "Save Weights"}
          </button>
          <button
            onClick={() => { setEditing(false); load(); }}
            style={{ padding: "0.45rem 1rem", borderRadius: 7, border: "1px solid var(--border)", background: "white", cursor: "pointer", fontSize: "0.88rem" }}
          >
            Cancel
          </button>
        </div>
      )}

      {/* Audit history */}
      <div>
        <h3 style={{ fontSize: "0.88rem", fontWeight: 700, marginBottom: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Change History
        </h3>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border)" }}>
                {["Peer", "Reg", "Trend", "Set by", "Date", "Reason", "Status"].map(h => (
                  <th key={h} style={{ textAlign: "left", padding: "0.4rem 0.6rem", color: "var(--text-muted)", fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map(row => (
                <tr key={row.id} style={{ borderBottom: "1px solid var(--border)", background: row.is_active ? "#f0fdf4" : "transparent" }}>
                  <td style={{ padding: "0.4rem 0.6rem", fontWeight: 600, color: LEGENDS.peer_adoption_rate.color }}>{Math.round(row.peer_adoption_rate * 100)}%</td>
                  <td style={{ padding: "0.4rem 0.6rem", fontWeight: 600, color: LEGENDS.regulatory_density.color }}>{Math.round(row.regulatory_density * 100)}%</td>
                  <td style={{ padding: "0.4rem 0.6rem", fontWeight: 600, color: LEGENDS.trend_velocity.color }}>{Math.round(row.trend_velocity * 100)}%</td>
                  <td style={{ padding: "0.4rem 0.6rem" }}>{row.set_by}</td>
                  <td style={{ padding: "0.4rem 0.6rem", whiteSpace: "nowrap" }}>{new Date(row.set_at).toLocaleDateString()}</td>
                  <td style={{ padding: "0.4rem 0.6rem", color: "var(--text-muted)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.reason || "—"}</td>
                  <td style={{ padding: "0.4rem 0.6rem" }}>
                    {row.is_active
                      ? <span style={{ background: "#dcfce7", color: "#16a34a", borderRadius: 4, padding: "1px 7px", fontWeight: 600, fontSize: "0.78rem" }}>Active</span>
                      : <span style={{ background: "#f3f4f6", color: "#6b7280", borderRadius: 4, padding: "1px 7px", fontSize: "0.78rem" }}>Superseded</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
