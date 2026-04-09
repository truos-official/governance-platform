import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client.js';
import CatalogSearchPanel from './CatalogSearchPanel.jsx';

const PAGE_SIZE = 25;

function buildControlParams({ domain, tier, skip }) {
  const params = new URLSearchParams();
  params.set('skip', String(skip));
  params.set('limit', String(PAGE_SIZE));
  if (domain.trim()) {
    params.set('domain', domain.trim());
  }
  if (tier) {
    params.set('tier', tier);
  }
  return params.toString();
}

export default function RisksControlsTab() {
  const [domain, setDomain] = useState('');
  const [tier, setTier] = useState('');
  const [skip, setSkip] = useState(0);

  const [controls, setControls] = useState([]);
  const [totalControls, setTotalControls] = useState(0);
  const [loadingControls, setLoadingControls] = useState(false);
  const [controlsError, setControlsError] = useState('');

  const [selectedControlId, setSelectedControlId] = useState('');
  const [selectedControl, setSelectedControl] = useState(null);
  const [requirements, setRequirements] = useState([]);
  const [requirementsTotal, setRequirementsTotal] = useState(0);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState('');

  const canPrev = skip > 0;
  const canNext = skip + PAGE_SIZE < totalControls;

  const pageLabel = useMemo(() => {
    if (totalControls === 0) {
      return '0 results';
    }
    const start = skip + 1;
    const end = Math.min(skip + controls.length, totalControls);
    return `${start}-${end} of ${totalControls}`;
  }, [controls.length, skip, totalControls]);

  const loadControls = async (nextSkip = 0, overrides = {}) => {
    const nextDomain = overrides.domain ?? domain;
    const nextTier = overrides.tier ?? tier;

    setLoadingControls(true);
    setControlsError('');
    try {
      const params = buildControlParams({ domain: nextDomain, tier: nextTier, skip: nextSkip });
      const payload = await api.getControls(params);
      setControls(payload.items || []);
      setTotalControls(payload.total || 0);
      setSkip(nextSkip);

      if (payload.items?.length === 0) {
        setSelectedControlId('');
        setSelectedControl(null);
        setRequirements([]);
        setRequirementsTotal(0);
      }
    } catch (e) {
      setControlsError(e.message || 'Failed to load controls');
      setControls([]);
      setTotalControls(0);
    } finally {
      setLoadingControls(false);
    }
  };

  const loadControlDetail = async (controlId) => {
    setSelectedControlId(controlId);
    setLoadingDetail(true);
    setDetailError('');
    setSelectedControl(null);
    setRequirements([]);
    setRequirementsTotal(0);

    try {
      const [controlResult, reqsResult] = await Promise.all([
        api.getControl(controlId),
        api.getRequirements(`control_id=${encodeURIComponent(controlId)}&limit=200`),
      ]);
      setSelectedControl(controlResult);
      setRequirements(reqsResult.items || []);
      setRequirementsTotal(reqsResult.total || 0);
    } catch (e) {
      setDetailError(e.message || 'Failed to load control detail');
    } finally {
      setLoadingDetail(false);
    }
  };

  useEffect(() => {
    loadControls(0);
  }, []);

  return (
    <div>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div className="card-title">
          Risks & Controls
          <span className="badge badge-unblue">Live Catalog Integration</span>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
          Phase 5 roadmap step: connect catalog read models for governance Step 3 (architecture) and Step 4 (data readiness).
        </p>
      </div>

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.92rem' }}>Controls</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              Query: GET /catalog/controls
            </div>
          </div>

          <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--border)', display: 'grid', gap: '0.6rem' }}>
            <input
              className="form-input"
              placeholder="Domain filter (optional)"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            />
            <select className="form-select" value={tier} onChange={(e) => setTier(e.target.value)}>
              <option value="">All Tiers</option>
              <option value="FOUNDATION">FOUNDATION</option>
              <option value="COMMON">COMMON</option>
              <option value="SPECIALIZED">SPECIALIZED</option>
            </select>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button className="btn btn-primary btn-sm" onClick={() => loadControls(0)} disabled={loadingControls}>
                {loadingControls ? 'Loading...' : 'Apply Filters'}
              </button>
              <button
                className="btn btn-outline btn-sm"
                onClick={() => {
                  setDomain('');
                  setTier('');
                  setSkip(0);
                  loadControls(0, { domain: '', tier: '' });
                }}
                disabled={loadingControls}
              >
                Reset
              </button>
            </div>
          </div>

          {controlsError && <div className="alert alert-danger" style={{ margin: '1rem' }}>{controlsError}</div>}

          <div style={{ padding: '0.75rem 1.25rem', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.76rem', color: 'var(--text-tertiary)' }}>{pageLabel}</span>
            <div style={{ display: 'flex', gap: '0.35rem' }}>
              <button className="btn btn-outline btn-xs" disabled={!canPrev || loadingControls} onClick={() => loadControls(skip - PAGE_SIZE)}>Prev</button>
              <button className="btn btn-outline btn-xs" disabled={!canNext || loadingControls} onClick={() => loadControls(skip + PAGE_SIZE)}>Next</button>
            </div>
          </div>

          <div style={{ maxHeight: 560, overflowY: 'auto' }}>
            {controls.length === 0 && !loadingControls ? (
              <div style={{ padding: '1rem 1.25rem', fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>
                No controls found for current filter.
              </div>
            ) : (
              <table className="table" style={{ marginBottom: 0 }}>
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Title</th>
                    <th>Tier</th>
                  </tr>
                </thead>
                <tbody>
                  {controls.map((control) => (
                    <tr
                      key={control.id}
                      onClick={() => loadControlDetail(control.id)}
                      style={{ cursor: 'pointer', background: selectedControlId === control.id ? 'var(--un-blue-light)' : undefined }}
                    >
                      <td style={{ fontWeight: 700 }}>{control.code}</td>
                      <td>{control.title}</td>
                      <td>{control.tier || 'N/A'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.92rem' }}>Control Detail</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              Queries: GET /catalog/controls/{'{id}'} + GET /catalog/requirements?control_id={"{id}"}
            </div>
          </div>

          {!selectedControlId && (
            <div style={{ padding: '1rem 1.25rem', color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>
              Select a control from the left panel.
            </div>
          )}

          {loadingDetail && (
            <div style={{ padding: '1rem 1.25rem', color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>
              Loading detail...
            </div>
          )}

          {detailError && (
            <div className="alert alert-danger" style={{ margin: '1rem' }}>
              {detailError}
            </div>
          )}

          {selectedControl && !loadingDetail && !detailError && (
            <div>
              <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--border)', display: 'grid', gap: '0.45rem' }}>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                  <span className="badge badge-unblue">{selectedControl.code}</span>
                  <span className="badge badge-grey">{selectedControl.tier || 'N/A'}</span>
                  <span className="badge badge-grey">{selectedControl.domain || 'N/A'}</span>
                </div>
                <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.95rem' }}>
                  {selectedControl.title}
                </div>
                <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                  {selectedControl.description || 'No description'}
                </div>
              </div>

              <div style={{ padding: '0.75rem 1.25rem', borderBottom: '1px solid var(--border)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                Linked requirements: {requirementsTotal}
              </div>

              <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                {requirements.length === 0 ? (
                  <div style={{ padding: '1rem 1.25rem', color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>
                    No linked requirements found.
                  </div>
                ) : (
                  <table className="table" style={{ marginBottom: 0 }}>
                    <thead>
                      <tr>
                        <th>Requirement</th>
                        <th>Regulation</th>
                        <th>Jurisdiction</th>
                      </tr>
                    </thead>
                    <tbody>
                      {requirements.map((req) => (
                        <tr key={req.id}>
                          <td>
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                              <span style={{ fontWeight: 700 }}>{req.code}</span>
                              <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>{req.title}</span>
                            </div>
                          </td>
                          <td>{req.regulation_title || 'N/A'}</td>
                          <td>{req.jurisdiction || 'N/A'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <CatalogSearchPanel />
      </div>
    </div>
  );
}
