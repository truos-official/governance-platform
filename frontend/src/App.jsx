import { useMemo, useState } from 'react';
import PropTypes from 'prop-types';
import { useApp } from './context/AppContext.jsx';
import DashboardsTab from './components/DashboardsTab.jsx';
import CatalogSearchPanel from './components/CatalogSearchPanel.jsx';
import AdminTab from './components/AdminTab.jsx';
import { normalizeRiskTier } from './components/shared/TierBadge.jsx';

const Icons = {
  Home: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 10.5 12 4l8 6.5" />
      <path d="M6 9.8V20a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9.8" />
      <path d="M10 21v-5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v5" />
    </svg>
  ),
  Dashboards: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3.5" y="4" width="17" height="16.5" rx="3" />
      <path d="M8 16V12" />
      <path d="M12 16V9" />
      <path d="M16 16V6.5" />
      <path d="M6 19h12" />
    </svg>
  ),
  Requirements: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 3.5h7l4 4V20a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1z" />
      <path d="M15 3.5V8h4" />
      <path d="M10 12h6" />
      <path d="M10 15.5h6" />
      <path d="M10 19h4" />
    </svg>
  ),
  Admin: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 7h8" />
      <path d="M4 12h16" />
      <path d="M4 17h10" />
      <circle cx="15" cy="7" r="2" />
      <circle cx="9" cy="12" r="2" />
      <circle cx="17" cy="17" r="2" />
    </svg>
  ),
  ChevronDown: () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9" /></svg>,
  Tier: () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><path d="M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6l8-4z" /></svg>,
  Compliance: () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><polyline points="20 6 9 17 4 12" /></svg>,
  Kpi: () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><polyline points="3 13 8 13 11 6 14 18 17 11 21 11" /></svg>,
};

const GOV_COLOR = '#009edb';

const STEPS = [
  { num: 1, label: 'Corporate Oversight' },
  { num: 2, label: 'Risk & Compliance' },
  { num: 3, label: 'Technical Architecture' },
  { num: 4, label: 'Data Readiness' },
  { num: 5, label: 'Data Integration' },
  { num: 6, label: 'Security' },
  { num: 7, label: 'Infrastructure' },
  { num: 8, label: 'Solution Design' },
  { num: 9, label: 'System Performance' },
];

function stepStatusTheme(status) {
  if (status === 'complete') {
    return {
      text: 'var(--success)',
      bubbleBg: 'var(--success-light)',
      bubbleColor: 'var(--success)',
      dot: 'var(--success)',
    };
  }
  if (status === 'attention') {
    return {
      text: '#b45309',
      bubbleBg: 'var(--warning-light)',
      bubbleColor: '#b45309',
      dot: '#d97706',
    };
  }
  return {
    text: 'var(--text-tertiary)',
    bubbleBg: 'var(--surface-3)',
    bubbleColor: 'var(--text-tertiary)',
    dot: 'var(--text-tertiary)',
  };
}

function fmtPercent(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A';
  }
  return `${Math.round(value * 100)}%`;
}

