const BASE = 'http://localhost:8000/api/v1';

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  // Applications
  listApplications:      ()        => request('GET',   '/applications'),
  getApplication:        (id)      => request('GET',   `/applications/${id}`),
  registerApplication:   (body)    => request('POST',  '/applications', body),
  updateApplication:     (id, b)   => request('PATCH', `/applications/${id}`, b),
  disconnectApplication: (id)      => request('PATCH', `/applications/${id}/disconnect`),
  getApplicationRequirements: (id, params='') => request('GET', `/applications/${id}/requirements?${params}`),
  setApplicationRequirements: (id, requirementIds=[]) => request('PUT', `/applications/${id}/requirements`, { requirement_ids: requirementIds }),
  getApplicationInterpretations: (id) => request('GET', `/applications/${id}/interpretations`),
  createApplicationInterpretation: (id, body) => request('POST', `/applications/${id}/interpretations`, body),
  patchApplicationInterpretation: (id, interpretationId, body) => request('PATCH', `/applications/${id}/interpretations/${interpretationId}`, body),
  getApplicationDashboardStep: (id, step) => request('GET', `/applications/${id}/dashboard/${step}`),

  // Tier
  getTier:        (id) => request('GET', `/applications/${id}/tier`),
  getTierHistory: (id) => request('GET', `/applications/${id}/tier/history`),

  // Compliance
  getCompliance:         (id) => request('GET',  `/applications/${id}/compliance`),
  recalcCompliance:      (id) => request('POST', `/applications/${id}/compliance`),
  getComplianceControls: (id) => request('GET',  `/applications/${id}/compliance/controls`),

  // Alignment + peers
  getAlignment:       (id) => request('GET', `/applications/${id}/alignment`),
  getBenchmarks:      (id) => request('GET', `/applications/${id}/benchmarks`),
  getRecommendations: (id) => request('GET', `/applications/${id}/recommendations`),

  // Telemetry
  getTelemetryStatus: () => request('GET', '/telemetry/status'),

  // Catalog
  getControls:         (params='') => request('GET', `/catalog/controls?${params}`),
  getControl:          (id)        => request('GET', `/catalog/controls/${id}`),
  getRequirements:     (params='') => request('GET', `/catalog/requirements?${params}`),
  getRequirement:      (id)        => request('GET', `/catalog/requirements/${id}`),
  getRegulations:      (params='') => request('GET', `/catalog/regulations?${params}`),
  getCatalogOverviewStats: ()      => request('GET', '/catalog/overview-stats'),
  searchCatalog:       (q)         => request('GET', `/catalog/search?q=${encodeURIComponent(q)}`),
  getInterpretations:  (params='') => request('GET', `/catalog/interpretations?${params}`),
  createInterpretation:(body)      => request('POST', '/catalog/interpretations', body),

  // Admin
  getAlignmentWeights:    ()    => request('GET',  '/admin/alignment-weights'),
  setAlignmentWeights:    (b)   => request('POST', '/admin/alignment-weights', b),
  refreshPeerAggregates:  ()    => request('POST', '/admin/refresh-peer-aggregates'),
  createCurationItem:     (body) => request('POST', '/curation/queue', body),

  // Health
  health: () => request('GET', '/health').catch(() => ({ status: 'error' })),
};

