import { useEffect, useMemo, useState } from 'react';
import PropTypes from 'prop-types';
import { api } from '../api/client.js';
import { useApp } from '../context/AppContext.jsx';
import { TierBadge } from './shared/TierBadge.jsx';

function fmtDate(value) {
  if (!value) {
    return 'N/A';
  }
  return new Date(value).toLocaleDateString();
}

export default function ApplicationsTab({ onNavigate }) {
  const { selectedApp, selectApp } = useApp();
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');

  const activeCount = useMemo(
    () => apps.filter((a) => a.status === 'active').length,
    [apps],
  );

  const loadApps = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.listApplications();
      setApps(data);
    } catch (e) {
      setError(e.message || 'Failed to load applications');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadApps();
  }, []);

  const handleSelect = (app) => {
    selectApp(app);
  };

  const handleDisconnect = async (appId) => {
    setBusyId(appId);
    setError('');
    try {
      const updated = await api.disconnectApplication(appId);
      setApps((prev) => prev.map((app) => (app.id === appId ? updated : app)));
      if (selectedApp?.id === appId) {
        selectApp(updated);
      }
    } catch (e) {
      setError(e.message || 'Failed to disconnect application');
    } finally {
      setBusyId('');
    }
  };

  return (
    <div>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div className="card-title">
          Applications
          <span className="badge badge-unblue">{activeCount}/{apps.length} Active</span>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.83rem' }}>
          Phase 5 focus: manage connected applications and choose the active context used by governance workflows.
        </p>
      </div>

      <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 1.25rem', borderBottom: '1px solid var(--border)' }}>
          <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
            Registered applications
          </span>
          <button className="btn btn-outline btn-sm" onClick={loadApps} disabled={loading}>
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        {error && (
          <div className="alert alert-danger" style={{ margin: '1rem' }}>
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ padding: '1.25rem', color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>
            Loading applications...
          </div>
        ) : apps.length === 0 ? (
          <div style={{ padding: '1.25rem', color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>
            No applications found. Register one via POST /api/v1/applications and refresh.
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Tier</th>
                <th>Status</th>
                <th>Domain</th>
                <th>Registered</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {apps.map((app) => {
                const isSelected = selectedApp?.id === app.id;
                const isBusy = busyId === app.id;
                return (
                  <tr key={app.id} style={isSelected ? { background: 'var(--un-blue-light)' } : undefined}>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ fontWeight: 600 }}>{app.name}</span>
                        <span style={{ color: 'var(--text-tertiary)', fontSize: '0.73rem' }}>{app.id}</span>
                      </div>
                    </td>
                    <td><TierBadge tier={app.current_tier} /></td>
                    <td>
                      <span className={`badge ${app.status === 'active' ? 'badge-green' : 'badge-grey'}`}>
                        {app.status}
                      </span>
                    </td>
                    <td>{app.domain || 'N/A'}</td>
                    <td>{fmtDate(app.registered_at)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <button className="btn btn-outline btn-xs" onClick={() => handleSelect(app)}>
                          {isSelected ? 'Selected' : 'Select'}
                        </button>
                        <button className="btn btn-primary btn-xs" onClick={() => { handleSelect(app); onNavigate('governance'); }}>
                          Open Governance
                        </button>
                        {app.status === 'active' && (
                          <button
                            className="btn btn-ghost btn-xs"
                            onClick={() => handleDisconnect(app.id)}
                            disabled={isBusy}
                            style={{ color: 'var(--danger)' }}
                          >
                            {isBusy ? 'Disconnecting...' : 'Disconnect'}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

ApplicationsTab.propTypes = {
  onNavigate: PropTypes.func.isRequired,
};
