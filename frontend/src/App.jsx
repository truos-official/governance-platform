// AI Governance Platform — Dashboard Shell
// Phase 5: full dashboard implementation.
// Stack: React, no TypeScript, CSS variables, inline styles (per handoff v2 Section 7).
// No lucide-react or external component libraries in this project.

function App() {
  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", color: "var(--color-text, #1a1a1a)" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>AI Governance Platform</h1>
      <p style={{ color: "#666", marginTop: "0.5rem" }}>
        Phase 1 — infrastructure skeleton. Dashboard arrives in Phase 5.
      </p>
      <section style={{ marginTop: "2rem" }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.5rem" }}>Services</h2>
        <ul style={{ listStyle: "none", padding: 0, display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {[
            { label: "API",        href: "http://localhost:8000/docs" },
            { label: "Health",     href: "http://localhost:8000/health" },
            { label: "OTEL gRPC",  href: null, note: "localhost:4317" },
            { label: "OTEL HTTP",  href: null, note: "localhost:4318" },
          ].map(({ label, href, note }) => (
            <li key={label} style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
              <span style={{ fontWeight: 500, minWidth: "8rem" }}>{label}</span>
              {href
                ? <a href={href} style={{ color: "#0066cc" }}>{href}</a>
                : <code style={{ fontSize: "0.875rem", background: "#f4f4f4", padding: "0.1rem 0.4rem", borderRadius: 4 }}>{note}</code>
              }
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export default App;
