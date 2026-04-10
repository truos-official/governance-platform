import React, { useEffect, useState, Suspense } from 'react';
import PropTypes from 'prop-types';
import AlignmentWeightsPanel from './AlignmentWeightsPanel.jsx';
import ApplicationsTab from './ApplicationsTab.jsx';
import { useApp, ROLES } from '../context/AppContext.jsx';

const DeveloperIntegrationGuide = React.lazy(() => import('./DeveloperIntegrationGuide.jsx'));

const SUBTABS = [
  { id: 'applications', label: 'Applications', minRole: ROLES.DIVISION_ADMIN },
  { id: 'weights', label: 'Risk Category Settings', minRole: ROLES.SECRETARIAT_ADMIN },
  { id: 'docs', label: 'Technical Docs', minRole: ROLES.DIVISION_ADMIN },
];

const ROLE_RANK = {
  [ROLES.APPLICATION_OWNER]: 1,
  [ROLES.EXPERT_CONTRIBUTOR]: 1,
  [ROLES.REVIEWER]: 1,
  [ROLES.DIVISION_ADMIN]: 2,
  [ROLES.SECRETARIAT_ADMIN]: 3,
};

function canAccessSubtab(userRole, minRole) {
  const userRank = ROLE_RANK[userRole] || 0;
  const requiredRank = ROLE_RANK[minRole] || 0;
  return userRank >= requiredRank;
}

export default function AdminTab({ onNavigate }) {
  const { currentUser } = useApp();
  const [sub, setSub] = useState('applications');
  const allowedSubtabs = SUBTABS.filter((tab) => canAccessSubtab(currentUser.role, tab.minRole));

  useEffect(() => {
    if (!allowedSubtabs.some((tab) => tab.id === sub)) {
      setSub(allowedSubtabs[0]?.id || null);
    }
  }, [allowedSubtabs, sub]);

  return (
    <div>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--border)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
          Role: <strong>{currentUser.role.replace(/_/g, ' ')}</strong>
        </div>
        <div className="subtab-strip">
          {allowedSubtabs.map(t => (
            <button key={t.id} className={`subtab ${sub === t.id ? 'active' : ''}`}
              onClick={() => setSub(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        <div style={{ padding: '1.5rem' }}>
          {sub === 'applications' && <ApplicationsTab onNavigate={onNavigate} />}
          {sub === 'weights'  && <AlignmentWeightsPanel />}
          {sub === 'docs'     && <TechDocsPanel />}
        </div>
      </div>
    </div>
  );
}

AdminTab.propTypes = {
  onNavigate: PropTypes.func,
};

AdminTab.defaultProps = {
  onNavigate: () => {},
};

function MCPAccessSection() {
  return (
    <div className="card card-sm" style={{ marginTop: '1rem', marginBottom: 0 }}>
      <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.4rem' }}>
        MCP Access
      </div>
      <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
        The governance platform exposes an MCP server with 11 tools for AI agents to query the regulatory catalog and peer intelligence data.
      </p>
      <div className="card card-flat" style={{ background: 'var(--surface-2)', marginBottom: '0.75rem' }}>
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
      <MCPAccessSection />
    </div>
  );
}

