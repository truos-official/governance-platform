import { useCallback, useEffect, useMemo, useState } from 'react';
import PropTypes from 'prop-types';
import { api } from '../api/client.js';
import { useApp } from '../context/AppContext.jsx';
import { TierBadge } from './shared/TierBadge.jsx';

const STEP_DEFS = [
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

function StepStatus({ status }) {
  if (status === 'complete') {
    return <span className="badge badge-green">Complete</span>;
  }
  if (status === 'attention') {
    return <span className="badge badge-yellow">Attention</span>;
  }
  return <span className="badge badge-grey">Pending</span>;
}

StepStatus.propTypes = {
  status: PropTypes.string.isRequired,
};

function fmtPercent(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A';
  }
  return `${Math.round(value * 100)}%`;
}

export default function GovernanceTab() {
  const { selectedApp } = useApp();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeStep, setActiveStep] = useState(null);
  const [loadingStepDetail, setLoadingStepDetail] = useState(false);
  const [stepDetailError, setStepDetailError] = useState('');
  const [detailCache, setDetailCache] = useState({
    controlsCatalog: null,
    complianceControls: null,
    benchmarks: null,
    alignment: null,
    history: null,
    recommendations: null,
  });
  const [snapshot, setSnapshot] = useState({
    tier: null,
    compliance: null,
    telemetry: null,
  });

  const loadSnapshot = useCallback(async () => {
    if (!selectedApp?.id) {
      return;
    }

    setLoading(true);
    setError('');

    const [tierResult, complianceResult, telemetryResult] = await Promise.allSettled([
      api.getTier(selectedApp.id),
      api.getCompliance(selectedApp.id),
      api.getTelemetryStatus(),
    ]);

    const next = { tier: null, compliance: null, telemetry: null };
    const failed = [];

    if (tierResult.status === 'fulfilled') {
      next.tier = tierResult.value;
    } else {
      failed.push('tier');
    }

    if (complianceResult.status === 'fulfilled') {
      next.compliance = complianceResult.value;
    } else {
      failed.push('compliance');
    }

    if (telemetryResult.status === 'fulfilled') {
      next.telemetry = telemetryResult.value;
    } else {
      failed.push('telemetry');
    }

    setSnapshot(next);
    if (failed.length > 0) {
      setError(`Some live data is unavailable: ${failed.join(', ')}`);
    }
    setLoading(false);
  }, [selectedApp?.id]);

  useEffect(() => {
    loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    setActiveStep(null);
    setLoadingStepDetail(false);
    setStepDetailError('');
    setDetailCache({
      controlsCatalog: null,
      complianceControls: null,
      benchmarks: null,
      alignment: null,
      history: null,
      recommendations: null,
    });
  }, [selectedApp?.id]);

  const loadStepDetail = useCallback(async (stepNum) => {
    setActiveStep(stepNum);
    setStepDetailError('');

    if (!selectedApp?.id || (stepNum !== 3 && stepNum !== 4 && stepNum !== 7 && stepNum !== 8 && stepNum !== 9)) {
      return;
    }

    if (stepNum === 3 && detailCache.controlsCatalog && detailCache.recommendations) {
      return;
    }

    if (stepNum === 4 && detailCache.complianceControls) {
      return;
    }

    if (stepNum === 7 && detailCache.benchmarks) {
      return;
    }

    if (stepNum === 8 && detailCache.alignment) {
      return;
    }

    if (stepNum === 9 && detailCache.history && detailCache.recommendations) {
      return;
    }

    setLoadingStepDetail(true);
    try {
      if (stepNum === 3) {
        const [controlsResult, recsResult] = await Promise.allSettled([
          api.getControls('limit=25'),
          api.getRecommendations(selectedApp.id),
        ]);

        const failed = [];
        if (controlsResult.status === 'fulfilled') {
          setDetailCache((prev) => ({ ...prev, controlsCatalog: controlsResult.value }));
        } else {
          failed.push('controls_catalog');
        }

        if (recsResult.status === 'fulfilled') {
          setDetailCache((prev) => ({ ...prev, recommendations: recsResult.value }));
        } else {
          failed.push('recommendations');
        }

        if (failed.length > 0) {
          setStepDetailError(`Some step 3 data is unavailable: ${failed.join(', ')}`);
        }
      } else if (stepNum === 4) {
        const result = await api.getComplianceControls(selectedApp.id);
        setDetailCache((prev) => ({ ...prev, complianceControls: result }));
      } else if (stepNum === 7) {
        const result = await api.getBenchmarks(selectedApp.id);
        setDetailCache((prev) => ({ ...prev, benchmarks: result }));
      } else if (stepNum === 8) {
        const result = await api.getAlignment(selectedApp.id);
        setDetailCache((prev) => ({ ...prev, alignment: result }));
      } else if (stepNum === 9) {
        const [historyResult, recsResult] = await Promise.allSettled([
          api.getTierHistory(selectedApp.id),
          api.getRecommendations(selectedApp.id),
        ]);

        const failed = [];
        if (historyResult.status === 'fulfilled') {
          setDetailCache((prev) => ({ ...prev, history: historyResult.value }));
        } else {
          failed.push('tier_history');
        }

        if (recsResult.status === 'fulfilled') {
          setDetailCache((prev) => ({ ...prev, recommendations: recsResult.value }));
        } else {
          failed.push('recommendations');
        }

        if (failed.length > 0) {
          setStepDetailError(`Some step 9 data is unavailable: ${failed.join(', ')}`);
        }
      }
    } catch (e) {
      setStepDetailError(e.message || 'Failed to load step detail');
    } finally {
      setLoadingStepDetail(false);
    }
  }, [detailCache.alignment, detailCache.benchmarks, detailCache.complianceControls, detailCache.controlsCatalog, detailCache.history, detailCache.recommendations, selectedApp?.id]);

  const fmtNum = useCallback((value, digits = 3) => {
    if (typeof value !== 'number' || Number.isNaN(value)) {
      return 'N/A';
    }
    return value.toFixed(digits);
  }, []);

  const fmtDateTime = useCallback((value) => {
    if (!value) {
      return 'N/A';
    }
    return new Date(value).toLocaleString();
  }, []);

  const stepRows = useMemo(() => {
    const telemetryReadings = snapshot.telemetry?.total_readings || 0;
    const hasCompliance = Boolean(snapshot.compliance);
    const hasTier = Boolean(snapshot.tier);

    return STEP_DEFS.map((step) => {
      if (step.num === 1) {
        return { ...step, status: selectedApp ? 'complete' : 'pending', note: selectedApp ? `Registered app: ${selectedApp.name}` : 'No selected app' };
      }
      if (step.num === 2) {
        return { ...step, status: hasTier ? 'complete' : 'attention', note: hasTier ? `Tier assigned: ${snapshot.tier.current_tier}` : 'Tier unavailable' };
      }
      if (step.num === 3) {
        if (detailCache.controlsCatalog || detailCache.recommendations) {
          const controlCount = detailCache.controlsCatalog?.total || 0;
          const recCount = detailCache.recommendations?.recommendations?.length || 0;
          return {
            ...step,
            status: controlCount > 0 || recCount > 0 ? 'complete' : 'attention',
            note: `Catalog controls: ${controlCount} | recommendations: ${recCount}`,
          };
        }
        return {
          ...step,
          status: hasTier ? 'attention' : 'pending',
          note: hasTier ? 'Click row to load controls architecture map' : 'Requires tier assignment first',
        };
      }
      if (step.num === 4) {
        if (detailCache.complianceControls) {
          const total = detailCache.complianceControls.length || 0;
          const pass = detailCache.complianceControls.filter((c) => c.result === 'PASS').length;
          return {
            ...step,
            status: total > 0 ? 'complete' : 'attention',
            note: `Evidence rows: ${total} | pass: ${pass}`,
          };
        }
        return {
          ...step,
          status: hasCompliance ? 'attention' : 'pending',
          note: hasCompliance ? 'Click row to load control evidence feed' : 'Compliance summary required first',
        };
      }
      if (step.num === 5) {
        return {
          ...step,
          status: telemetryReadings > 0 ? 'complete' : 'attention',
          note: telemetryReadings > 0 ? `${telemetryReadings} readings ingested` : 'No readings yet',
        };
      }
      if (step.num === 6) {
        return {
          ...step,
          status: hasCompliance ? 'complete' : 'attention',
          note: hasCompliance ? `Pass rate: ${fmtPercent(snapshot.compliance.pass_rate)}` : 'Compliance unavailable',
        };
      }
      if (step.num === 7) {
        if (detailCache.benchmarks) {
          if (detailCache.benchmarks.available) {
            return {
              ...step,
              status: 'complete',
              note: `Peer cohort: ${detailCache.benchmarks.peer_count} | metrics: ${detailCache.benchmarks.benchmarks?.length || 0}`,
            };
          }
          return {
            ...step,
            status: 'attention',
            note: detailCache.benchmarks.reason || 'Benchmarks not available yet',
          };
        }
        return {
          ...step,
          status: hasTier ? 'attention' : 'pending',
          note: hasTier ? 'Click row to load peer benchmark metrics' : 'Requires tier assignment first',
        };
      }
      if (step.num === 8) {
        if (detailCache.alignment) {
          return {
            ...step,
            status: 'complete',
            note: `Alignment score: ${Math.round(detailCache.alignment.alignment_score || 0)}`,
          };
        }
        return {
          ...step,
          status: hasTier ? 'attention' : 'pending',
          note: hasTier ? 'Click row to load alignment breakdown' : 'Requires tier assignment first',
        };
      }
      if (step.num === 9) {
        if (detailCache.history || detailCache.recommendations) {
          const transitions = detailCache.history?.length || 0;
          const recs = detailCache.recommendations?.recommendations?.length || 0;
          return {
            ...step,
            status: recs > 0 || transitions > 0 ? 'complete' : 'attention',
            note: `Transitions: ${transitions} | recommendations: ${recs}`,
          };
        }
        return {
          ...step,
          status: hasTier && hasCompliance ? 'attention' : 'pending',
          note: hasTier && hasCompliance ? 'Click row to load tier history and recommendations' : 'Waiting for upstream steps',
        };
      }
      return { ...step, status: 'pending', note: 'Panel wiring next increment' };
    });
  }, [detailCache.alignment, detailCache.benchmarks, detailCache.complianceControls, detailCache.controlsCatalog, detailCache.history, detailCache.recommendations, selectedApp, snapshot]);

  if (!selectedApp) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
        <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
          No application selected
        </p>
        <p style={{ color: 'var(--text-tertiary)', fontSize: '0.85rem' }}>
          Select a connected application from the sidebar to view its governance pipeline.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div className="card-title">
          Governance Pipeline - {selectedApp.name}
          <button className="btn btn-outline btn-sm" onClick={loadSnapshot} disabled={loading}>
            {loading ? 'Refreshing...' : 'Refresh Snapshot'}
          </button>
        </div>

        {error && <div className="alert alert-warning">{error}</div>}

        <div className="kpi-grid" style={{ marginTop: '0.75rem' }}>
          <div className="kpi-card">
            <div className="kpi-label">Current Tier</div>
            <div style={{ marginTop: '0.6rem' }}>
              <TierBadge tier={snapshot.tier?.current_tier || selectedApp.current_tier} />
            </div>
            <div className="kpi-source">Raw score: {snapshot.tier ? snapshot.tier.raw_score.toFixed(3) : 'N/A'}</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-label">Compliance</div>
            <div className="kpi-value" style={{ fontSize: '1.6rem' }}>
              {snapshot.compliance ? fmtPercent(snapshot.compliance.pass_rate) : 'N/A'}
            </div>
            <div className="kpi-source">
              {snapshot.compliance
                ? `${snapshot.compliance.pass_count} pass / ${snapshot.compliance.fail_count} fail / ${snapshot.compliance.insufficient_count} no data`
                : 'Compliance data unavailable'}
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-label">Telemetry Pipeline</div>
            <div className="kpi-value" style={{ fontSize: '1.6rem' }}>
              {snapshot.telemetry ? snapshot.telemetry.total_readings : 'N/A'}
            </div>
            <div className="kpi-source">
              {snapshot.telemetry
                ? `Status: ${snapshot.telemetry.status} | production_only=${String(snapshot.telemetry.production_only)}`
                : 'Telemetry status unavailable'}
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.95rem' }}>
            9-Step Pipeline Status
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
            Live status from integrated endpoints. Remaining steps will be wired in the next increments.
          </div>
        </div>

        <table className="table" style={{ marginBottom: 0 }}>
          <thead>
            <tr>
              <th>Step</th>
              <th>Area</th>
              <th>Status</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {stepRows.map((row) => (
              <tr
                key={row.num}
                onClick={() => loadStepDetail(row.num)}
                style={activeStep === row.num ? { background: 'var(--un-blue-light)' } : undefined}
              >
                <td>{row.num}</td>
                <td>{row.label}</td>
                <td><StepStatus status={row.status} /></td>
                <td style={{ color: 'var(--text-secondary)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                    <span>{row.note}</span>
                    {(row.num === 3 || row.num === 4 || row.num === 7 || row.num === 8 || row.num === 9) && (
                      <span className="badge badge-unblue">View</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {(activeStep === 3 || activeStep === 4 || activeStep === 7 || activeStep === 8 || activeStep === 9) && (
          <div style={{ borderTop: '1px solid var(--border)', padding: '1rem 1.25rem' }}>
            <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, marginBottom: '0.5rem' }}>
              {activeStep === 3
                ? 'Step 3 Detail: Controls Architecture'
                : activeStep === 4
                  ? 'Step 4 Detail: Data Readiness Evidence'
                  : activeStep === 7
                    ? 'Step 7 Detail: Peer Benchmarks'
                    : activeStep === 8
                      ? 'Step 8 Detail: Alignment Score'
                      : 'Step 9 Detail: Trends & Recommendations'}
            </div>

            {loadingStepDetail && (
              <div style={{ fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>
                Loading detail...
              </div>
            )}

            {stepDetailError && (
              <div className="alert alert-danger" style={{ marginBottom: 0 }}>
                {stepDetailError}
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 3 && (
              <div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                  <span className="badge badge-grey">Catalog controls: {detailCache.controlsCatalog?.total || 0}</span>
                  <span className="badge badge-grey">Recommended controls: {detailCache.recommendations?.recommendations?.length || 0}</span>
                </div>

                <div className="grid-2" style={{ alignItems: 'start' }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.82rem', marginBottom: '0.45rem' }}>
                      Top Catalog Controls
                    </div>
                    {detailCache.controlsCatalog?.items?.length ? (
                      <table className="table" style={{ marginBottom: 0 }}>
                        <thead>
                          <tr>
                            <th>Code</th>
                            <th>Domain</th>
                            <th>Tier</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detailCache.controlsCatalog.items.slice(0, 12).map((control) => (
                            <tr key={control.id}>
                              <td>
                                <div style={{ display: 'flex', flexDirection: 'column' }}>
                                  <span style={{ fontWeight: 700 }}>{control.code}</span>
                                  <span style={{ color: 'var(--text-secondary)', fontSize: '0.74rem' }}>{control.title}</span>
                                </div>
                              </td>
                              <td>{control.domain || 'N/A'}</td>
                              <td>{control.tier || 'N/A'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                        No catalog controls available.
                      </div>
                    )}
                  </div>

                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.82rem', marginBottom: '0.45rem' }}>
                      Architecture Recommendations
                    </div>
                    {detailCache.recommendations?.recommendations?.length ? (
                      <table className="table" style={{ marginBottom: 0 }}>
                        <thead>
                          <tr>
                            <th>Code</th>
                            <th>Tier</th>
                            <th>Reg Density</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detailCache.recommendations.recommendations.slice(0, 12).map((rec) => (
                            <tr key={rec.control_id}>
                              <td>
                                <div style={{ display: 'flex', flexDirection: 'column' }}>
                                  <span style={{ fontWeight: 700 }}>{rec.code}</span>
                                  <span style={{ color: 'var(--text-secondary)', fontSize: '0.74rem' }}>{rec.title}</span>
                                </div>
                              </td>
                              <td>{rec.tier || 'N/A'}</td>
                              <td>{rec.regulatory_density ?? 0}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                        No recommendations returned.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 4 && (
              <div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                  <span className="badge badge-grey">Control evidence rows: {detailCache.complianceControls?.length || 0}</span>
                  <span className="badge badge-green">
                    PASS: {(detailCache.complianceControls || []).filter((row) => row.result === 'PASS').length}
                  </span>
                  <span className="badge badge-red">
                    FAIL: {(detailCache.complianceControls || []).filter((row) => row.result === 'FAIL').length}
                  </span>
                </div>

                {detailCache.complianceControls?.length ? (
                  <table className="table" style={{ marginBottom: 0 }}>
                    <thead>
                      <tr>
                        <th>Control ID</th>
                        <th>Metric</th>
                        <th>Result</th>
                        <th>Value</th>
                        <th>Evidence Timestamp</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailCache.complianceControls.slice(0, 20).map((row, idx) => (
                        <tr key={`${row.control_id}-${idx}`}>
                          <td>{row.control_id}</td>
                          <td>{row.metric_name}</td>
                          <td>
                            <span className={`badge ${row.result === 'PASS' ? 'badge-green' : row.result === 'FAIL' ? 'badge-red' : 'badge-grey'}`}>
                              {row.result}
                            </span>
                          </td>
                          <td>{fmtNum(row.value)}</td>
                          <td>{fmtDateTime(row.evidence_ts)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                    No compliance control evidence available.
                  </div>
                )}
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 7 && detailCache.benchmarks && (
              <div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.7rem' }}>
                  <span className="badge badge-grey">Tier: {detailCache.benchmarks.tier || 'N/A'}</span>
                  <span className="badge badge-grey">Peer Count: {detailCache.benchmarks.peer_count ?? 0}</span>
                  <span className={`badge ${detailCache.benchmarks.available ? 'badge-green' : 'badge-yellow'}`}>
                    {detailCache.benchmarks.available ? 'Available' : 'Limited'}
                  </span>
                </div>

                {!detailCache.benchmarks.available && (
                  <div className="alert alert-warning">
                    {detailCache.benchmarks.reason || 'Benchmarks currently unavailable'}
                  </div>
                )}

                {detailCache.benchmarks.benchmarks?.length > 0 && (
                  <table className="table" style={{ marginBottom: 0 }}>
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th>App Value</th>
                        <th>Peer Avg</th>
                        <th>Delta</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailCache.benchmarks.benchmarks.slice(0, 12).map((metric) => (
                        <tr key={metric.metric_name}>
                          <td>{metric.metric_name}</td>
                          <td>{fmtNum(metric.app_value)}</td>
                          <td>{fmtNum(metric.peer_avg)}</td>
                          <td className={metric.delta > 0 ? 'delta-positive' : metric.delta < 0 ? 'delta-negative' : 'delta-neutral'}>
                            {fmtNum(metric.delta)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 8 && detailCache.alignment && (
              <div>
                <div className="kpi-grid" style={{ marginBottom: '0.75rem' }}>
                  <div className="kpi-card">
                    <div className="kpi-label">Alignment Score</div>
                    <div className="kpi-value" style={{ fontSize: '1.7rem' }}>
                      {Math.round(detailCache.alignment.alignment_score || 0)}
                    </div>
                    <div className="kpi-source">Cohort: {detailCache.alignment.peer_cohort_size ?? 0}</div>
                  </div>
                  <div className="kpi-card">
                    <div className="kpi-label">Weights</div>
                    <div className="kpi-source">Peer: {fmtNum(detailCache.alignment.weights?.peer_adoption_rate, 2)}</div>
                    <div className="kpi-source">Regulatory: {fmtNum(detailCache.alignment.weights?.regulatory_density, 2)}</div>
                    <div className="kpi-source">Trend: {fmtNum(detailCache.alignment.weights?.trend_velocity, 2)}</div>
                  </div>
                </div>

                <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.7rem' }}>
                  {detailCache.alignment.commentary || 'No commentary returned'}
                </div>

                {detailCache.alignment.controls?.length > 0 && (
                  <table className="table" style={{ marginBottom: 0 }}>
                    <thead>
                      <tr>
                        <th>Control ID</th>
                        <th>Adopted</th>
                        <th>Control Weight</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailCache.alignment.controls.slice(0, 12).map((control) => (
                        <tr key={control.control_id}>
                          <td>{control.control_id}</td>
                          <td>
                            <span className={`badge ${control.adopted ? 'badge-green' : 'badge-grey'}`}>
                              {control.adopted ? 'Yes' : 'No'}
                            </span>
                          </td>
                          <td>{fmtNum(control.control_weight)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 9 && (
              <div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                  <span className="badge badge-grey">
                    Tier transitions: {detailCache.history?.length || 0}
                  </span>
                  <span className="badge badge-grey">
                    Recommendations: {detailCache.recommendations?.recommendations?.length || 0}
                  </span>
                  {detailCache.recommendations?.message && (
                    <span className="badge badge-green">{detailCache.recommendations.message}</span>
                  )}
                </div>

                <div className="grid-2" style={{ alignItems: 'start' }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.82rem', marginBottom: '0.45rem' }}>
                      Tier History
                    </div>
                    {detailCache.history?.length ? (
                      <table className="table" style={{ marginBottom: 0 }}>
                        <thead>
                          <tr>
                            <th>Changed At</th>
                            <th>From</th>
                            <th>To</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detailCache.history.slice(0, 12).map((entry) => (
                            <tr key={entry.id}>
                              <td>{fmtDateTime(entry.changed_at)}</td>
                              <td>{entry.previous_tier || 'N/A'}</td>
                              <td>{entry.new_tier}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                        No tier transitions available.
                      </div>
                    )}
                  </div>

                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.82rem', marginBottom: '0.45rem' }}>
                      Top Recommended Controls
                    </div>
                    {detailCache.recommendations?.recommendations?.length ? (
                      <table className="table" style={{ marginBottom: 0 }}>
                        <thead>
                          <tr>
                            <th>Code</th>
                            <th>Tier</th>
                            <th>Reg Density</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detailCache.recommendations.recommendations.slice(0, 12).map((rec) => (
                            <tr key={rec.control_id}>
                              <td>
                                <div style={{ display: 'flex', flexDirection: 'column' }}>
                                  <span style={{ fontWeight: 700 }}>{rec.code}</span>
                                  <span style={{ color: 'var(--text-secondary)', fontSize: '0.74rem' }}>{rec.title}</span>
                                </div>
                              </td>
                              <td>{rec.tier || 'N/A'}</td>
                              <td>{rec.regulatory_density ?? 0}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>
                        No pending recommendations.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
