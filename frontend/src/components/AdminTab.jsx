import React, { useEffect, useState, Suspense } from 'react';
import AlignmentWeightsPanel from './AlignmentWeightsPanel.jsx';
import { api } from '../api/client.js';

const DeveloperIntegrationGuide = React.lazy(() => import('./DeveloperIntegrationGuide.jsx'));

const SUBTABS = [
  { id: 'weights',    label: 'Alignment Weights' },
  { id: 'peers',      label: 'Peer Aggregates' },
  { id: 'curation',   label: 'Curation Queue' },
  { id: 'apps',       label: 'Connected Apps' },
  { id: 'mcp',        label: 'MCP Access' },
  { id: 'docs',       label: 'Technical Docs' },
];

export default function AdminTab() {
  const [sub, setSub] = useState('weights');

  return (
    <div>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="subtab-strip">
          {SUBTABS.map(t => (
            <button key={t.id} className={`subtab ${sub === t.id ? 'active' : ''}`}
              onClick={() => setSub(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        <div style={{ padding: '1.5rem' }}>
          {sub === 'weights'  && <AlignmentWeightsPanel />}
          {sub === 'peers'    && <PeerAggregatesPanel />}
          {sub === 'curation' && <CurationQueuePanel />}
          {sub === 'apps'     && <ConnectedAppsPanel />}
          {sub === 'mcp'      && <MCPAccessPanel />}
          {sub === 'docs'     && <TechDocsPanel />}
        </div>
      </div>
    </div>
  );
}

function PeerAggregatesPanel() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const payload = await api.refreshPeerAggregates();
      setResult(payload);
    } catch (e) { setResult({ error: e.message }); }
    finally { setLoading(false); }
  };

  return (
    <div>
      <h3 className="card-title" style={{ border: 'none', padding: 0, marginBottom: '0.75rem' }}>Peer Aggregates</h3>
      <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
        Refreshes the peer benchmark table used by the alignment engine and benchmark panels.
        Run after significant new telemetry has been ingested.
      </p>
      <button className="btn btn-unblue" onClick={refresh} disabled={loading}>
        {loading ? 'Refreshing…' : 'Refresh Peer Aggregates'}
      </button>
      {result && !result.error && (
        <div className="alert alert-success" style={{ marginTop: '1rem' }}>
          ✓ Refreshed — {result.tiers_processed} tiers, {result.aggregates_written} aggregates written
        </div>
      )}
      {result?.error && (
        <div className="alert alert-danger" style={{ marginTop: '1rem' }}>{result.error}</div>
      )}
    </div>
  );
}

function fmtDateTime(value) {
  if (!value) {
    return 'N/A';
  }
  return new Date(value).toLocaleString();
}

function CurationQueuePanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadItems = async () => {
    setLoading(true);
    setError('');
    try {
      const payload = await api.getCurationQueue();
      setItems(payload || []);
    } catch (e) {
      setError(e.message || 'Failed to load curation queue');
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, []);

  return (
    <div>
      <h3 className="card-title" style={{ border: 'none', padding: 0, marginBottom: '0.75rem' }}>Curation Queue</h3>
      <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
        Governance curation items awaiting review. Endpoint: GET /curation/queue.
      </p>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
        <span className="badge badge-grey">Total Items: {items.length}</span>
        <span className="badge badge-yellow">Pending: {items.filter((i) => (i.status || '').toUpperCase() === 'PENDING').length}</span>
        <button className="btn btn-outline btn-sm" onClick={loadItems} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh Queue'}
        </button>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {!error && (
        <table className="table" style={{ marginBottom: 0 }}>
          <thead>
            <tr>
              <th>Created</th>
              <th>Control ID</th>
              <th>Type</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={4} style={{ color: 'var(--text-tertiary)' }}>No curation items found.</td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id}>
                <td>{fmtDateTime(item.created_at)}</td>
                <td>{item.control_id || 'N/A'}</td>
                <td>{item.item_type || 'N/A'}</td>
                <td>
                  <span className={`badge ${(item.status || '').toUpperCase() === 'PENDING' ? 'badge-yellow' : 'badge-green'}`}>
                    {item.status || 'UNKNOWN'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ConnectedAppsPanel() {
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadApps = async () => {
    setLoading(true);
    setError('');
    try {
      const payload = await api.listApplications();
      setApps(payload || []);
    } catch (e) {
      setError(e.message || 'Failed to load applications');
      setApps([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadApps();
  }, []);

  const activeCount = apps.filter((app) => app.status === 'active').length;
  const disconnectedCount = apps.filter((app) => app.status === 'disconnected').length;

  return (
    <div>
      <h3 className="card-title" style={{ border: 'none', padding: 0, marginBottom: '0.75rem' }}>Connected Applications</h3>
      <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
        Admin inventory of registered applications. Endpoint: GET /applications.
      </p>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
        <span className="badge badge-grey">Total: {apps.length}</span>
        <span className="badge badge-green">Active: {activeCount}</span>
        <span className="badge badge-grey">Disconnected: {disconnectedCount}</span>
        <button className="btn btn-outline btn-sm" onClick={loadApps} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh Apps'}
        </button>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {!error && (
        <table className="table" style={{ marginBottom: 0 }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Tier</th>
              <th>Status</th>
              <th>Owner</th>
              <th>Registered</th>
            </tr>
          </thead>
          <tbody>
            {apps.length === 0 && (
              <tr>
                <td colSpan={5} style={{ color: 'var(--text-tertiary)' }}>No applications found.</td>
              </tr>
            )}
            {apps.map((app) => (
              <tr key={app.id}>
                <td>
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontWeight: 700 }}>{app.name}</span>
                    <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{app.id}</span>
                  </div>
                </td>
                <td>{app.current_tier || 'N/A'}</td>
                <td>
                  <span className={`badge ${app.status === 'active' ? 'badge-green' : 'badge-grey'}`}>
                    {app.status}
                  </span>
                </td>
                <td>{app.owner_email || 'N/A'}</td>
                <td>{fmtDateTime(app.registered_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function MCPAccessPanel() {
  return (
    <div>
      <h3 className="card-title" style={{ border: 'none', padding: 0, marginBottom: '0.75rem' }}>MCP Access</h3>
      <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
        The governance platform exposes an MCP server with 11 tools for AI agents to query the regulatory catalog and peer intelligence data.
      </p>
      <div className="card card-flat" style={{ background: 'var(--surface-2)', marginBottom: '1rem' }}>
        <div className="section-label">Server Configuration</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
          {[
            { label: 'Server name', value: 'ai-governance' },
            { label: 'Auth', value: 'Azure Entra ID OAuth2 client_credentials' },
            { label: 'Scope', value: 'governance.read' },
            { label: 'Endpoint', value: 'https://{governance-api-host}/mcp' },
          ].map(row => (
            <div key={row.label} style={{ display: 'flex', gap: '1rem', fontSize: '0.82rem' }}>
              <span style={{ width: 120, color: 'var(--text-tertiary)', flexShrink: 0 }}>{row.label}</span>
              <code className="inline-code">{row.value}</code>
            </div>
          ))}
        </div>
      </div>
      <div className="section-label">Available Tools (11)</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginTop: '0.5rem' }}>
        {[
          'search_controls', 'get_control_detail', 'get_requirement_detail',
          'list_controls_by_domain', 'get_interpretation_tree',
          'get_peer_benchmarks', 'get_alignment_score', 'get_risk_tier',
          'get_recommended_controls', 'get_gap_analysis', 'get_compliance_trend',
        ].map(tool => (
          <code key={tool} className="inline-code" style={{ fontSize: '0.75rem' }}>{tool}</code>
        ))}
      </div>
    </div>
  );
}

function TechDocsPanel() {
  const [activeDoc, setActiveDoc] = useState(null);

  const DOCS = [
    { id: 'architecture', title: 'Platform Architecture',      desc: 'Complete technical architecture by component — data layer, API layer, telemetry, tier engine, alignment engine, KPI calculator.' },
    { id: 'risks-guide',  title: 'Risks & Controls Guide',     desc: 'How to set up and manage the governance catalog: interpretations, curation queue, control tiers, measurement modes, audit logs.' },
    { id: 'rules-ref',    title: 'Governance Rules Reference', desc: 'Definitions of all governance concepts: regulations, requirements, controls, measures, tier scoring, alignment formula, peer benchmarking.' },
  ];

  if (activeDoc === 'dev-guide') {
    return (
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
          <button onClick={() => setActiveDoc(null)}
            style={{ fontSize: '0.82rem', color: 'var(--primary)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>
            ← Back to Docs
          </button>
          <span style={{ color: 'var(--border)' }}>|</span>
          <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.9rem' }}>Developer Integration Guide</span>
        </div>
        <Suspense fallback={
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-tertiary)' }}>
            Loading feature catalog…
          </div>
        }>
          <DeveloperIntegrationGuide />
        </Suspense>
      </div>
    );
  }

  return (
    <div>
      <h3 className="card-title" style={{ border: 'none', padding: 0, marginBottom: '1rem' }}>Technical Documentation</h3>
      <div className="grid-2">
        {DOCS.map(doc => (
          <div key={doc.id} className="card card-sm" style={{ cursor: 'default', marginBottom: 0 }}>
            <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.4rem' }}>{doc.title}</div>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: '0.875rem' }}>{doc.desc}</p>
            <span className="badge badge-grey">Coming soon</span>
          </div>
        ))}
        <div className="card card-sm" style={{ cursor: 'pointer', marginBottom: 0, border: '1.5px solid var(--un-blue)', background: 'var(--un-blue-light)' }}
          onClick={() => setActiveDoc('dev-guide')}>
          <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.4rem', color: 'var(--un-blue-dark)' }}>
            Developer Integration Guide ↗
          </div>
          <p style={{ fontSize: '0.78rem', color: 'var(--un-blue-dark)', lineHeight: 1.5, marginBottom: '0.875rem' }}>
            Interactive feature catalog wizard. Select features, configure your app profile, and export a personalized Excel spec sheet.
          </p>
          <span className="badge badge-unblue">39 features · 8 categories</span>
        </div>
      </div>
    </div>
  );
}
