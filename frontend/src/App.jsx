import { useState } from 'react';
import PropTypes from 'prop-types';
import { useApp } from './context/AppContext.jsx';
import GovernanceTab    from './components/GovernanceTab.jsx';
import ApplicationsTab  from './components/ApplicationsTab.jsx';
import RisksControlsTab from './components/RisksControlsTab.jsx';
import AdminTab         from './components/AdminTab.jsx';

// Tab icons (inline SVG — no lucide dependency required)
const Icons = {
  Governance:    () => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>,
  Applications:  () => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>,
  RisksControls: () => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  Admin:         () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0-16 0"/><path d="M19 8l2 2-6 6-3-3 2-2 1 1 4-4z"/></svg>,
  ChevronDown:   () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"/></svg>,
};

const GOV_COLOR = '#009edb';

export default function App() {
  const { currentUser, canAdmin, selectedApp } = useApp();
  const [activeTab, setActiveTab] = useState('governance');
  const [adminOpen, setAdminOpen] = useState(false);

  const govTabs = [
    { id: 'governance',     label: 'Governance',       Icon: Icons.Governance },
    { id: 'applications',   label: 'Applications',     Icon: Icons.Applications },
    { id: 'risks-controls', label: 'Risks & Controls', Icon: Icons.RisksControls },
  ];

  const NavTab = ({ tab, color }) => {
    const isActive = activeTab === tab.id;
    return (
      <button
        onClick={() => setActiveTab(tab.id)}
        className="nav-tab"
        style={{
          color: isActive ? color : undefined,
          borderBottomColor: isActive ? color : undefined,
          fontWeight: isActive ? 600 : 400,
        }}
      >
        <tab.Icon />
        {tab.label}
      </button>
    );
  };
  NavTab.propTypes = {
    tab: PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      Icon: PropTypes.func,
    }).isRequired,
    color: PropTypes.string,
  };

  const renderTab = () => {
    switch (activeTab) {
      case 'governance':     return <GovernanceTab />;
      case 'applications':   return <ApplicationsTab onNavigate={setActiveTab} />;
      case 'risks-controls': return <RisksControlsTab />;
      case 'admin':          return canAdmin ? <AdminTab /> : null;
      default:               return <GovernanceTab />;
    }
  };

  return (
    <div className="app-shell">

      {/* ── Header ── */}
      <header className="app-header">

        {/* Top row — brand + user + admin */}
        <div className="header-top">
          <div className="header-brand">
            <img src="/un-emblem.png" alt="UN Emblem" style={{ height: 34, width: 'auto' }} />
            <div>
              <h1>AI Governance Platform</h1>
              <p>United Nations · OICT</p>
            </div>
          </div>

          <div className="header-actions">
            {/* Role badge */}
            <span className="chip" style={{ fontSize: '0.72rem', background: 'var(--un-blue-light)', borderColor: 'var(--un-blue)', color: 'var(--un-blue-dark)' }}>
              {currentUser.role.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
            </span>

            {/* User name */}
            <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
              {currentUser.name}
            </span>

            {/* Admin button */}
            {canAdmin && (
              <div style={{ position: 'relative' }}>
                <button
                  onClick={() => { setAdminOpen(!adminOpen); setActiveTab('admin'); }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.3rem',
                    background: activeTab === 'admin' ? 'var(--surface-2)' : 'none',
                    border: '1px solid var(--border)', borderRadius: 6,
                    padding: '0.3rem 0.65rem', fontSize: '0.75rem', cursor: 'pointer',
                    color: activeTab === 'admin' ? 'var(--text-primary)' : 'var(--text-secondary)',
                    fontFamily: 'inherit',
                  }}
                >
                  <Icons.Admin />
                  Admin
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Nav row — two zones */}
        <div className="header-nav">
          <div className="nav-zone" style={{ paddingLeft: '0.5rem' }}>
            <span className="nav-zone-label">Governance Platform</span>
            <div className="nav-zone-tabs">
              {govTabs.map(tab => <NavTab key={tab.id} tab={tab} color={GOV_COLOR} />)}
            </div>
          </div>
        </div>

      </header>

      {/* ── Body ── */}
      <div className="app-body">

        {/* Sidebar — app selector + step nav (only on Governance tab) */}
        {activeTab === 'governance' && (
          <AppSidebar onNavigate={setActiveTab} />
        )}

        {/* Main content */}
        <main style={{ flex: 1, overflowY: 'auto', padding: '1.5rem 2rem', maxWidth: activeTab === 'governance' ? 'none' : 1200, margin: '0 auto', width: '100%' }}>
          {renderTab()}
        </main>

      </div>

      {/* Footer */}
      <footer style={{ borderTop: '1px solid var(--border)', background: 'var(--surface)', padding: '0.875rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <p style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
          UN AI Governance Platform · Built by{' '}
          <a href="https://linkedin.com/in/tristangitman" target="_blank" rel="noreferrer"
            style={{ color: 'var(--primary)', textDecoration: 'none', fontWeight: 500 }}>
            Tristan Gitman
          </a>
          {' '}· OICT
        </p>
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer"
          style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', textDecoration: 'none' }}>
          API Docs ↗
        </a>
      </footer>
    </div>
  );
}

// ── Sidebar ──────────────────────────────────────────────────
function AppSidebar({ onNavigate }) {
  const { selectedApp, selectApp } = useApp();
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const loadApps = async () => {
    if (apps.length > 0) { setOpen(!open); return; }
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/v1/applications');
      const data = await res.json();
      setApps(data);
      setOpen(true);
    } catch { } finally { setLoading(false); }
  };

  const STEPS = [
    { num: 1, label: 'Use Case' },
    { num: 2, label: 'Risk Classification' },
    { num: 3, label: 'Technical Architecture' },
    { num: 4, label: 'Data Readiness' },
    { num: 5, label: 'Data Integration' },
    { num: 6, label: 'Security' },
    { num: 7, label: 'Infrastructure' },
    { num: 8, label: 'Solution Design' },
    { num: 9, label: 'System Performance' },
  ];

  return (
    <aside className="app-sidebar" style={{ padding: '1rem 0' }}>

      {/* App selector */}
      <div style={{ padding: '0 0.75rem 0.75rem' }}>
        <div className="sidebar-section-label" style={{ marginBottom: '0.5rem' }}>Connected App</div>
        <button
          onClick={loadApps}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '0.5rem 0.75rem', border: '1px solid var(--border)', borderRadius: 8,
            background: 'var(--surface-2)', cursor: 'pointer', fontFamily: 'inherit',
            fontSize: '0.82rem', fontWeight: 500, color: 'var(--text-primary)',
            transition: 'border-color 0.15s',
          }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {selectedApp ? selectedApp.name : 'Select application…'}
          </span>
          <Icons.ChevronDown />
        </button>

        {/* App dropdown */}
        {open && (
          <div style={{
            position: 'absolute', zIndex: 50, left: 0, right: 0,
            margin: '0 0.75rem', background: 'var(--surface)',
            border: '1px solid var(--border)', borderRadius: 8,
            boxShadow: 'var(--shadow-3)', maxHeight: 200, overflowY: 'auto',
          }}>
            {loading && <div style={{ padding: '0.75rem 1rem', fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>Loading…</div>}
            {apps.length === 0 && !loading && (
              <div style={{ padding: '0.75rem 1rem', fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>
                No apps registered.{' '}
                <button onClick={() => { setOpen(false); onNavigate('applications'); }}
                  style={{ color: 'var(--primary)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'inherit', textDecoration: 'underline' }}>
                  Register one →
                </button>
              </div>
            )}
            {apps.map(app => (
              <button key={app.id}
                onClick={() => { selectApp(app); setOpen(false); }}
                style={{
                  width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                  padding: '0.6rem 1rem', border: 'none', background: selectedApp?.id === app.id ? 'var(--un-blue-light)' : 'none',
                  cursor: 'pointer', fontFamily: 'inherit', borderBottom: '1px solid var(--surface-3)',
                  transition: 'background 0.15s',
                }}
              >
                <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)' }}>{app.name}</span>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginTop: 2 }}>
                  {app.current_tier || 'Untiered'} · {app.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="divider" style={{ margin: '0 0.75rem 0.75rem' }} />

      {/* Step navigation */}
      <div>
        <div className="sidebar-section-label" style={{ padding: '0 1.25rem', marginBottom: '0.4rem' }}>
          9-Step Pipeline
        </div>
        {STEPS.map(step => (
          <SidebarStep key={step.num} step={step} />
        ))}
      </div>

      <div className="divider" style={{ margin: '0.75rem 0.75rem' }} />

      {/* Quick links */}
      <div>
        <div className="sidebar-section-label" style={{ padding: '0 1.25rem', marginBottom: '0.4rem' }}>Quick Links</div>
        <button className="sidebar-item" onClick={() => onNavigate('applications')}>
          <Icons.Applications />
          Applications
        </button>
        <button className="sidebar-item" onClick={() => onNavigate('risks-controls')}>
          <Icons.RisksControls />
          Risks & Controls
        </button>
      </div>
    </aside>
  );
}

function SidebarStep({ step }) {
  return (
    <button className="sidebar-item" style={{ padding: '0.4rem 0.75rem', borderRadius: 0 }}>
      <span style={{
        width: 20, height: 20, borderRadius: '50%',
        background: 'var(--un-blue-light)', color: 'var(--un-blue)',
        fontSize: '0.68rem', fontWeight: 700,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0, fontFamily: 'Syne, sans-serif',
      }}>
        {step.num}
      </span>
      <span style={{ fontSize: '0.78rem' }}>{step.label}</span>
    </button>
  );
}

AppSidebar.propTypes = {
  onNavigate: PropTypes.func.isRequired,
};

SidebarStep.propTypes = {
  step: PropTypes.shape({
    num: PropTypes.number.isRequired,
    label: PropTypes.string.isRequired,
  }).isRequired,
};