export default function App() {
  const { currentUser, canAdmin, selectedApp, selectApp } = useApp();
  const [activeTab, setActiveTab] = useState('dashboards');
  const [requestedStep, setRequestedStep] = useState(null);
  const [dashboardUi, setDashboardUi] = useState({
    activeStep: null,
    stepRows: [],
    snapshot: null,
    loading: false,
    error: '',
    selectedAppId: null,
    totalKpis: null,
    complianceSummary: null,
  });

  const goHome = () => {
    setActiveTab('dashboards');
    setRequestedStep(null);
    setDashboardUi((prev) => ({
      ...prev,
      activeStep: null,
      selectedAppId: null,
    }));
    selectApp(null);
  };

  const mainTabs = [
    { id: 'home', label: 'Home', Icon: Icons.Home },
    { id: 'dashboards', label: 'Enterprise Dashboard', Icon: Icons.Dashboards },
    { id: 'requirements', label: 'Governance Requirements', Icon: Icons.Requirements },
  ];
  const adminTabs = canAdmin ? [{ id: 'admin', label: 'Admin', Icon: Icons.Admin }] : [];

  const stepStatusByNum = useMemo(() => {
    const map = new Map();
    (dashboardUi.stepRows || []).forEach((row) => {
      map.set(row.num, row.status);
    });
    return map;
  }, [dashboardUi.stepRows]);

  const NavTab = ({ tab, color }) => {
    const isHomeTab = tab.id === 'home';
    const isDashboardTab = tab.id === 'dashboards';
    const isActive = isHomeTab
      ? activeTab === 'dashboards' && !selectedApp
      : isDashboardTab
        ? activeTab === 'dashboards' && Boolean(selectedApp)
        : activeTab === tab.id;

    const handleClick = () => {
      if (isHomeTab) {
        goHome();
        return;
      }
      setActiveTab(tab.id);
    };

    return (
      <button
        onClick={handleClick}
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
      case 'dashboards':
        return <DashboardsTab requestedStep={requestedStep} onDashboardUiChange={setDashboardUi} />;
      case 'requirements':
        return <CatalogSearchPanel />;
      case 'admin':
        return canAdmin ? <AdminTab onNavigate={setActiveTab} /> : null;
      default:
        return <DashboardsTab requestedStep={requestedStep} onDashboardUiChange={setDashboardUi} />;
    }
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-top">
          <div className="header-brand">
            <img src="/un-emblem.png" alt="UN Emblem" style={{ height: 34, width: 'auto' }} />
            <div>
              <h1>Universal Responsible AI Governance Solution</h1>
            </div>
          </div>

          <div className="header-actions">
            <span className="chip" style={{ fontSize: '0.72rem', background: 'var(--un-blue-light)', borderColor: 'var(--un-blue)', color: 'var(--un-blue-dark)' }}>
              {currentUser.role.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
            </span>

            <span className="header-user-name" style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
              {currentUser.name}
            </span>
          </div>
        </div>

        <div className="header-nav">
          <div className="nav-zone" style={{ paddingLeft: '0.5rem' }}>
            <div className="nav-zone-tabs">
              {mainTabs.map((tab) => <NavTab key={tab.id} tab={tab} color={GOV_COLOR} />)}
            </div>
          </div>
          {adminTabs.length > 0 && (
            <>
              <div className="nav-divider" />
              <div className="nav-zone" style={{ marginLeft: 'auto', paddingRight: '0.5rem' }}>
                <div className="nav-zone-tabs">
                  {adminTabs.map((tab) => <NavTab key={tab.id} tab={tab} color={GOV_COLOR} />)}
                </div>
              </div>
            </>
          )}
        </div>
      </header>

      <div className="app-body">
        {activeTab === 'dashboards' && (
          <AppSidebar
            onNavigate={setActiveTab}
            onStepNavigate={(stepNum) => {
              setActiveTab('dashboards');
              setRequestedStep({ stepNum, token: Date.now() });
              setDashboardUi((prev) => ({ ...prev, activeStep: stepNum }));
            }}
            activeStep={dashboardUi.activeStep}
            stepStatusByNum={stepStatusByNum}
            dashboardUi={dashboardUi}
          />
        )}

        <main style={{ flex: 1, overflowY: 'auto', padding: '1.5rem 2rem', maxWidth: activeTab === 'dashboards' ? 'none' : 1200, margin: '0 auto', width: '100%' }}>
          {renderTab()}
        </main>
      </div>

      <footer style={{ borderTop: '1px solid var(--border)', background: 'var(--surface)', padding: '0.875rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <p style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
          UN AI Governance Platform - Built by{' '}
          <a href="https://linkedin.com/in/tristangitman" target="_blank" rel="noreferrer" style={{ color: 'var(--primary)', textDecoration: 'none', fontWeight: 500 }}>
            Tristan Gitman
          </a>
          {' '} - OICT
        </p>
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', textDecoration: 'none' }}>
          API Docs {'->'}
        </a>
      </footer>
    </div>
  );
}

function AppSidebar({ onNavigate, onStepNavigate, activeStep, stepStatusByNum, dashboardUi }) {
  const { selectedApp, selectApp } = useApp();
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const loadApps = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/v1/applications');
      const data = await res.json();
      const activeApps = Array.isArray(data)
        ? data.filter((app) => app?.status === 'active')
        : [];
      setApps(activeApps);
      if (selectedApp && selectedApp.status !== 'active' && activeApps.length > 0) {
        selectApp(activeApps[0]);
      }
      setOpen(true);
    } catch {
      // no-op
    } finally {
      setLoading(false);
    }
  };

  const snapshot = dashboardUi.snapshot || {};
  const currentTier = normalizeRiskTier(snapshot.tier?.current_tier || selectedApp?.current_tier) || 'N/A';
  const complianceRate = (typeof dashboardUi.complianceSummary?.overall_pass_rate === 'number')
    ? dashboardUi.complianceSummary.overall_pass_rate
    : snapshot.compliance?.pass_rate;
  const complianceValue = (typeof complianceRate === 'number')
    ? `${fmtPercent(complianceRate)} pass`
    : 'N/A';
  const kpiTotal = typeof dashboardUi.totalKpis === 'number' && dashboardUi.totalKpis > 0
    ? dashboardUi.totalKpis
    : null;
  const kpiValue = kpiTotal !== null ? `${kpiTotal} KPIs` : 'N/A';

  return (
    <aside className="app-sidebar" style={{ padding: '1rem 0' }}>
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
            {selectedApp ? selectedApp.name : 'Select application...'}
          </span>
          <Icons.ChevronDown />
        </button>

        {open && (
          <div style={{
            position: 'absolute', zIndex: 50, left: 0, right: 0,
            margin: '0 0.75rem', background: 'var(--surface)',
            border: '1px solid var(--border)', borderRadius: 8,
            boxShadow: 'var(--shadow-3)', maxHeight: 200, overflowY: 'auto',
          }}>
            {loading && <div style={{ padding: '0.75rem 1rem', fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>Loading...</div>}
            {apps.length === 0 && !loading && (
              <div style={{ padding: '0.75rem 1rem', fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>
                No apps registered.{' '}
                <button
                  onClick={() => { setOpen(false); onNavigate('admin'); }}
                  style={{ color: 'var(--primary)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'inherit', textDecoration: 'underline' }}
                >
                  Register one {'->'}
                </button>
              </div>
            )}
            {apps.map((app) => (
              <button
                key={app.id}
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
                  {normalizeRiskTier(app.current_tier) || 'Untiered'} - {app.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="divider" style={{ margin: '0 0.75rem 0.75rem' }} />

      <div>
        <div className="sidebar-section-label" style={{ padding: '0 1.25rem', marginBottom: '0.4rem' }}>
          Governance Categories
        </div>
        {STEPS.map((step) => (
          <SidebarStep
            key={step.num}
            step={step}
            status={stepStatusByNum.get(step.num) || 'pending'}
            active={activeStep === step.num}
            onSelect={onStepNavigate}
          />
        ))}
      </div>

      <div className="divider" style={{ margin: '0.75rem 0.75rem' }} />

      <div>
        <div className="sidebar-section-label" style={{ padding: '0 1.25rem', marginBottom: '0.4rem' }}>
          STATUS
        </div>
        <div style={{ padding: '0 0.85rem', display: 'grid', gap: '0.45rem' }}>
          <StatusMetricRow
            Icon={Icons.Tier}
            label="Risk Tier"
            value={currentTier}
            legend="Risk tier from the tier engine (domain, decision type, autonomy, and observed likelihood)."
          />
          <StatusMetricRow
            Icon={Icons.Compliance}
            label="Compliance"
            value={complianceValue}
            legend="Overall pass rate across all loaded governance category KPI controls."
          />
          <StatusMetricRow
            Icon={Icons.Kpi}
            label="KPIs"
            value={kpiValue}
            legend="Total KPI controls currently loaded across governance category dashboards."
          />
        </div>
      </div>


    </aside>
  );
}

function StatusMetricRow({ Icon, label, value, legend }) {
  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: 8,
      background: 'var(--surface-2)',
      padding: '0.45rem 0.55rem',
      display: 'flex',
      alignItems: 'center',
      gap: '0.45rem',
      minHeight: 34,
    }}>
      <span
        title={legend}
        style={{
          width: 20,
          height: 20,
          borderRadius: '50%',
          background: 'var(--un-blue-light)',
          color: 'var(--un-blue)',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          cursor: 'help',
        }}
      >
        <Icon />
      </span>
      <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>{label}</span>
      <span style={{ marginLeft: 'auto', fontSize: '0.78rem', color: 'var(--text-primary)', fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function SidebarStep({ step, status, active, onSelect }) {
  const theme = stepStatusTheme(status);
  return (
    <button
      className={`sidebar-item${active ? ' active' : ''}`}
      style={{
        padding: '0.4rem 0.75rem',
        borderRadius: 0,
        borderLeft: active ? '2px solid var(--un-blue)' : '2px solid transparent',
      }}
      onClick={() => onSelect(step.num)}
    >
      <span style={{
        width: 20,
        height: 20,
        borderRadius: '50%',
        background: active ? 'var(--un-blue)' : theme.bubbleBg,
        color: active ? '#fff' : theme.bubbleColor,
        fontSize: '0.68rem',
        fontWeight: 700,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        fontFamily: 'Syne, sans-serif',
      }}>
        {step.num}
      </span>
      <span style={{ fontSize: '0.78rem', color: active ? 'var(--un-blue)' : theme.text, fontWeight: active ? 600 : 500 }}>
        {step.label}
      </span>
      <span
        title={`Status: ${status}`}
        style={{
          marginLeft: 'auto',
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: active ? 'var(--un-blue)' : theme.dot,
          flexShrink: 0,
        }}
      />
    </button>
  );
}

StatusMetricRow.propTypes = {
  Icon: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  value: PropTypes.string.isRequired,
  legend: PropTypes.string.isRequired,
};

AppSidebar.propTypes = {
  onNavigate: PropTypes.func.isRequired,
  onStepNavigate: PropTypes.func.isRequired,
  activeStep: PropTypes.number,
  stepStatusByNum: PropTypes.instanceOf(Map),
  dashboardUi: PropTypes.shape({
    totalKpis: PropTypes.number,
    complianceSummary: PropTypes.shape({
      overall_pass_rate: PropTypes.number,
      evaluated_count: PropTypes.number,
      pass_count: PropTypes.number,
      fail_count: PropTypes.number,
      step1_fail_count: PropTypes.number,
      step1_total: PropTypes.number,
      step2_total: PropTypes.number,
      step2_pass_rate: PropTypes.number,
    }),
    snapshot: PropTypes.shape({
      tier: PropTypes.object,
      compliance: PropTypes.object,
      telemetry: PropTypes.object,
    }),
  }),
};

AppSidebar.defaultProps = {
  activeStep: null,
  stepStatusByNum: new Map(),
  dashboardUi: {
    totalKpis: null,
    complianceSummary: null,
    snapshot: null,
  },
};

SidebarStep.propTypes = {
  step: PropTypes.shape({
    num: PropTypes.number.isRequired,
    label: PropTypes.string.isRequired,
  }).isRequired,
  status: PropTypes.oneOf(['complete', 'attention', 'pending']),
  active: PropTypes.bool,
  onSelect: PropTypes.func.isRequired,
};

SidebarStep.defaultProps = {
  status: 'pending',
  active: false,
};








