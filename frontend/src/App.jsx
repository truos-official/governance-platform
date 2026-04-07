import React from "react";
import AlignmentWeightsPanel from "./components/AlignmentWeightsPanel";
import CatalogSearchPanel from "./components/CatalogSearchPanel";
import InterpretationsPanel from "./components/InterpretationsPanel";

function App() {
  return (
    <div className="app">
      <header className="header" style={{ padding: 0 }}>
        <div className="header-top">
          <div className="header-title">
            <img src="/un-emblem.png" alt="UN Emblem" style={{ height: "34px", width: "auto" }} />
            <div>
              <h1>Responsible AI</h1>
              <p>Demo</p>
            </div>
          </div>
          <div className="header-meta">
            <span className="chip">Enterprise Governance</span>
          </div>
        </div>

        <div className="header-nav-row">
          <div className="header-nav-group">
            <span className="zone-label">Platform Endpoints</span>
            <div className="service-inline-list">
              <a href="http://localhost:8000/docs" className="service-inline-link">API Docs</a>
              <a href="http://localhost:8000/health" className="service-inline-link">Health</a>
              <span className="service-inline-code">OTEL gRPC:4317</span>
              <span className="service-inline-code">OTEL HTTP:4318</span>
            </div>
          </div>
        </div>
      </header>

      <main className="main">
        <section className="card">
          <h2 className="card-title">System Services</h2>
          <div className="service-grid">
            {[
              { label: "API", href: "http://localhost:8000/docs", value: "OpenAPI" },
              { label: "Health", href: "http://localhost:8000/health", value: "Status" },
              { label: "OTEL gRPC", href: null, value: "localhost:4317" },
              { label: "OTEL HTTP", href: null, value: "localhost:4318" },
            ].map(({ label, href, value }) => (
              <div key={label} className="service-tile">
                <p className="service-label">{label}</p>
                {href ? (
                  <a href={href} className="service-link">{value}</a>
                ) : (
                  <code className="inline-code">{value}</code>
                )}
              </div>
            ))}
          </div>
        </section>

        <CatalogSearchPanel />
        <InterpretationsPanel />
        <AlignmentWeightsPanel />
      </main>
    </div>
  );
}

export default App;
