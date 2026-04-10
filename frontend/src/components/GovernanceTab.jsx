import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { api } from '../api/client.js';
import { useApp } from '../context/AppContext.jsx';
import { normalizeRiskTier } from './shared/TierBadge.jsx';
import { PeerBenchmarkInline } from './shared/PeerBenchmarkInline.jsx';

const STEP_DEFS = [
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

const BASELINE_STEP2_KPI_COUNT = 10;

const THRESHOLD_OPERATOR_OPTIONS = [
  { value: 'lte', label: '<= (less than or equal)' },
  { value: 'gte', label: '>= (greater than or equal)' },
  { value: 'lt', label: '< (less than)' },
  { value: 'gt', label: '> (greater than)' },
  { value: 'eq', label: '= (equal)' },
  { value: 'between', label: 'between (min and max)' },
];

const INDUSTRY_LIBRARY = [
  { id: 'all', label: 'All Industries', keywords: [] },
  { id: 'healthcare', label: 'Healthcare & Life Sciences', keywords: ['health', 'medical', 'hospital', 'hipaa', 'fda', 'mdr', 'clinical'] },
  { id: 'financial', label: 'Financial Services & Banking', keywords: ['finance', 'financial', 'bank', 'basel', 'finra', 'credit', 'loan'] },
  { id: 'criminal_justice', label: 'Criminal Justice & Public Safety', keywords: ['criminal', 'justice', 'law enforcement', 'police', 'public safety'] },
  { id: 'hr', label: 'Human Resources & Employment', keywords: ['hr', 'employment', 'hiring', 'workforce', 'eeoc', 'labor'] },
  { id: 'education', label: 'Education & Research', keywords: ['education', 'school', 'student', 'ferpa', 'research', 'academic'] },
  { id: 'humanitarian', label: 'Humanitarian & Development', keywords: ['humanitarian', 'refugee', 'unhcr', 'aid', 'development'] },
  { id: 'government', label: 'Government & Public Sector', keywords: ['government', 'public sector', 'secretariat', 'un ', 'un-', 'dpk', 'state'] },
  { id: 'enterprise', label: 'General Enterprise', keywords: ['enterprise', 'nist', 'iso', 'ai act', 'cross-industry'] },
];

const REGION_LAYOUT = [
  { key: 'Americas', color: '#00A3FF' },
  { key: 'Europe', color: '#4DD4A6' },
  { key: 'Africa/Middle East', color: '#F6B14A' },
  { key: 'APAC', color: '#7B8CFF' },
  { key: 'Global', color: '#FF8CA8' },
];

function mapJurisdictionToRegion(jurisdiction) {
  const text = String(jurisdiction || '').toLowerCase();
  if (!text) {
    return 'Global';
  }
  if (text.includes('international') || text.includes('global') || text.includes('un ')) {
    return 'Global';
  }
  if (
    text.includes('us')
    || text.includes('united states')
    || text.includes('canada')
    || text.includes('america')
    || text.includes('brazil')
    || text.includes('mexico')
  ) {
    return 'Americas';
  }
  if (
    text.includes('eu')
    || text.includes('europe')
    || text.includes('uk')
    || text.includes('france')
    || text.includes('germany')
    || text.includes('italy')
    || text.includes('spain')
  ) {
    return 'Europe';
  }
  if (
    text.includes('africa')
    || text.includes('middle east')
    || text.includes('gcc')
    || text.includes('saudi')
    || text.includes('uae')
  ) {
    return 'Africa/Middle East';
  }
  if (
    text.includes('asia')
    || text.includes('apac')
    || text.includes('india')
    || text.includes('china')
    || text.includes('japan')
    || text.includes('australia')
    || text.includes('singapore')
  ) {
    return 'APAC';
  }
  return 'Global';
}

function isValidRegulationTitle(title) {
  const normalized = String(title || '').trim();
  if (!normalized) {
    return false;
  }
  const lower = normalized.toLowerCase();
  if (lower.startsWith('unlinked')) {
    return false;
  }
  if (lower.includes('phase 3')) {
    return false;
  }
  return true;
}
function normalizeRequirementItem(raw) {
  return {
    id: raw.requirement_id || raw.id || '',
    code: raw.code || 'N/A',
    title: raw.title || '',
    regulation_title: raw.regulation_title || null,
    jurisdiction: raw.jurisdiction || null,
    category: raw.category || null,
    selected: Boolean(raw.selected),
    is_default: Boolean(raw.is_default),
    linked_controls: Array.isArray(raw.linked_controls)
      ? raw.linked_controls
        .map((control) => ({
          id: control?.id || '',
          code: control?.code || 'N/A',
          title: control?.title || '',
          metric_name: control?.metric_name || null,
          default_threshold: control?.default_threshold && typeof control.default_threshold === 'object'
            ? control.default_threshold
            : null,
        }))
        .filter((control) => Boolean(control.id))
      : [],
  };
}

function matchesIndustryRequirement(requirement, categoryId) {
  if (!requirement || !categoryId || categoryId === 'all') {
    return true;
  }
  const category = INDUSTRY_LIBRARY.find((item) => item.id === categoryId);
  if (!category || !category.keywords.length) {
    return true;
  }
  const haystack = [
    requirement.code,
    requirement.title,
    requirement.category,
    requirement.regulation_title,
    requirement.jurisdiction,
  ].join(' ').toLowerCase();
  return category.keywords.some((keyword) => haystack.includes(keyword.toLowerCase()));
}


function fmtPercent(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A';
  }
  return `${Math.round(value * 100)}%`;
}

const STEP2_METRIC_META = {
  'governance.owner_assignment_pct': {
    label: 'Owner accountability coverage',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Checks whether an accountable application owner is assigned in the registry.',
  },
  'governance.division_assignment_pct': {
    label: 'Division accountability coverage',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Checks whether the application is mapped to a division-level governance owner.',
  },
  'governance.profile_completeness_pct': {
    label: 'Application profile completeness',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Percentage of required governance profile fields completed at registration.',
  },
  'governance.telemetry_pipeline_health_pct': {
    label: 'Telemetry pipeline health',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Whether the telemetry pipeline is currently healthy and ingesting data as expected.',
  },
  'governance.telemetry_freshness_hours': {
    label: 'Telemetry freshness',
    unitSuffix: 'h',
    percentAutoScale: false,
    measure: 'Hours since the latest telemetry reading was ingested for this application.',
  },
  'governance.compliance_pass_rate_pct': {
    label: 'Compliance pass rate',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Share of scoped controls currently passing configured thresholds.',
  },
  'ai.resources.compute_cost': {
    label: 'Compute cost',
    unitSuffix: ' USD',
    percentAutoScale: false,
    measure: 'Latest AI compute spend captured from telemetry for governance FinOps oversight.',
  },
  'ai.resources.token_usage': {
    label: 'Token usage',
    unitSuffix: ' tokens',
    percentAutoScale: false,
    measure: 'Latest model token consumption captured from telemetry for governance FinOps oversight.',
  },
  'ai.resources.active_users': {
    label: 'Active users',
    unitSuffix: ' users',
    percentAutoScale: false,
    measure: 'Latest active-user count captured from telemetry for governance scale oversight.',
  },
  'ai.resources.cost_per_token': {
    label: 'Cost per token',
    unitSuffix: ' USD/token',
    percentAutoScale: false,
    decimalPlaces: 4,
    measure: 'Average compute cost divided by token usage for the current telemetry window.',
  },
  'ai.resources.frontier_model_count': {
    label: 'Frontier model count',
    unitSuffix: ' models',
    percentAutoScale: false,
    measure: 'Number of frontier AI models currently used by the application solution stack.',
  },
  'ai.core.error_rate': {
    label: 'AI response error rate',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Percentage of AI responses that fail validation or return an error in the current monitoring window.',
  },
  'ai.oversight.override_rate': {
    label: 'Human override rate',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Percentage of AI outputs that were overridden by human reviewers in the current monitoring window.',
  },
  'ai.oversight.feedback_positive_rate': {
    label: 'Thumbs-up feedback rate',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Percentage of user feedback events marked thumbs-up versus total thumbs-up/down feedback events.',
  },
  'ai.core.drift_score': {
    label: 'Model drift score',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Percentage drift score comparing current model behavior to its approved baseline behavior.',
  },
  'ai.transparency.disclosure_rate': {
    label: 'AI disclosure coverage',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Percentage of relevant interactions where AI usage was disclosed to end users.',
  },
  'ai.transparency.doc_completeness': {
    label: 'Documentation completeness',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Percentage of required governance documentation fields that are currently completed.',
  },
  'ai.rag.citation_coverage': {
    label: 'Citation coverage',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Percentage of grounded response claims that include supporting citations from the retrieval layer.',
  },
  'ai.rag.retrieval_latency_p95': {
    label: 'Retrieval latency p95',
    unitSuffix: 'ms',
    percentAutoScale: false,
    measure: '95th percentile latency for the retrieval step before generation begins.',
  },
  'ai.model.accuracy': {
    label: 'Model accuracy',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Percentage of evaluated model outputs that meet expected quality and correctness criteria.',
  },
  'ai.model.hallucination_rate': {
    label: 'Hallucination rate',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Percentage of outputs flagged as ungrounded or unsupported by retrieved evidence.',
  },
  'ai.data.quality_score': {
    label: 'Data quality score',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Composite score of data completeness, validity, and consistency for AI inputs.',
  },
  'ai.data.bias_score': {
    label: 'Data bias score',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Bias indicator derived from disparity checks across relevant groups.',
  },
  'ai.risk.error_to_limit_ratio': {
    label: 'Error rate vs allowed limit',
    unitSuffix: '%',
    percentAutoScale: false,
    ratioToPercent: true,
    measure: 'Current error rate divided by the approved error limit, expressed as percentage of limit utilization.',
  },
  'ai.risk.override_to_target_ratio': {
    label: 'Override rate vs target',
    unitSuffix: '%',
    percentAutoScale: false,
    ratioToPercent: true,
    clampMax100: true,
    measure: 'Current human override rate divided by the target override threshold, expressed as percentage of target utilization.',
  },
  'ai.risk.drift_to_limit_ratio': {
    label: 'Drift score vs allowed limit',
    unitSuffix: '%',
    percentAutoScale: false,
    ratioToPercent: true,
    measure: 'Current drift score divided by the approved drift limit, expressed as percentage of limit utilization.',
  },
  'ai.risk.disclosure_gap_pct': {
    label: 'Disclosure gap to target',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Gap between current disclosure coverage and target disclosure threshold, expressed as a percentage.',
  },
  'ai.risk.doc_completeness_gap_pct': {
    label: 'Documentation gap to target',
    unitSuffix: '%',
    percentAutoScale: true,
    measure: 'Gap between current documentation completeness and target completeness threshold, expressed as a percentage.',
  },
};

function humanizeMetricName(metricName) {
  if (!metricName) {
    return 'Measure';
  }
  const tail = String(metricName).split('.').pop() || String(metricName);
  return tail
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function getStep2MetricMeta(metricName) {
  if (metricName && STEP2_METRIC_META[metricName]) {
    return STEP2_METRIC_META[metricName];
  }
  return {
    label: humanizeMetricName(metricName),
    unitSuffix: '',
    percentAutoScale: false,
    ratioToPercent: false,
    clampMax100: false,
    decimalPlaces: 0,
    measure: 'Calculated from live application telemetry for this mandatory requirement.',
  };
}

function formatStep2MetricValue(metricName, value) {
  const scaled = toStep2DisplayNumber(metricName, value);
  if (scaled === null) {
    return 'N/A';
  }
  const meta = getStep2MetricMeta(metricName);
  const decimalPlaces = Number.isInteger(meta.decimalPlaces) ? meta.decimalPlaces : 0;
  const rounded = decimalPlaces > 0 ? Number(scaled).toFixed(decimalPlaces) : `${Math.round(scaled)}`;
  return meta.unitSuffix ? `${rounded}${meta.unitSuffix}` : `${rounded}`;
}

function toStep2DisplayNumber(metricName, value) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return null;
  }
  const meta = getStep2MetricMeta(metricName);
  let scaled = value;
  if (meta.unitSuffix === '%' && meta.ratioToPercent) {
    // Ratio metrics can arrive either as 0..1 (ratio) or already as 0..100 (percent).
    scaled = Math.abs(value) <= 1 ? value * 100 : value;
  } else if (meta.unitSuffix === '%' && meta.percentAutoScale) {
    scaled = Math.abs(value) <= 1 ? value * 100 : value;
  }
  if (meta.unitSuffix === '%' && meta.clampMax100) {
    scaled = Math.min(100, scaled);
  }
  return scaled;
}

function getStep2InterpretationText(row) {
  const metricLabel = getStep2MetricMeta(row?.metric_name).label;
  if (row?.benchmark_result === 'PASS') {
    return `${metricLabel} meets the configured benchmark test against industry and peer baselines.`;
  }
  if (row?.benchmark_result === 'FAIL') {
    return `${metricLabel} misses one or more benchmark targets (industry baseline and/or peer baseline).`;
  }
  if (row?.benchmark_result === 'INSUFFICIENT_DATA') {
    return `Telemetry is not yet sufficient to benchmark ${metricLabel.toLowerCase()} against industry or peers.`;
  }
  if (row?.result === 'PASS') {
    return `${metricLabel} is within the acceptable operating range.`;
  }
  if (row?.result === 'FAIL') {
    return `${metricLabel} is outside the acceptable operating range and needs follow-up action.`;
  }
  return `Telemetry is not yet sufficient to evaluate ${metricLabel.toLowerCase()}.`;
}

function buildStep2BenchmarkComparison(row, label, benchmark) {
  const current = toStep2DisplayNumber(row?.metric_name, row?.value);
  const baseline = toStep2DisplayNumber(row?.metric_name, benchmark);
  if (current === null || baseline === null) {
    return null;
  }
  const delta = current - baseline;
  const atParity = Math.abs(delta) < 1e-9;
  const higherBetter = String(row?.threshold?.direction || '').toLowerCase() !== 'lower_better';
  const better = atParity ? null : (higherBetter ? delta > 0 : delta < 0);
  return {
    label,
    current,
    baseline,
    delta,
    atParity,
    better,
    trendArrow: atParity ? '\u2192' : (delta > 0 ? '\u2191' : '\u2193'),
    currentText: formatStep2MetricValue(row.metric_name, row?.value),
    baselineText: formatStep2MetricValue(row.metric_name, benchmark),
    deltaText: formatStep2MetricValue(row.metric_name, Math.abs(delta)),
  };
}

function renderStep2BenchmarkInline(row) {
  const current = toStep2DisplayNumber(row?.metric_name, row?.value);
  if (current === null) {
    return <span className="peer-inline-muted">No current application value available yet.</span>;
  }

  const industryValue = toStep2DisplayNumber(row?.metric_name, row?.industry_benchmark);
  const peerValue = toStep2DisplayNumber(row?.metric_name, row?.peer_benchmark ?? row?.peer_avg);

  const points = [
    { key: 'kpi', label: 'KPI', value: current, valueText: formatStep2MetricValue(row.metric_name, row?.value), tone: 'kpi' },
    { key: 'industry', label: 'Industry', value: industryValue, valueText: formatStep2MetricValue(row.metric_name, row?.industry_benchmark), tone: 'industry' },
    { key: 'peer', label: 'Peer', value: peerValue, valueText: formatStep2MetricValue(row.metric_name, row?.peer_benchmark ?? row?.peer_avg), tone: 'peer' },
  ].filter((item) => item.value !== null);

  if (points.length < 2) {
    return <span className="peer-inline-muted">Industry and peer benchmarks are not available yet.</span>;
  }

  const minValue = Math.min(...points.map((item) => item.value));
  const maxValue = Math.max(...points.map((item) => item.value));
  const span = Math.max(maxValue - minValue, Math.abs(maxValue || 1) * 0.1, 1);
  const rangeMin = minValue - span * 0.12;
  const rangeMax = maxValue + span * 0.12;
  const toPosition = (value) => {
    if (rangeMax <= rangeMin) {
      return 50;
    }
    return Math.max(0, Math.min(100, ((value - rangeMin) / (rangeMax - rangeMin)) * 100));
  };

  const comparisons = [
    buildStep2BenchmarkComparison(row, 'Industry', row?.industry_benchmark),
    buildStep2BenchmarkComparison(row, 'Peer', row?.peer_benchmark ?? row?.peer_avg),
  ].filter(Boolean);

  return (
    <div className="step2-benchmark-combined">
      <div className="step2-benchmark-combined-top">
        {comparisons.length ? (
          comparisons.map((comparison) => (
            <span key={`${row.metric_name}-${comparison.label}`} className={`step2-benchmark-chip tone-${comparison.atParity ? 'neutral' : comparison.better ? 'better' : 'worse'}`}>
              {comparison.label}: {comparison.atParity ? 'at baseline' : `${comparison.better ? 'better' : 'worse'} by ${comparison.deltaText}`} ({comparison.trendArrow})
            </span>
          ))
        ) : (
          <span className="peer-inline-muted">Benchmark comparison unavailable.</span>
        )}
      </div>
      <div className="step2-benchmark-track-wrap">
        <span className="step2-benchmark-track-line" />
        {points.map((point) => (
          <span
            key={`${row.metric_name}-${point.key}`}
            className={`step2-benchmark-dot dot-${point.tone}`}
            style={{ left: `${toPosition(point.value)}%` }}
            title={`${point.label}: ${point.valueText}`}
          />
        ))}
      </div>
      <div className="step2-benchmark-legend">
        {[
          { key: 'kpi', label: 'KPI', value: current, valueText: formatStep2MetricValue(row.metric_name, row?.value), tone: 'kpi' },
          { key: 'industry', label: 'Industry', value: industryValue, valueText: formatStep2MetricValue(row.metric_name, row?.industry_benchmark), tone: 'industry' },
          { key: 'peer', label: 'Peer', value: peerValue, valueText: formatStep2MetricValue(row.metric_name, row?.peer_benchmark ?? row?.peer_avg), tone: 'peer' },
        ].map((point) => (
          <span key={`${row.metric_name}-legend-${point.key}`} className="step2-benchmark-legend-item">
            <span className={`step2-benchmark-swatch dot-${point.tone}`} />
            {point.label}: {point.value === null ? (point.key === 'peer' ? 'No peer data' : 'No benchmark data') : point.valueText}
          </span>
        ))}
      </div>
    </div>
  );
}
function extractFormulaMetricRefs(formula) {
  if (!formula) {
    return [];
  }
  const matches = String(formula).match(/ai\.[a-z0-9_.]+/gi) || [];
  return Array.from(new Set(matches.map((item) => item.toLowerCase())));
}

function getSourceSystemLabel(sourceSystem) {
  const source = String(sourceSystem || '').toLowerCase();
  if (source === 'otel') {
    return 'live OpenTelemetry application metrics';
  }
  if (source === 'calculated') {
    return 'derived KPI calculations from existing telemetry metrics';
  }
  if (source === 'github_actions') {
    return 'CI/CD governance signals from GitHub Actions';
  }
  if (source === 'your_feedback') {
    return 'human oversight and feedback event logs';
  }
  return 'governance telemetry sources configured for this KPI';
}

function getStep2ValueSourceLegend(row) {
  const threshold = row?.threshold || {};
  const formula = String(threshold.formula || '').trim();
  const calcType = String(threshold.calculation_type || '').toLowerCase();
  const sourceSystem = String(threshold.source_system || '').toLowerCase();
  const sourceLabel = getSourceSystemLabel(sourceSystem);
  const dependencies = extractFormulaMetricRefs(formula);
  const dependencyLabels = dependencies
    .map((metric) => `${getStep2MetricMeta(metric).label} (${metric})`);

  if (formula && (calcType === 'derived' || sourceSystem === 'calculated')) {
    if (dependencyLabels.length) {
      return `Derived from ${dependencyLabels.join(', ')} using formula "${formula}". Source: ${sourceLabel}.`;
    }
    return `Derived using formula "${formula}". Source: ${sourceLabel}.`;
  }

  if (formula) {
    return `Directly read from ${getStep2MetricMeta(row?.metric_name).label} (${row?.metric_name}) using "${formula}". Source: ${sourceLabel}.`;
  }

  return `Directly read from ${getStep2MetricMeta(row?.metric_name).label} (${row?.metric_name}). Source: ${sourceLabel}.`;
}

function getStep1ValueSourceLegend(row) {
  const byMetric = {
    'governance.owner_assignment_pct': 'Derived from application registry field owner_email.',
    'governance.division_assignment_pct': 'Derived from application registry field division_id.',
    'governance.profile_completeness_pct': 'Derived from required registration fields in the application profile.',
    'governance.telemetry_pipeline_health_pct': 'Derived from telemetry status heartbeat for the connected application.',
    'governance.telemetry_freshness_hours': 'Derived from timestamp of latest telemetry reading ingested by the platform.',
    'governance.compliance_pass_rate_pct': 'Derived from live compliance calculator output for scoped controls.',
    'ai.resources.compute_cost': 'Directly read from telemetry metric ai.resources.compute_cost (USD).',
    'ai.resources.token_usage': 'Directly read from telemetry metric ai.resources.token_usage (token count).',
    'ai.resources.active_users': 'Directly read from telemetry metric ai.resources.active_users (distinct active users).',
    'ai.resources.cost_per_token': 'Derived from ai.resources.compute_cost divided by ai.resources.token_usage.',
    'ai.resources.frontier_model_count': 'Derived from frontier model telemetry attributes or explicit frontier model count metric.',
    'ai.oversight.feedback_positive_rate': 'Derived from thumbs-up/down feedback telemetry events emitted by the connected application.',
  };
  return byMetric[row?.metric_name] || 'Derived from live governance system data for this application.';
}

function toRatio(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return null;
  }
  if (Math.abs(value) <= 1) {
    return value;
  }
  return value / 100;
}

function buildCorporateOversightRows(selectedApp, snapshot, summary, finopsRows = []) {
  const app = selectedApp || {};
  const profile = summary && typeof summary === 'object' ? summary : app;
  const telemetry = snapshot?.telemetry || {};
  const compliance = snapshot?.compliance || {};

  const ownerAssigned = Boolean(app.owner_email || profile.owner_email);
  const divisionAssigned = Boolean(app.division_id || profile.division_id);

  const requiredFields = [
    profile?.name,
    profile?.domain,
    profile?.ai_system_type,
    profile?.decision_type,
    profile?.autonomy_level,
    app?.owner_email || profile?.owner_email,
    app?.division_id || profile?.division_id,
  ];
  const filledFields = requiredFields.filter((value) => Boolean(String(value || '').trim())).length;
  const profileCompleteness = requiredFields.length ? (filledFields / requiredFields.length) : 0;

  const telemetryStatus = String(telemetry?.status || '').toLowerCase();
  const telemetryHealthy = ['healthy', 'ok', 'active', 'running'].includes(telemetryStatus);

  let freshnessHours = null;
  if (telemetry?.latest_reading) {
    const latestMs = Date.parse(telemetry.latest_reading);
    if (!Number.isNaN(latestMs)) {
      freshnessHours = (Date.now() - latestMs) / 36e5;
    }
  }

  const complianceRatio = toRatio(compliance?.pass_rate);

  const baseRows = [
    {
      control_title: 'Accountability Owner Assignment',
      requirement_title: 'An accountable owner must be explicitly assigned for governance accountability.',
      metric_name: 'governance.owner_assignment_pct',
      value: ownerAssigned ? 1 : 0,
      result: ownerAssigned ? 'PASS' : 'FAIL',
      threshold: { direction: 'higher_better' },
      industry_benchmark: 0.95,
      peer_benchmark: 0.9,
    },
    {
      control_title: 'Division Governance Ownership',
      requirement_title: 'Each application must be mapped to a division or governance accountability unit.',
      metric_name: 'governance.division_assignment_pct',
      value: divisionAssigned ? 1 : 0,
      result: divisionAssigned ? 'PASS' : 'FAIL',
      threshold: { direction: 'higher_better' },
      industry_benchmark: 0.95,
      peer_benchmark: 0.9,
    },
    {
      control_title: 'Governance Registration Completeness',
      requirement_title: 'Corporate oversight requires a complete application governance profile.',
      metric_name: 'governance.profile_completeness_pct',
      value: profileCompleteness,
      result: profileCompleteness >= 0.85 ? 'PASS' : 'FAIL',
      threshold: { direction: 'higher_better' },
      industry_benchmark: 0.9,
      peer_benchmark: 0.85,
    },
    {
      control_title: 'Telemetry Pipeline Operational Health',
      requirement_title: 'Oversight monitoring requires a healthy telemetry ingestion pipeline.',
      metric_name: 'governance.telemetry_pipeline_health_pct',
      value: telemetryStatus ? (telemetryHealthy ? 1 : 0) : null,
      result: !telemetryStatus ? 'INSUFFICIENT_DATA' : (telemetryHealthy ? 'PASS' : 'FAIL'),
      threshold: { direction: 'higher_better' },
      industry_benchmark: 0.9,
      peer_benchmark: 0.85,
    },
    {
      control_title: 'Telemetry Recency Oversight',
      requirement_title: 'Oversight KPIs must be based on fresh telemetry data.',
      metric_name: 'governance.telemetry_freshness_hours',
      value: typeof freshnessHours === 'number' && !Number.isNaN(freshnessHours) ? freshnessHours : null,
      result: freshnessHours === null ? 'INSUFFICIENT_DATA' : (freshnessHours <= 24 ? 'PASS' : 'FAIL'),
      threshold: { direction: 'lower_better' },
      industry_benchmark: 12,
      peer_benchmark: 18,
    },
    {
      control_title: 'Compliance Monitoring Coverage',
      requirement_title: 'Corporate oversight requires ongoing control compliance monitoring.',
      metric_name: 'governance.compliance_pass_rate_pct',
      value: complianceRatio,
      result: complianceRatio === null ? 'INSUFFICIENT_DATA' : (complianceRatio >= 0.75 ? 'PASS' : 'FAIL'),
      threshold: { direction: 'higher_better' },
      industry_benchmark: 0.8,
      peer_benchmark: 0.75,
    },
  ];

  const finopsMetricNames = new Set([
    'ai.resources.compute_cost',
    'ai.resources.token_usage',
    'ai.resources.active_users',
    'ai.resources.cost_per_token',
    'ai.resources.frontier_model_count',
  ]);
  const finopsTelemetryRows = Array.isArray(finopsRows)
    ? finopsRows
      .filter((row) => finopsMetricNames.has(row?.metric_name))
      .map((row) => ({
        ...row,
        threshold: row?.threshold || { direction: 'lower_better' },
      }))
    : [];

  return [...baseRows, ...finopsTelemetryRows];
}

function resolveDefaultControlId(requirementId, requirements, currentControlId = '') {
  const requirement = requirements.find((item) => item.id === requirementId);
  const controls = requirement?.linked_controls || [];
  if (!controls.length) {
    return '';
  }
  if (currentControlId && controls.some((item) => item.id === currentControlId)) {
    return currentControlId;
  }
  return controls[0].id;
}

function parseNumericInput(rawValue) {
  const normalized = String(rawValue ?? '').trim();
  if (!normalized) {
    return null;
  }
  const value = Number(normalized);
  if (Number.isNaN(value)) {
    return null;
  }
  return value;
}

function sameStringSet(valuesA, valuesB) {
  const setA = new Set(valuesA || []);
  const setB = new Set(valuesB || []);
  if (setA.size !== setB.size) {
    return false;
  }
  for (const value of setA) {
    if (!setB.has(value)) {
      return false;
    }
  }
  return true;
}

function toNumeric(value) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return null;
  }
  return parsed;
}

function buildThresholdOverrideFromDraft(draft) {
  if (!draft.thresholdEnabled) {
    return { thresholdOverride: null, validationError: '' };
  }
  if (draft.thresholdOperator === 'between') {
    const minValue = parseNumericInput(draft.thresholdMin);
    const maxValue = parseNumericInput(draft.thresholdMax);
    if (minValue === null || maxValue === null) {
      return {
        thresholdOverride: null,
        validationError: 'Threshold override requires numeric min and max values.',
      };
    }
    if (minValue > maxValue) {
      return {
        thresholdOverride: null,
        validationError: 'Threshold override requires min_value <= max_value.',
      };
    }
    return {
      thresholdOverride: {
        operator: 'between',
        min_value: minValue,
        max_value: maxValue,
      },
      validationError: '',
    };
  }

  const value = parseNumericInput(draft.thresholdValue);
  if (value === null) {
    return {
      thresholdOverride: null,
      validationError: 'Threshold override requires a numeric value.',
    };
  }
  return {
    thresholdOverride: {
      operator: draft.thresholdOperator,
      value,
    },
    validationError: '',
  };
}

function formatThresholdOverride(override) {
  if (!override || typeof override !== 'object') {
    return 'N/A';
  }
  const operator = override.operator || 'N/A';
  if (operator === 'between') {
    return `between ${override.min_value ?? '?'} and ${override.max_value ?? '?'}`;
  }
  return `${operator} ${override.value ?? '?'}`;
}

function isMorePermissiveThreshold(override, baseline) {
  if (!override || !baseline || typeof override !== 'object' || typeof baseline !== 'object') {
    return false;
  }
  const overrideOp = String(override.operator || '');
  const baselineOp = String(baseline.operator || '');
  if (!overrideOp || !baselineOp || overrideOp !== baselineOp) {
    return false;
  }

  if (overrideOp === 'between') {
    const oMin = toNumeric(override.min_value);
    const oMax = toNumeric(override.max_value);
    const bMin = toNumeric(baseline.min_value);
    const bMax = toNumeric(baseline.max_value);
    if (oMin === null || oMax === null || bMin === null || bMax === null) {
      return false;
    }
    return oMin < bMin || oMax > bMax;
  }

  const oValue = toNumeric(override.value);
  const bValue = toNumeric(baseline.value);
  if (oValue === null || bValue === null) {
    return false;
  }

  if (overrideOp === 'lte' || overrideOp === 'lt') {
    return oValue > bValue;
  }
  if (overrideOp === 'gte' || overrideOp === 'gt') {
    return oValue < bValue;
  }
  return false;
}

function SystemGeoMap({ regionCounts }) {
  const getCount = (key) => Number(regionCounts?.[key] || 0);
  const rows = REGION_LAYOUT
    .map((region) => ({ ...region, count: getCount(region.key) }))
    .sort((a, b) => b.count - a.count);
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  const maxCount = Math.max(1, ...rows.map((row) => row.count));

  let cursor = 0;
  const stops = rows
    .filter((row) => row.count > 0)
    .map((row) => {
      const start = cursor;
      const pct = (row.count / total) * 100;
      cursor += pct;
      return `${row.color} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`;
    });
  const donutBackground = stops.length
    ? `conic-gradient(${stops.join(', ')})`
    : 'conic-gradient(rgba(255,255,255,0.12) 0% 100%)';

  return (
    <div className="system-geo-wrap">
      <div className="system-geo-summary">
        <div className="system-geo-donut" style={{ background: donutBackground }}>
          <div className="system-geo-donut-center">
            <strong>{total}</strong>
            <span>total</span>
          </div>
        </div>
        <div className="system-geo-summary-copy">
          <div className="system-geo-summary-title">Regional Coverage</div>
          <div className="system-geo-summary-subtitle">
            Share of mapped jurisdiction references across governance regulations.
          </div>
        </div>
      </div>

      <div className="system-geo-bars">
        {rows.map((row) => {
          const share = total > 0 ? (row.count / total) * 100 : 0;
          const barWidth = row.count > 0 ? Math.max(8, (row.count / maxCount) * 100) : 0;
          return (
            <div key={`geo-${row.key}`} className="system-geo-row">
              <div className="system-geo-row-head">
                <span className="system-geo-label">
                  <span className="system-geo-dot" style={{ background: row.color }} />
                  {row.key}
                </span>
                <span className="system-geo-value">
                  {row.count} <em>{Math.round(share)}%</em>
                </span>
              </div>
              <div className="system-geo-track">
                <span
                  className="system-geo-fill"
                  style={{
                    width: `${barWidth}%`,
                    background: `linear-gradient(90deg, ${row.color}, rgba(255,255,255,0.2))`,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

SystemGeoMap.propTypes = {
  regionCounts: PropTypes.objectOf(PropTypes.number),
};

SystemGeoMap.defaultProps = {
  regionCounts: {},
};

function pctFromTotals(value, total) {
  const numerator = Number(value || 0);
  const denominator = Number(total || 0);
  if (denominator <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round((numerator / denominator) * 100)));
}

function CoverageTrack({ label, value, total, tone }) {
  const safeValue = Math.max(0, Number(value || 0));
  const safeTotal = Math.max(0, Number(total || 0));
  const percent = pctFromTotals(safeValue, safeTotal);
  const displayTotal = safeTotal > 0 ? safeTotal : 0;
  const gradient = tone === 'teal'
    ? 'linear-gradient(90deg, #2dd4bf, #67e8f9)'
    : tone === 'amber'
      ? 'linear-gradient(90deg, #f59e0b, #fbbf24)'
      : tone === 'rose'
        ? 'linear-gradient(90deg, #fb7185, #fda4af)'
        : 'linear-gradient(90deg, #00a3ff, #7dd3fc)';

  return (
    <div className="coverage-track-row">
      <div className="coverage-track-head">
        <span>{label}</span>
        <strong>
          {safeValue}/{displayTotal} <em>{percent}%</em>
        </strong>
      </div>
      <div className="coverage-track-bar">
        <span className="coverage-track-fill" style={{ width: `${percent}%`, background: gradient }} />
      </div>
    </div>
  );
}

CoverageTrack.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.number,
  total: PropTypes.number,
  tone: PropTypes.oneOf(['blue', 'teal', 'amber', 'rose']),
};

CoverageTrack.defaultProps = {
  value: 0,
  total: 0,
  tone: 'blue',
};

function StepBasicPanel({ activeStep, selectedApp, snapshot, fmtDateTime, fmtNum }) {
  if (activeStep === 1) {
    const telemetry = snapshot?.telemetry;
    const compliance = snapshot?.compliance;
    return (
      <div className="grid-2">
        <div className="card card-flat">
          <div className="section-label">Application Profile</div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            <div><strong>Name:</strong> {selectedApp?.name || 'N/A'}</div>
            <div><strong>Domain:</strong> {selectedApp?.domain || 'N/A'}</div>
            <div><strong>AI System Type:</strong> {selectedApp?.ai_system_type || 'N/A'}</div>
            <div><strong>Decision Type:</strong> {selectedApp?.decision_type || 'N/A'}</div>
            <div><strong>Autonomy:</strong> {selectedApp?.autonomy_level || 'N/A'}</div>
          </div>
        </div>
        <div className="card card-flat">
          <div className="section-label">Corporate Oversight Signals</div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            <div><strong>Owner:</strong> {selectedApp?.owner_email || 'N/A'}</div>
            <div><strong>Division:</strong> {selectedApp?.division_id || 'N/A'}</div>
            <div><strong>Telemetry Status:</strong> {telemetry?.status || 'N/A'}</div>
            <div><strong>KPI Readings:</strong> {telemetry?.total_readings ?? 'N/A'}</div>
            <div><strong>Compliance Pass Rate:</strong> {fmtPercent(compliance?.pass_rate)}</div>
            <div><strong>Last KPI Ingest:</strong> {fmtDateTime(telemetry?.latest_reading)}</div>
          </div>
        </div>
      </div>
    );
  }


  return null;
}

StepBasicPanel.propTypes = {
  activeStep: PropTypes.number,
  selectedApp: PropTypes.shape({
    name: PropTypes.string,
    domain: PropTypes.string,
    ai_system_type: PropTypes.string,
    decision_type: PropTypes.string,
    autonomy_level: PropTypes.string,
    owner_email: PropTypes.string,
    division_id: PropTypes.string,
    consent_scope: PropTypes.string,
    status: PropTypes.string,
    registered_at: PropTypes.string,
  }),
  snapshot: PropTypes.shape({
    tier: PropTypes.object,
    compliance: PropTypes.object,
    telemetry: PropTypes.object,
  }).isRequired,
  fmtDateTime: PropTypes.func.isRequired,
  fmtNum: PropTypes.func.isRequired,
};

export default function GovernanceTab({ requestedStep, onDashboardUiChange }) {
  const { selectedApp } = useApp();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeStep, setActiveStep] = useState(null);
  const [loadingStepDetail, setLoadingStepDetail] = useState(false);
  const [stepDetailError, setStepDetailError] = useState('');
  const [showAllCorporate, setShowAllCorporate] = useState(false);
  const [showAllMandatory, setShowAllMandatory] = useState(false);
  const [showAllTechnical, setShowAllTechnical] = useState(false);
  const [showAllDataReadiness, setShowAllDataReadiness] = useState(false);
  const [showAllDataIntegration, setShowAllDataIntegration] = useState(false);
  const [showAllSecurity, setShowAllSecurity] = useState(false);
  const [showAllInfrastructure, setShowAllInfrastructure] = useState(false);
  const [showAllSolutionDesign, setShowAllSolutionDesign] = useState(false);
  const [showAllSystemPerformance, setShowAllSystemPerformance] = useState(false);
  const [detailCache, setDetailCache] = useState({
    benchmarks: null,
    history: null,
    recommendations: null,
    dashboardStep1: null,
    dashboardStep2: null,
    dashboardStep3: null,
    dashboardStep4: null,
    dashboardStep5: null,
    dashboardStep6: null,
    dashboardStep7: null,
    dashboardStep8: null,
    dashboardStep9: null,
  });
  const [snapshot, setSnapshot] = useState({
    tier: null,
    compliance: null,
    telemetry: null,
  });
  const [interpretationRequirements, setInterpretationRequirements] = useState([]);
  const [interpretationRows, setInterpretationRows] = useState([]);
  const [interpretationLoading, setInterpretationLoading] = useState(false);
  const [interpretationSaving, setInterpretationSaving] = useState(false);
  const [interpretationError, setInterpretationError] = useState('');
  const [interpretationNotice, setInterpretationNotice] = useState('');
  const [interpretationDraft, setInterpretationDraft] = useState({
    requirementId: '',
    controlId: '',
    content: '',
    thresholdEnabled: false,
    thresholdOperator: 'lte',
    thresholdValue: '',
    thresholdMin: '',
    thresholdMax: '',
  });
  const [requirementFilter, setRequirementFilter] = useState('');
  const [scopedRequirementIds, setScopedRequirementIds] = useState([]);
  const [showScopedOnly, setShowScopedOnly] = useState(true);
  const [scopeSaving, setScopeSaving] = useState(false);
  const [scopeError, setScopeError] = useState('');
  const [scopeNotice, setScopeNotice] = useState('');
  const [catalogSearchQuery, setCatalogSearchQuery] = useState('');
  const [catalogSearchLoading, setCatalogSearchLoading] = useState(false);
  const [catalogSearchError, setCatalogSearchError] = useState('');
  const [catalogSearchResults, setCatalogSearchResults] = useState([]);
  const [industryCategory, setIndustryCategory] = useState('all');
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState('');
  const [systemOverview, setSystemOverview] = useState({
    totalApps: 0,
    connectedApps: 0,
    distinctRules: 0,
    totalRequirements: 0,
    distinctControls: 0,
    totalControls: 0,
    rulesWithControls: 0,
    rulesWithMeasures: 0,
    controlsWithMeasures: 0,
    totalMeasureDefinitions: 0,
    distinctMeasureMetrics: 0,
    peerBenchmarkedMetrics: 0,
    totalRuleControlLinks: 0,
    distinctControlDomains: 0,
    riskComplianceControls: 0,
    riskComplianceMeasurableControls: 0,
    riskComplianceDomainsPresent: 0,
    totalRegulations: 0,
    totalJurisdictions: 0,
    totalIndustryCategories: Math.max(0, INDUSTRY_LIBRARY.length - 1),
    telemetryReadings: 0,
    telemetryStatus: 'N/A',
    totalInterpretations: 0,
    regulations: [],
    topJurisdictions: [],
    regionCounts: {},
  });
  const detailSectionRef = useRef(null);

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

  const preloadDashboardStatusData = useCallback(async () => {
    if (!selectedApp?.id) {
      return;
    }
    const steps = [1, 2, 3, 4, 5, 6, 7, 8, 9];
    const results = await Promise.allSettled(
      steps.map((stepNum) => api.getApplicationDashboardStep(selectedApp.id, stepNum))
    );
    const updates = {};
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        updates[`dashboardStep${steps[index]}`] = result.value;
      }
    });
    if (Object.keys(updates).length > 0) {
      setDetailCache((prev) => ({ ...prev, ...updates }));
    }
  }, [selectedApp?.id]);

  useEffect(() => {
    preloadDashboardStatusData();
  }, [preloadDashboardStatusData]);

  const loadSystemOverview = useCallback(async () => {
    setOverviewLoading(true);
    setOverviewError('');

    const [appsResult, requirementsResult, controlsResult, regulationsResult, overviewStatsResult, telemetryResult] = await Promise.allSettled([
      api.listApplications(),
      api.getRequirements('limit=200'),
      api.getControls('limit=200'),
      api.getRegulations('limit=500'),
      api.getCatalogOverviewStats(),
      api.getTelemetryStatus(),
    ]);

    const failed = [];

    const applications = appsResult.status === 'fulfilled' && Array.isArray(appsResult.value)
      ? appsResult.value
      : [];
    if (appsResult.status !== 'fulfilled') {
      failed.push('applications');
    }

    const requirementPayload = requirementsResult.status === 'fulfilled' ? requirementsResult.value : null;
    if (requirementsResult.status !== 'fulfilled') {
      failed.push('requirements');
    }
    const requirements = Array.isArray(requirementPayload?.items) ? requirementPayload.items : [];

    const controlsPayload = controlsResult.status === 'fulfilled' ? controlsResult.value : null;
    if (controlsResult.status !== 'fulfilled') {
      failed.push('controls');
    }
    const controls = Array.isArray(controlsPayload?.items) ? controlsPayload.items : [];

    const regulationsPayload = regulationsResult.status === 'fulfilled' ? regulationsResult.value : null;
    if (regulationsResult.status !== 'fulfilled') {
      failed.push('regulations');
    }
    const regulations = Array.isArray(regulationsPayload?.items) ? regulationsPayload.items : [];

    const overviewStats = overviewStatsResult.status === 'fulfilled' ? overviewStatsResult.value : null;
    if (overviewStatsResult.status !== 'fulfilled') {
      failed.push('overview_stats');
    }

    const telemetry = telemetryResult.status === 'fulfilled' ? telemetryResult.value : null;
    if (telemetryResult.status !== 'fulfilled') {
      failed.push('telemetry');
    }

    const regulationSet = new Set(
      regulations
        .map((item) => String(item?.title || '').trim())
        .filter((title) => isValidRegulationTitle(title))
    );
    const jurisdictionCounts = {};
    regulations.forEach((item) => {
      const jurisdiction = String(item?.jurisdiction || '').trim();
      if (!jurisdiction) {
        return;
      }
      const weight = Number(item?.requirement_count ?? 0);
      jurisdictionCounts[jurisdiction] = (jurisdictionCounts[jurisdiction] || 0) + (Number.isFinite(weight) && weight > 0 ? weight : 1);
    });

    if (regulationSet.size === 0 || Object.keys(jurisdictionCounts).length === 0) {
      requirements.forEach((item) => {
        const regulationTitle = String(item?.regulation_title || '').trim();
        if (isValidRegulationTitle(regulationTitle)) {
          regulationSet.add(regulationTitle);
        }
        const jurisdiction = String(item?.jurisdiction || '').trim();
        if (jurisdiction) {
          jurisdictionCounts[jurisdiction] = (jurisdictionCounts[jurisdiction] || 0) + 1;
        }
      });
    }

    const regionCounts = {};
    Object.entries(jurisdictionCounts).forEach(([jurisdiction, count]) => {
      const region = mapJurisdictionToRegion(jurisdiction);
      regionCounts[region] = (regionCounts[region] || 0) + Number(count || 0);
    });

    const topJurisdictions = Object.entries(jurisdictionCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name, count]) => ({ name, count }));

    const riskComplianceDomainSet = new Set(['risk management', 'regulatory', 'governance', 'audit', 'privacy']);
    const normalizedControls = controls.map((item) => ({
      domain: String(item?.domain || '').trim().toLowerCase(),
      measurementMode: String(item?.measurement_mode || '').trim().toLowerCase(),
    }));
    const riskComplianceControls = normalizedControls.filter((item) => riskComplianceDomainSet.has(item.domain));
    const riskComplianceMeasurableControls = riskComplianceControls.filter((item) => item.measurementMode !== 'manual');
    const riskComplianceDomainsPresent = new Set(riskComplianceControls.map((item) => item.domain)).size;
    const controlsWithMeasuresFallback = normalizedControls.filter((item) => item.measurementMode !== 'manual').length;

    setSystemOverview({
      totalApps: applications.length,
      connectedApps: applications.filter((app) => app?.status === 'active').length,
      distinctRules: Number(overviewStats?.distinct_rules ?? requirementPayload?.total ?? requirements.length ?? 0),
      totalRequirements: Number(overviewStats?.total_requirements ?? requirementPayload?.total ?? requirements.length ?? 0),
      distinctControls: Number(overviewStats?.total_controls ?? controlsPayload?.total ?? controls.length ?? 0),
      totalControls: Number(overviewStats?.total_controls ?? controlsPayload?.total ?? controls.length ?? 0),
      rulesWithControls: Number(overviewStats?.rules_with_controls ?? 0),
      rulesWithMeasures: Number(overviewStats?.rules_with_measures ?? 0),
      controlsWithMeasures: Number(overviewStats?.controls_with_measures ?? controlsWithMeasuresFallback),
      totalMeasureDefinitions: Number(overviewStats?.total_measure_definitions ?? 0),
      distinctMeasureMetrics: Number(overviewStats?.distinct_measure_metrics ?? 0),
      peerBenchmarkedMetrics: Number(overviewStats?.peer_benchmarked_metrics ?? 0),
      totalRuleControlLinks: Number(overviewStats?.total_control_requirement_links ?? 0),
      distinctControlDomains: Number(overviewStats?.distinct_control_domains ?? 0),
      riskComplianceControls: Number(overviewStats?.risk_compliance_controls ?? riskComplianceControls.length),
      riskComplianceMeasurableControls: Number(
        overviewStats?.risk_compliance_measurable_controls ?? riskComplianceMeasurableControls.length
      ),
      riskComplianceDomainsPresent: Number(overviewStats?.risk_compliance_domains_present ?? riskComplianceDomainsPresent),
      totalRegulations: regulationSet.size || Number(overviewStats?.total_regulations ?? regulationsPayload?.total ?? 0),
      totalJurisdictions: Number(overviewStats?.total_jurisdictions ?? Object.keys(jurisdictionCounts).length),
      totalIndustryCategories: Math.max(0, INDUSTRY_LIBRARY.length - 1),
      telemetryReadings: Number(telemetry?.total_readings ?? 0),
      telemetryStatus: String(telemetry?.status || 'N/A'),
      totalInterpretations: Number(overviewStats?.total_interpretations ?? 0),
      regulations: Array.from(regulationSet).sort((a, b) => a.localeCompare(b)).slice(0, 18),
      topJurisdictions,
      regionCounts,
    });

    if (failed.length > 0) {
      setOverviewError(`Some system data is unavailable: ${failed.join(', ')}`);
    }
    setOverviewLoading(false);
  }, []);

  useEffect(() => {
    if (!selectedApp) {
      loadSystemOverview();
    }
  }, [loadSystemOverview, selectedApp]);

  useEffect(() => {
    setActiveStep(null);
    setLoadingStepDetail(false);
    setStepDetailError('');
    setShowAllCorporate(false);
    setShowAllMandatory(false);
    setShowAllTechnical(false);
    setShowAllDataReadiness(false);
    setShowAllDataIntegration(false);
    setShowAllSecurity(false);
    setShowAllInfrastructure(false);
    setShowAllSolutionDesign(false);
    setShowAllSystemPerformance(false);
    setDetailCache({
      benchmarks: null,
      history: null,
      recommendations: null,
      dashboardStep1: null,
      dashboardStep2: null,
      dashboardStep3: null,
      dashboardStep4: null,
      dashboardStep5: null,
      dashboardStep6: null,
      dashboardStep7: null,
      dashboardStep8: null,
      dashboardStep9: null,
    });
    setInterpretationRequirements([]);
    setInterpretationRows([]);
    setInterpretationLoading(false);
    setInterpretationSaving(false);
    setInterpretationError('');
    setInterpretationNotice('');
    setInterpretationDraft({
      requirementId: '',
      controlId: '',
      content: '',
      thresholdEnabled: false,
      thresholdOperator: 'lte',
      thresholdValue: '',
      thresholdMin: '',
      thresholdMax: '',
    });
    setRequirementFilter('');
    setScopedRequirementIds([]);
    setShowScopedOnly(true);
    setScopeSaving(false);
    setScopeError('');
    setScopeNotice('');
    setCatalogSearchQuery('');
    setCatalogSearchLoading(false);
    setCatalogSearchError('');
    setCatalogSearchResults([]);
    setIndustryCategory('all');
  }, [selectedApp?.id]);

  const loadInterpretationRows = useCallback(async (requirementId) => {
    if (!selectedApp?.id || !requirementId) {
      setInterpretationRows([]);
      return;
    }

    setInterpretationLoading(true);
    setInterpretationError('');
    try {
      const payload = await api.getApplicationInterpretations(selectedApp.id);
      const rows = Array.isArray(payload)
        ? payload.filter((item) => item.requirement_id === requirementId)
        : [];
      setInterpretationRows(rows);
    } catch (e) {
      setInterpretationRows([]);
      setInterpretationError(e.message || 'Failed to load interpretations');
    } finally {
      setInterpretationLoading(false);
    }
  }, [selectedApp?.id]);

  const loadRequirementScope = useCallback(async () => {
    if (!selectedApp?.id) {
      setInterpretationRequirements([]);
      setScopedRequirementIds([]);
      return [];
    }

    const payload = await api.getApplicationRequirements(selectedApp.id, 'limit=300');
    const items = (payload.items || []).map(normalizeRequirementItem);
    const selectedIds = items.filter((item) => item.selected).map((item) => item.id);

    setInterpretationRequirements(items);
    setScopedRequirementIds(selectedIds);
    setInterpretationDraft((prev) => {
      const hasRequirement = prev.requirementId && items.some((item) => item.id === prev.requirementId);
      const nextRequirementId = hasRequirement
        ? prev.requirementId
        : (selectedIds[0] || items[0]?.id || '');
      return {
        ...prev,
        requirementId: nextRequirementId,
        controlId: resolveDefaultControlId(nextRequirementId, items, prev.controlId),
      };
    });
    return items;
  }, [selectedApp?.id]);

  const filteredRequirements = useMemo(() => {
    const q = requirementFilter.trim().toLowerCase();
    if (!q) {
      return interpretationRequirements;
    }
    return interpretationRequirements.filter((req) =>
      `${req.code} ${req.title} ${req.regulation_title || ''} ${req.jurisdiction || ''}`
        .toLowerCase()
        .includes(q)
    );
  }, [interpretationRequirements, requirementFilter]);

  const scopedRequirementSet = useMemo(
    () => new Set(scopedRequirementIds),
    [scopedRequirementIds]
  );

  const interpretationRequirementOptions = useMemo(() => {
    const hasScopedRequirements = scopedRequirementIds.length > 0;
    if (!showScopedOnly || !hasScopedRequirements) {
      return filteredRequirements;
    }
    return filteredRequirements.filter((req) => scopedRequirementSet.has(req.id));
  }, [filteredRequirements, scopedRequirementIds.length, scopedRequirementSet, showScopedOnly]);

  const selectedInterpretationRequirement = useMemo(() => (
    interpretationRequirementOptions.find((item) => item.id === interpretationDraft.requirementId)
    || interpretationRequirements.find((item) => item.id === interpretationDraft.requirementId)
    || null
  ), [interpretationDraft.requirementId, interpretationRequirementOptions, interpretationRequirements]);

  const interpretationControlOptions = useMemo(
    () => selectedInterpretationRequirement?.linked_controls || [],
    [selectedInterpretationRequirement]
  );

  const defaultRequirementCount = useMemo(
    () => interpretationRequirements.filter((item) => item.is_default).length,
    [interpretationRequirements]
  );

  const selectedDefaultCount = useMemo(
    () => interpretationRequirements.filter((item) => item.is_default && scopedRequirementSet.has(item.id)).length,
    [interpretationRequirements, scopedRequirementSet]
  );

  const selectedCustomCount = useMemo(
    () => interpretationRequirements.filter((item) => !item.is_default && scopedRequirementSet.has(item.id)).length,
    [interpretationRequirements, scopedRequirementSet]
  );

  const defaultFilteredRequirements = useMemo(
    () => filteredRequirements.filter((item) => item.is_default),
    [filteredRequirements]
  );

  const customFilteredRequirements = useMemo(
    () => filteredRequirements.filter((item) => !item.is_default),
    [filteredRequirements]
  );

  const activeCustomRequirements = useMemo(
    () => interpretationRequirements.filter((item) => !item.is_default && scopedRequirementSet.has(item.id)),
    [interpretationRequirements, scopedRequirementSet]
  );

  const benchmarkByMetric = useMemo(() => {
    const map = new Map();
    (detailCache.benchmarks?.benchmarks || []).forEach((item) => {
      if (item?.metric_name) {
        map.set(String(item.metric_name), item);
      }
    });
    return map;
  }, [detailCache.benchmarks]);

  const requirementsById = useMemo(
    () => new Map(interpretationRequirements.map((item) => [item.id, item])),
    [interpretationRequirements]
  );

  const controlToRequirementIds = useMemo(() => {
    const map = new Map();
    interpretationRequirements.forEach((req) => {
      (req.linked_controls || []).forEach((control) => {
        const key = String(control.id);
        if (!map.has(key)) {
          map.set(key, []);
        }
        map.set(key, [...map.get(key), req.id]);
      });
    });
    return map;
  }, [interpretationRequirements]);

  const recommendedControlIdSet = useMemo(
    () => new Set((detailCache.recommendations?.recommendations || []).map((item) => String(item.control_id))),
    [detailCache.recommendations]
  );

  const serverScopedRequirementIds = useMemo(
    () => interpretationRequirements.filter((item) => item.selected).map((item) => item.id),
    [interpretationRequirements]
  );

  const scopeAddedCount = useMemo(
    () => scopedRequirementIds.filter((id) => !serverScopedRequirementIds.includes(id)).length,
    [scopedRequirementIds, serverScopedRequirementIds]
  );

  const scopeRemovedCount = useMemo(
    () => serverScopedRequirementIds.filter((id) => !scopedRequirementSet.has(id)).length,
    [serverScopedRequirementIds, scopedRequirementSet]
  );

  const isScopeDirty = useMemo(
    () => !sameStringSet(scopedRequirementIds, serverScopedRequirementIds),
    [scopedRequirementIds, serverScopedRequirementIds]
  );

  const suggestedRequirements = useMemo(
    () => interpretationRequirements
      .filter((req) => (
        !req.is_default
        && !scopedRequirementSet.has(req.id)
        && (req.linked_controls || []).some((ctrl) => recommendedControlIdSet.has(String(ctrl.id)))
      ))
      .slice(0, 20),
    [interpretationRequirements, recommendedControlIdSet, scopedRequirementSet]
  );

  const industryFilteredSuggestions = useMemo(
    () => suggestedRequirements.filter((req) => matchesIndustryRequirement(req, industryCategory)),
    [suggestedRequirements, industryCategory]
  );

  const suggestedRequirementIds = useMemo(
    () => suggestedRequirements.map((item) => item.id),
    [suggestedRequirements]
  );

  const industryFilteredCustomRequirements = useMemo(
    () => customFilteredRequirements.filter((req) => matchesIndustryRequirement(req, industryCategory)),
    [customFilteredRequirements, industryCategory]
  );

  const addableIndustryRequirementIds = useMemo(
    () => industryFilteredCustomRequirements
      .filter((req) => !scopedRequirementSet.has(req.id))
      .map((req) => req.id),
    [industryFilteredCustomRequirements, scopedRequirementSet]
  );

  const selectedInterpretationControl = useMemo(
    () => interpretationControlOptions.find((item) => item.id === interpretationDraft.controlId) || null,
    [interpretationControlOptions, interpretationDraft.controlId]
  );

  const thresholdDraftResult = useMemo(
    () => buildThresholdOverrideFromDraft(interpretationDraft),
    [interpretationDraft]
  );

  const permissivenessWarning = useMemo(() => {
    if (!interpretationDraft.thresholdEnabled || thresholdDraftResult.validationError) {
      return '';
    }
    const baseline = selectedInterpretationControl?.default_threshold;
    if (!baseline) {
      return '';
    }
    if (isMorePermissiveThreshold(thresholdDraftResult.thresholdOverride, baseline)) {
      return `Warning: this override is more permissive than platform default (${formatThresholdOverride(baseline)}).`;
    }
    return '';
  }, [
    interpretationDraft.thresholdEnabled,
    selectedInterpretationControl,
    thresholdDraftResult.thresholdOverride,
    thresholdDraftResult.validationError,
  ]);

  const toggleScopedRequirement = useCallback((requirementId) => {
    const requirement = interpretationRequirements.find((item) => item.id === requirementId);
    if (requirement?.is_default) {
      return;
    }
    setScopedRequirementIds((prev) => (
      prev.includes(requirementId)
        ? prev.filter((id) => id !== requirementId)
        : [...prev, requirementId]
    ));
  }, [interpretationRequirements]);

  const addRequirementToScope = useCallback((requirementId) => {
    setScopedRequirementIds((prev) => (
      prev.includes(requirementId) ? prev : [...prev, requirementId]
    ));
  }, []);

  const addRequirementsToScope = useCallback((requirementIds) => {
    const normalized = Array.from(new Set((requirementIds || []).filter(Boolean)));
    if (!normalized.length) {
      return;
    }
    setScopedRequirementIds((prev) => Array.from(new Set([...prev, ...normalized])));
  }, []);

  const removeRequirementFromScope = useCallback((requirementId) => {
    const requirement = interpretationRequirements.find((item) => item.id === requirementId);
    if (requirement?.is_default) {
      return;
    }
    setScopedRequirementIds((prev) => prev.filter((id) => id !== requirementId));
  }, [interpretationRequirements]);

  const addAllSuggestedToScope = useCallback(() => {
    if (!suggestedRequirementIds.length) {
      return;
    }
    setScopedRequirementIds((prev) => Array.from(new Set([...prev, ...suggestedRequirementIds])));
  }, [suggestedRequirementIds]);

  const resetScopeDraft = useCallback(() => {
    setScopedRequirementIds(serverScopedRequirementIds);
  }, [serverScopedRequirementIds]);

  const runCatalogSearch = useCallback(async () => {
    const q = catalogSearchQuery.trim();
    if (!q) {
      setCatalogSearchResults([]);
      setCatalogSearchError('');
      return;
    }
    setCatalogSearchLoading(true);
    setCatalogSearchError('');
    try {
      const payload = await api.searchCatalog(q);
      setCatalogSearchResults(payload.items || []);
    } catch (e) {
      setCatalogSearchResults([]);
      setCatalogSearchError(e.message || 'Catalog search failed');
    } finally {
      setCatalogSearchLoading(false);
    }
  }, [catalogSearchQuery]);

  const saveRequirementScope = useCallback(async () => {
    if (!selectedApp?.id) {
      return;
    }
    setScopeSaving(true);
    setScopeError('');
    setScopeNotice('');
    try {
      const uniqueIds = Array.from(new Set(scopedRequirementIds));
      const result = await api.setApplicationRequirements(selectedApp.id, uniqueIds);
      setScopeNotice(`Saved scope with ${result.selected_count} requirement(s)`);
      await loadRequirementScope();
    } catch (e) {
      setScopeError(e.message || 'Failed to save application requirement scope');
    } finally {
      setScopeSaving(false);
    }
  }, [loadRequirementScope, scopedRequirementIds, selectedApp?.id]);

  const loadStepDetail = useCallback(async (stepNum) => {
    setActiveStep(stepNum);
    setStepDetailError('');

    if (!selectedApp?.id || (stepNum !== 1 && stepNum !== 2 && stepNum !== 3 && stepNum !== 4 && stepNum !== 5 && stepNum !== 6 && stepNum !== 7 && stepNum !== 8 && stepNum !== 9)) {
      return;
    }

    // Always refresh step rows on selection so newly ingested telemetry appears immediately.

    setLoadingStepDetail(true);
    try {
      if (stepNum === 1) {
        const dashboardStep = await api.getApplicationDashboardStep(selectedApp.id, 1);
        setDetailCache((prev) => ({ ...prev, dashboardStep1: dashboardStep }));
      } else if (stepNum === 2) {
        const failed = [];
        await loadRequirementScope();
        try {
          const dashboardStep = await api.getApplicationDashboardStep(selectedApp.id, 2);
          setDetailCache((prev) => ({ ...prev, dashboardStep2: dashboardStep }));
        } catch {
          failed.push('dashboard_step_2');
        }
        if (!detailCache.history) {
          try {
            const history = await api.getTierHistory(selectedApp.id);
            setDetailCache((prev) => ({ ...prev, history }));
          } catch {
            failed.push('tier_history');
          }
        }
        if (!detailCache.recommendations) {
          try {
            const recommendations = await api.getRecommendations(selectedApp.id);
            setDetailCache((prev) => ({ ...prev, recommendations }));
          } catch {
            failed.push('recommendations');
          }
        }
        if (!detailCache.benchmarks) {
          try {
            const benchmarks = await api.getBenchmarks(selectedApp.id);
            setDetailCache((prev) => ({ ...prev, benchmarks }));
          } catch {
            failed.push('benchmarks');
          }
        }
        if (failed.length > 0) {
          setStepDetailError(`Some step 2 data is unavailable: ${failed.join(', ')}`);
        }
      } else if (stepNum === 3) {
        const dashboardStep = await api.getApplicationDashboardStep(selectedApp.id, 3);
        setDetailCache((prev) => ({
          ...prev,
          dashboardStep3: dashboardStep,
        }));
      } else if (stepNum === 4) {
        const dashboardStep = await api.getApplicationDashboardStep(selectedApp.id, 4);
        setDetailCache((prev) => ({ ...prev, dashboardStep4: dashboardStep }));
      } else if (stepNum === 5) {
        const dashboardStep = await api.getApplicationDashboardStep(selectedApp.id, 5);
        setDetailCache((prev) => ({ ...prev, dashboardStep5: dashboardStep }));
      } else if (stepNum === 6) {
        const dashboardStep = await api.getApplicationDashboardStep(selectedApp.id, 6);
        setDetailCache((prev) => ({ ...prev, dashboardStep6: dashboardStep }));
      } else if (stepNum === 7) {
        const dashboardStep = await api.getApplicationDashboardStep(selectedApp.id, 7);
        setDetailCache((prev) => ({ ...prev, dashboardStep7: dashboardStep }));
      } else if (stepNum === 8) {
        const dashboardStep = await api.getApplicationDashboardStep(selectedApp.id, 8);
        setDetailCache((prev) => ({ ...prev, dashboardStep8: dashboardStep }));
      } else if (stepNum === 9) {
        const dashboardStep = await api.getApplicationDashboardStep(selectedApp.id, 9);
        setDetailCache((prev) => ({ ...prev, dashboardStep9: dashboardStep }));
      }
    } catch (e) {
      setStepDetailError(e.message || 'Failed to load step detail');
    } finally {
      setLoadingStepDetail(false);
    }
  }, [detailCache.benchmarks, detailCache.dashboardStep9, detailCache.dashboardStep8, detailCache.dashboardStep7, detailCache.dashboardStep6, detailCache.dashboardStep5, detailCache.dashboardStep4, detailCache.dashboardStep3, detailCache.dashboardStep2, detailCache.dashboardStep1, detailCache.history, detailCache.recommendations, interpretationRequirements.length, loadRequirementScope, selectedApp?.id]);

  useEffect(() => {
    if (!requestedStep?.stepNum) {
      return;
    }
    loadStepDetail(requestedStep.stepNum);
    setTimeout(() => detailSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
  }, [requestedStep?.token]);

  useEffect(() => {
    if (!selectedApp?.id || !activeStep) {
      return undefined;
    }
    const liveSteps = new Set([1, 3, 4, 5, 6, 7, 8, 9]);
    if (!liveSteps.has(activeStep)) {
      return undefined;
    }

    const handle = setInterval(() => {
      loadStepDetail(activeStep);
    }, 15000);

    return () => clearInterval(handle);
  }, [activeStep, loadStepDetail, selectedApp?.id]);


  useEffect(() => {
    if (activeStep !== 2 || !interpretationDraft.requirementId) {
      return;
    }
    loadInterpretationRows(interpretationDraft.requirementId);
  }, [activeStep, interpretationDraft.requirementId, loadInterpretationRows]);

  useEffect(() => {
    if (activeStep !== 2) {
      return;
    }
    if (!interpretationRequirementOptions.some((item) => item.id === interpretationDraft.requirementId)) {
      const nextRequirementId = interpretationRequirementOptions[0]?.id || '';
      setInterpretationDraft((prev) => ({
        ...prev,
        requirementId: nextRequirementId,
        controlId: resolveDefaultControlId(nextRequirementId, interpretationRequirements, prev.controlId),
      }));
      return;
    }
    if (!interpretationControlOptions.some((item) => item.id === interpretationDraft.controlId)) {
      setInterpretationDraft((prev) => ({
        ...prev,
        controlId: resolveDefaultControlId(prev.requirementId, interpretationRequirements, prev.controlId),
      }));
    }
  }, [
    activeStep,
    interpretationControlOptions,
    interpretationDraft.controlId,
    interpretationDraft.requirementId,
    interpretationRequirementOptions,
    interpretationRequirements,
  ]);

  const submitInterpretation = useCallback(async (event) => {
    event.preventDefault();
    if (!selectedApp?.id) {
      return;
    }
    const requirementId = interpretationDraft.requirementId;
    const controlId = interpretationDraft.controlId;
    const content = interpretationDraft.content.trim();
    const { thresholdOverride, validationError } = buildThresholdOverrideFromDraft(interpretationDraft);
    const existingRow = interpretationRows.find(
      (row) => row.requirement_id === requirementId && row.control_id === controlId
    );
    if (!requirementId) {
      setInterpretationError('Select a requirement before submitting an interpretation');
      return;
    }
    if (!controlId) {
      setInterpretationError('Select a linked control before submitting an interpretation');
      return;
    }
    if (validationError) {
      setInterpretationError(validationError);
      return;
    }
    if (!content && !thresholdOverride) {
      setInterpretationError('Provide interpretation text or enable threshold override.');
      return;
    }
    if (!content && thresholdOverride && !existingRow) {
      setInterpretationError('First save for this requirement/control needs interpretation text.');
      return;
    }

    setInterpretationSaving(true);
    setInterpretationError('');
    setInterpretationNotice('');
    try {
      const actor = selectedApp.owner_email || 'application_owner';
      let saved;
      if (!content && thresholdOverride && existingRow) {
        saved = await api.patchApplicationInterpretation(selectedApp.id, existingRow.id, {
          threshold_override: thresholdOverride,
          set_by: actor,
        });
      } else {
        saved = await api.createApplicationInterpretation(selectedApp.id, {
          requirement_id: requirementId,
          control_id: controlId,
          interpretation_text: content || null,
          threshold_override: thresholdOverride,
          set_by: actor,
        });
      }

      setInterpretationDraft((prev) => ({
        ...prev,
        content: '',
        thresholdEnabled: false,
        thresholdOperator: 'lte',
        thresholdValue: '',
        thresholdMin: '',
        thresholdMax: '',
      }));
      setInterpretationNotice(
        thresholdOverride
          ? `Saved interpretation + threshold override for ${saved.control_code || saved.control_id}`
          : `Saved interpretation for ${saved.control_code || saved.control_id}`
      );
      await loadInterpretationRows(requirementId);
    } catch (e) {
      setInterpretationError(e.message || 'Failed to create interpretation');
    } finally {
      setInterpretationSaving(false);
    }
  }, [interpretationDraft, interpretationRows, loadInterpretationRows, selectedApp?.id, selectedApp?.owner_email]);

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
        if (selectedApp) {
          const oversightRows = buildCorporateOversightRows(
            selectedApp,
            snapshot,
            detailCache.dashboardStep1?.summary,
            detailCache.dashboardStep1?.rows
          );
          const fail = oversightRows.filter((row) => row.result === 'FAIL').length;
          return {
            ...step,
            status: oversightRows.length ? 'complete' : 'attention',
            note: `Corporate KPIs: ${oversightRows.length} | fail: ${fail}`,
          };
        }
        return { ...step, status: 'pending', note: 'No selected app' };
      }
      if (step.num === 2) {
        const scoped = scopedRequirementIds.length;
        if (detailCache.dashboardStep2) {
          const total = detailCache.dashboardStep2.row_count || 0;
          const fail = (detailCache.dashboardStep2.rows || []).filter((r) => r.result === 'FAIL').length;
          return {
            ...step,
            status: total > 0 ? 'complete' : 'attention',
            note: `Baseline KPIs: ${total} | fail: ${fail} | scoped reqs: ${scoped}`,
          };
        }
        return {
          ...step,
          status: hasTier ? 'attention' : 'pending',
          note: hasTier
            ? `Tier assigned: ${normalizeRiskTier(snapshot.tier.current_tier) || snapshot.tier.current_tier} | scoped reqs: ${scoped}`
            : 'Tier unavailable',
        };
      }
      if (step.num === 3) {
        if (detailCache.dashboardStep3) {
          const total = detailCache.dashboardStep3.row_count || 0;
          const fail = (detailCache.dashboardStep3.rows || []).filter((r) => r.result === 'FAIL').length;
          return {
            ...step,
            status: total > 0 ? 'complete' : 'attention',
            note: `Rows: ${total} | fail: ${fail}`,
          };
        }
        return {
          ...step,
          status: hasTier ? 'attention' : 'pending',
          note: hasTier ? 'Click row to load technical architecture KPIs' : 'Requires tier assignment first',
        };
      }
      if (step.num === 4) {
        if (detailCache.dashboardStep4) {
          const total = detailCache.dashboardStep4.row_count || 0;
          const pass = (detailCache.dashboardStep4.rows || []).filter((r) => r.result === 'PASS').length;
          return {
            ...step,
            status: total > 0 ? 'complete' : 'attention',
            note: `Rows: ${total} | pass: ${pass}`,
          };
        }
        return {
          ...step,
          status: hasCompliance ? 'attention' : 'pending',
          note: hasCompliance ? 'Click row to load data-readiness KPIs' : 'Compliance summary required first',
        };
      }
      if (step.num === 5) {
        if (detailCache.dashboardStep5) {
          const total = detailCache.dashboardStep5.row_count || 0;
          const fail = (detailCache.dashboardStep5.rows || []).filter((r) => r.result === 'FAIL').length;
          return {
            ...step,
            status: total > 0 ? 'complete' : 'attention',
            note: `Rows: ${total} | fail: ${fail}`,
          };
        }
        return {
          ...step,
          status: hasTier ? 'attention' : 'pending',
          note: hasTier ? 'Click row to load data-integration KPIs' : 'Requires tier assignment first',
        };
      }
      if (step.num === 6) {
        if (detailCache.dashboardStep6) {
          const total = detailCache.dashboardStep6.row_count || 0;
          const fail = (detailCache.dashboardStep6.rows || []).filter((r) => r.result === 'FAIL').length;
          return {
            ...step,
            status: total > 0 ? 'complete' : 'attention',
            note: `Rows: ${total} | fail: ${fail}`,
          };
        }
        return {
          ...step,
          status: hasTier ? 'attention' : 'pending',
          note: hasTier ? 'Click row to load security KPIs' : 'Requires tier assignment first',
        };
      }
      if (step.num === 7) {
        if (detailCache.dashboardStep7) {
          const total = detailCache.dashboardStep7.row_count || 0;
          const fail = (detailCache.dashboardStep7.rows || []).filter((r) => r.result === 'FAIL').length;
          return {
            ...step,
            status: total > 0 ? 'complete' : 'attention',
            note: `Rows: ${total} | fail: ${fail}`,
          };
        }
        return {
          ...step,
          status: hasTier ? 'attention' : 'pending',
          note: hasTier ? 'Click row to load infrastructure KPIs' : 'Requires tier assignment first',
        };
      }
      if (step.num === 8) {
        if (detailCache.dashboardStep8) {
          const total = detailCache.dashboardStep8.row_count || 0;
          const fail = (detailCache.dashboardStep8.rows || []).filter((r) => r.result === 'FAIL').length;
          return {
            ...step,
            status: total > 0 ? 'complete' : 'attention',
            note: `Rows: ${total} | fail: ${fail}`,
          };
        }
        return {
          ...step,
          status: hasTier ? 'attention' : 'pending',
          note: hasTier ? 'Click row to load solution-design KPIs' : 'Requires tier assignment first',
        };
      }
      if (step.num === 9) {
        if (detailCache.dashboardStep9) {
          const total = detailCache.dashboardStep9.row_count || 0;
          const fail = (detailCache.dashboardStep9.rows || []).filter((r) => r.result === 'FAIL').length;
          return {
            ...step,
            status: total > 0 ? 'complete' : 'attention',
            note: `Rows: ${total} | fail: ${fail}`,
          };
        }
        return {
          ...step,
          status: hasTier ? 'attention' : 'pending',
          note: hasTier ? 'Click row to load system-performance KPIs' : 'Requires tier assignment first',
        };
      }
      return { ...step, status: 'pending', note: 'Panel wiring next increment' };
    });
  }, [detailCache.benchmarks, detailCache.dashboardStep9, detailCache.dashboardStep8, detailCache.dashboardStep7, detailCache.dashboardStep6, detailCache.dashboardStep5, detailCache.dashboardStep4, detailCache.dashboardStep3, detailCache.dashboardStep2, detailCache.dashboardStep1, detailCache.dashboardStep1?.rows, detailCache.history, detailCache.recommendations, scopedRequirementIds.length, selectedApp, snapshot]);

  const totalKpis = useMemo(() => {
    if (!selectedApp) {
      return null;
    }
    const step1Count = buildCorporateOversightRows(
      selectedApp,
      snapshot,
      detailCache.dashboardStep1?.summary,
      detailCache.dashboardStep1?.rows
    ).length;
    const stepCounts = [2, 3, 4, 5, 6, 7, 8, 9]
      .map((stepNum) => {
        const rowCount = detailCache[`dashboardStep${stepNum}`]?.row_count;
        return typeof rowCount === 'number' ? rowCount : 0;
      })
      .reduce((sum, count) => sum + count, 0);
    return step1Count + stepCounts;
  }, [
    detailCache.dashboardStep1?.summary,
    detailCache.dashboardStep1?.rows,
    detailCache.dashboardStep2?.row_count,
    detailCache.dashboardStep3?.row_count,
    detailCache.dashboardStep4?.row_count,
    detailCache.dashboardStep5?.row_count,
    detailCache.dashboardStep6?.row_count,
    detailCache.dashboardStep7?.row_count,
    detailCache.dashboardStep8?.row_count,
    detailCache.dashboardStep9?.row_count,
    selectedApp,
    snapshot,
  ]);

  const complianceSummary = useMemo(() => {
    if (!selectedApp) {
      return null;
    }

    const step1Rows = buildCorporateOversightRows(
      selectedApp,
      snapshot,
      detailCache.dashboardStep1?.summary,
      detailCache.dashboardStep1?.rows
    );
    const scopedRows = [
      ...(detailCache.dashboardStep2?.rows || []),
      ...(detailCache.dashboardStep3?.rows || []),
      ...(detailCache.dashboardStep4?.rows || []),
      ...(detailCache.dashboardStep5?.rows || []),
      ...(detailCache.dashboardStep6?.rows || []),
      ...(detailCache.dashboardStep7?.rows || []),
      ...(detailCache.dashboardStep8?.rows || []),
      ...(detailCache.dashboardStep9?.rows || []),
    ];
    const allRows = [...step1Rows, ...scopedRows];

    const evaluated = allRows.filter((row) => row.result !== 'INSUFFICIENT_DATA').length;
    const passCount = allRows.filter((row) => row.result === 'PASS').length;
    const failCount = allRows.filter((row) => row.result === 'FAIL').length;
    const noDataCount = allRows.filter((row) => row.result === 'INSUFFICIENT_DATA').length;
    const overallPassRate = evaluated > 0 ? (passCount / evaluated) : null;

    return {
      overall_pass_rate: overallPassRate,
      evaluated_count: evaluated,
      pass_count: passCount,
      fail_count: failCount,
      no_data_count: noDataCount,
      step1_fail_count: step1Rows.filter((row) => row.result === 'FAIL').length,
      step1_total: step1Rows.length,
      step2_total: detailCache.dashboardStep2?.row_count ?? 0,
      step2_pass_rate: toRatio(snapshot?.compliance?.pass_rate),
    };
  }, [
    detailCache.dashboardStep1?.summary,
    detailCache.dashboardStep1?.rows,
    detailCache.dashboardStep2?.row_count,
    detailCache.dashboardStep2?.rows,
    detailCache.dashboardStep3?.rows,
    detailCache.dashboardStep4?.rows,
    detailCache.dashboardStep5?.rows,
    detailCache.dashboardStep6?.rows,
    detailCache.dashboardStep7?.rows,
    detailCache.dashboardStep8?.rows,
    detailCache.dashboardStep9?.rows,
    selectedApp,
    snapshot,
  ]);

  useEffect(() => {
    if (!onDashboardUiChange) {
      return;
    }
    onDashboardUiChange({
      activeStep,
      stepRows,
      snapshot,
      loading,
      error,
      selectedAppId: selectedApp?.id || null,
      totalKpis,
      complianceSummary,
    });
  }, [activeStep, complianceSummary, error, loading, onDashboardUiChange, selectedApp?.id, snapshot, stepRows, totalKpis]);

  if (!selectedApp) {
    const riskComplianceDomainTarget = 5;
    const telemetryState = String(systemOverview.telemetryStatus || '').trim().toLowerCase();
    const telemetryHealthy = ['healthy', 'ok', 'up', 'running'].includes(telemetryState);

    return (
      <div className="system-frontpage">
        <div className="card system-frontpage-hero">
          <p className="system-frontpage-title">
            No application selected
          </p>
          <p className="system-frontpage-subtitle">
            Select a connected application from the sidebar to view its governance pipeline.
          </p>
          {overviewLoading && (
            <p className="system-frontpage-note">Loading system-wide governance overview...</p>
          )}
          {overviewError && (
            <div className="alert alert-warning" style={{ marginTop: '0.7rem' }}>
              {overviewError}
            </div>
          )}
          <div className="system-frontpage-hero-meta">
            <span className={`system-frontpage-pill ${telemetryHealthy ? 'is-good' : 'is-warning'}`}>
              Telemetry: {systemOverview.telemetryStatus || 'N/A'}
            </span>
            <span className="system-frontpage-pill">
              Peer-ready metrics: {systemOverview.peerBenchmarkedMetrics}/{systemOverview.distinctMeasureMetrics}
            </span>
            <span className="system-frontpage-pill">
              Interpretation records: {systemOverview.totalInterpretations}
            </span>
          </div>
        </div>

        <div className="system-frontpage-tiles system-frontpage-tiles-compact">
          <div className="system-frontpage-tile">
            <span className="system-frontpage-tile-label">Connected Apps</span>
            <span className="system-frontpage-tile-value">{systemOverview.connectedApps}</span>
          </div>
          <div className="system-frontpage-tile">
            <span className="system-frontpage-tile-label">Distinct Rules</span>
            <span className="system-frontpage-tile-value">{systemOverview.distinctRules}</span>
          </div>
          <div className="system-frontpage-tile">
            <span className="system-frontpage-tile-label">Distinct Controls</span>
            <span className="system-frontpage-tile-value">{systemOverview.distinctControls}</span>
          </div>
          <div className="system-frontpage-tile">
            <span className="system-frontpage-tile-label">Measure Definitions</span>
            <span className="system-frontpage-tile-value">{systemOverview.totalMeasureDefinitions}</span>
          </div>
          <div className="system-frontpage-tile">
            <span className="system-frontpage-tile-label">Regulations</span>
            <span className="system-frontpage-tile-value">{systemOverview.totalRegulations}</span>
          </div>
          <div className="system-frontpage-tile">
            <span className="system-frontpage-tile-label">Jurisdictions</span>
            <span className="system-frontpage-tile-value">{systemOverview.totalJurisdictions}</span>
          </div>
        </div>

        <div className="system-frontpage-cockpit-grid">
          <div className="card system-frontpage-panel system-frontpage-cockpit-card">
            <div className="system-frontpage-panel-title">Global Coverage</div>
            <CoverageTrack
              label="Rules mapped to controls"
              value={systemOverview.rulesWithControls}
              total={systemOverview.distinctRules}
              tone="blue"
            />
            <CoverageTrack
              label="Rules with measurable KPIs"
              value={systemOverview.rulesWithMeasures}
              total={systemOverview.distinctRules}
              tone="teal"
            />
            <CoverageTrack
              label="Controls with measure mappings"
              value={systemOverview.controlsWithMeasures}
              total={systemOverview.distinctControls}
              tone="amber"
            />
            <CoverageTrack
              label="Metrics with peer benchmark data"
              value={systemOverview.peerBenchmarkedMetrics}
              total={systemOverview.distinctMeasureMetrics}
              tone="rose"
            />
          </div>

          <div className="card system-frontpage-panel system-frontpage-cockpit-card">
            <div className="system-frontpage-panel-title">Risk & Compliance Coverage</div>
            <CoverageTrack
              label="R&C controls measurable"
              value={systemOverview.riskComplianceMeasurableControls}
              total={systemOverview.riskComplianceControls}
              tone="amber"
            />
            <CoverageTrack
              label="R&C governance domains represented"
              value={systemOverview.riskComplianceDomainsPresent}
              total={riskComplianceDomainTarget}
              tone="teal"
            />
            <CoverageTrack
              label="Interpreted rules in catalog"
              value={systemOverview.totalInterpretations}
              total={systemOverview.rulesWithControls}
              tone="blue"
            />
            <CoverageTrack
              label="Industry + peer benchmark readiness"
              value={systemOverview.peerBenchmarkedMetrics}
              total={systemOverview.distinctMeasureMetrics}
              tone="rose"
            />
            <div className="system-frontpage-kicker-row">
              <span className="system-frontpage-kicker">
                Governance Categories: {systemOverview.distinctControlDomains}
              </span>
              <span className="system-frontpage-kicker">
                Rule-Control Links: {systemOverview.totalRuleControlLinks}
              </span>
              <span className="system-frontpage-kicker">
                Industry Taxonomy: {systemOverview.totalIndustryCategories}
              </span>
            </div>
          </div>
        </div>

        <div className="system-frontpage-grid">
          <div className="card system-frontpage-panel">
            <div className="system-frontpage-panel-title">Regulation Universe</div>
            <div className="system-frontpage-chip-list">
              {systemOverview.regulations.length ? (
                systemOverview.regulations.map((name) => (
                  <span key={name} className="system-frontpage-chip">{name}</span>
                ))
              ) : (
                <span className="system-frontpage-muted">No regulations loaded yet.</span>
              )}
            </div>
            <div className="system-frontpage-panel-title" style={{ marginTop: '0.75rem' }}>Top Jurisdictions</div>
            <div className="system-frontpage-jurisdictions">
              {systemOverview.topJurisdictions.length ? (
                systemOverview.topJurisdictions.map((item) => (
                  <span key={`jur-${item.name}`} className="system-frontpage-jurisdiction-item">
                    <span>{item.name}</span>
                    <strong>{item.count}</strong>
                  </span>
                ))
              ) : (
                <span className="system-frontpage-muted">No jurisdiction data loaded yet.</span>
              )}
            </div>
          </div>

          <div className="card system-frontpage-panel">
            <div className="system-frontpage-panel-title">Regulatory Geography</div>
            <p className="system-frontpage-muted" style={{ marginBottom: '0.55rem' }}>
              Regional distribution of jurisdiction references across the governance catalog.
            </p>
            <SystemGeoMap regionCounts={systemOverview.regionCounts} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      {error && <div className="alert alert-warning">{error}</div>}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {!activeStep && (
          <div style={{ padding: '1rem 1.25rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Select a step from the left menu to view details.
          </div>
        )}

        {activeStep && (
          <div ref={detailSectionRef} style={{ borderTop: '1px solid var(--border)', padding: '1rem 1.25rem' }}>
              <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, marginBottom: '0.5rem' }}>
                {activeStep === 3
                  ? 'Step 3 Detail: Technical Architecture'
                  : activeStep === 4
                    ? 'Step 4 Detail: Data Readiness Evidence'
                    : activeStep === 1
                    ? 'Step 1 Detail: Corporate Oversight'
                    : activeStep === 2
                ? 'Step 2 Detail: Risk & Compliance'
                      : activeStep === 5
                        ? 'Step 5 Detail: Data Integration'
                        : activeStep === 6
                          ? 'Step 6 Detail: Security'
                  : activeStep === 7
                    ? 'Step 7 Detail: Infrastructure'
                    : activeStep === 8
                      ? 'Step 8 Detail: Solution Design'
                      : 'Step 9 Detail: System Performance'}
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

            {!loadingStepDetail && !stepDetailError && activeStep !== 1 && (
              <StepBasicPanel
                activeStep={activeStep}
                selectedApp={selectedApp}
                snapshot={snapshot}
                fmtDateTime={fmtDateTime}
                fmtNum={fmtNum}
              />
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 1 && (
              <div style={{ marginTop: '1rem', display: 'grid', gap: '0.75rem' }}>
                <div className="card card-flat">
                  {(() => {
                    const corporateRows = buildCorporateOversightRows(
                      selectedApp,
                      snapshot,
                      detailCache.dashboardStep1?.summary,
                      detailCache.dashboardStep1?.rows
                    );
                    const prioritizedRows = [...corporateRows].sort((a, b) => {
                      const aHasValue = typeof a?.value === 'number' && !Number.isNaN(a.value);
                      const bHasValue = typeof b?.value === 'number' && !Number.isNaN(b.value);
                      if (aHasValue !== bHasValue) {
                        return aHasValue ? -1 : 1;
                      }
                      return 0;
                    });
                    const visibleRows = showAllCorporate ? prioritizedRows : prioritizedRows.slice(0, 5);
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.6rem', marginBottom: '0.45rem' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.82rem' }}>
                            Mandatory Requirements - Corporate Oversight
                          </div>
                          {corporateRows.length > 5 && (
                            <button
                              type="button"
                              className="btn btn-outline btn-xs"
                              onClick={() => setShowAllCorporate((prev) => !prev)}
                            >
                              {showAllCorporate ? 'Show Top 5' : `Show All (${corporateRows.length})`}
                            </button>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.55rem' }}>
                          Live application telemetry
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.55rem' }}>
                          <span className="badge badge-grey">Total: {corporateRows.length}</span>
                          <span className="badge badge-grey">Showing: {visibleRows.length}</span>
                          <span className="badge badge-red">
                            FAIL: {corporateRows.filter((row) => row.result === 'FAIL').length}
                          </span>
                          <span className="badge badge-yellow">
                            NO DATA: {corporateRows.filter((row) => row.result === 'INSUFFICIENT_DATA').length}
                          </span>
                          <span className="badge badge-green">
                            PASS: {corporateRows.filter((row) => row.result === 'PASS').length}
                          </span>
                        </div>

                        {visibleRows.length ? (
                          <div style={{ display: 'grid', gap: '0.55rem' }}>
                            {visibleRows.map((row, idx) => {
                              const metricMeta = getStep2MetricMeta(row.metric_name);
                              const valueSourceLegend = getStep1ValueSourceLegend(row);
                              const rowStatusClass = row.result === 'PASS'
                                ? 'badge-green'
                                : row.result === 'FAIL'
                                  ? 'badge-red'
                                  : 'badge-yellow';
                              return (
                                <div
                                  key={`step1-${row.metric_name}-${idx}`}
                                  style={{
                                    border: '1px solid var(--border)',
                                    borderRadius: 8,
                                    padding: '0.65rem',
                                    background: 'var(--surface)',
                                    display: 'grid',
                                    gap: '0.55rem',
                                  }}
                                >
                                  <div style={{ display: 'grid', gap: '0.15rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.79rem' }}>
                                        {row.control_title || 'Control'}
                                      </div>
                                      <span className={`badge ${rowStatusClass}`} style={{ width: 'fit-content' }}>
                                        {row.result || 'N/A'}
                                      </span>
                                    </div>
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                      {row.requirement_title || 'Requirement details are not available for this row.'}
                                    </div>
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.55rem' }}>
                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Measure
                                      </span>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 600 }}>{metricMeta.label}</span>
                                      <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {metricMeta.measure}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Value
                                      </span>
                                      <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                                        {formatStep2MetricValue(row.metric_name, row.value)}
                                      </span>
                                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'flex-start' }}>
                                        <span
                                          title={valueSourceLegend}
                                          style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            width: 16,
                                            height: 16,
                                            borderRadius: '50%',
                                            border: '1px solid var(--border)',
                                            fontSize: '0.66rem',
                                            fontWeight: 700,
                                            color: 'var(--text-secondary)',
                                            background: 'var(--surface-2)',
                                            flexShrink: 0,
                                          }}
                                        >
                                          i
                                        </span>
                                      </div>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Interpretation
                                      </span>
                                      <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {getStep2InterpretationText(row)}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Benchmark
                                      </span>
                                      {renderStep2BenchmarkInline(row)}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
                            No corporate oversight KPI rows returned yet.
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 2 && (
              <div style={{ marginTop: '1rem', display: 'grid', gap: '0.75rem' }}>
                <div className="card card-flat">
                  {(() => {
                    const mandatoryRows = detailCache.dashboardStep2?.rows || [];
                    const prioritizedRows = [...mandatoryRows].sort((a, b) => {
                      const aHasValue = typeof a?.value === 'number' && !Number.isNaN(a.value);
                      const bHasValue = typeof b?.value === 'number' && !Number.isNaN(b.value);
                      if (aHasValue !== bHasValue) {
                        return aHasValue ? -1 : 1;
                      }
                      return 0;
                    });
                    const visibleRows = showAllMandatory ? prioritizedRows : prioritizedRows.slice(0, 5);
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.6rem', marginBottom: '0.45rem' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.82rem' }}>
                            Mandatory Requirements
                          </div>
                          {mandatoryRows.length > 5 && (
                            <button
                              type="button"
                              className="btn btn-outline btn-xs"
                              onClick={() => setShowAllMandatory((prev) => !prev)}
                            >
                              {showAllMandatory ? 'Show Top 5' : `Show All (${mandatoryRows.length})`}
                            </button>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.55rem' }}>
                          Live application telemetry
                        </div>
                        <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '0.45rem' }}>
                          <span className="badge badge-grey">
                            Risk Tier: {normalizeRiskTier(snapshot?.tier?.current_tier) || snapshot?.tier?.current_tier || 'N/A'}
                          </span>
                          <span className="badge badge-grey" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                            Risk Score: {typeof snapshot?.tier?.raw_score === 'number' && !Number.isNaN(snapshot.tier.raw_score) ? Math.round(snapshot.tier.raw_score) : 'N/A'}
                            <span
                              title="Risk score combines weighted factors: deployment domain, decision impact, autonomy level, population breadth, affected populations, and observed likelihood."
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                width: 14,
                                height: 14,
                                borderRadius: '50%',
                                border: '1px solid var(--border)',
                                fontSize: '0.62rem',
                                fontWeight: 700,
                                color: 'var(--text-secondary)',
                                background: 'var(--surface)',
                                cursor: 'help',
                              }}
                            >
                              i
                            </span>
                          </span>
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.55rem' }}>
                          <span className="badge badge-grey">Total: {mandatoryRows.length}</span>
                          <span className="badge badge-grey">Showing: {visibleRows.length}</span>
                          <span className="badge badge-red">
                            FAIL: {mandatoryRows.filter((row) => row.result === 'FAIL').length}
                          </span>
                          <span className="badge badge-yellow">
                            NO DATA: {mandatoryRows.filter((row) => row.result === 'INSUFFICIENT_DATA').length}
                          </span>
                          <span className="badge badge-green">
                            PASS: {mandatoryRows.filter((row) => row.result === 'PASS').length}
                          </span>
                        </div>

                        {visibleRows.length ? (
                          <div style={{ display: 'grid', gap: '0.55rem' }}>
                            {visibleRows.map((row) => {
                              const metricMeta = getStep2MetricMeta(row.metric_name);
                              const valueSourceLegend = getStep2ValueSourceLegend(row);
                              const rowStatusClass = row.result === 'PASS'
                                ? 'badge-green'
                                : row.result === 'FAIL'
                                  ? 'badge-red'
                                  : 'badge-yellow';
                              return (
                                <div
                                  key={`${row.control_id}-${row.metric_name}-${row.requirement_id || 'none'}`}
                                  style={{
                                    border: '1px solid var(--border)',
                                    borderRadius: 8,
                                    padding: '0.65rem',
                                    background: 'var(--surface)',
                                    display: 'grid',
                                    gap: '0.55rem',
                                  }}
                                >
                                  <div style={{ display: 'grid', gap: '0.15rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.79rem' }}>
                                        {row.control_title || 'Control'}
                                      </div>
                                      <span className={`badge ${rowStatusClass}`} style={{ width: 'fit-content' }}>
                                        {row.result || 'N/A'}
                                      </span>
                                    </div>
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                      {row.requirement_title || 'Requirement details are not available for this row.'}
                                    </div>
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.55rem' }}>
                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Measure
                                      </span>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 600 }}>{metricMeta.label}</span>
                                      <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {metricMeta.measure}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Value
                                      </span>
                                      <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                                        {formatStep2MetricValue(row.metric_name, row.value)}
                                      </span>
                                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'flex-start' }}>
                                        <span
                                          title={valueSourceLegend}
                                          style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            width: 16,
                                            height: 16,
                                            borderRadius: '50%',
                                            border: '1px solid var(--border)',
                                            fontSize: '0.66rem',
                                            fontWeight: 700,
                                            color: 'var(--text-secondary)',
                                            background: 'var(--surface-2)',
                                            flexShrink: 0,
                                          }}
                                        >
                                          i
                                        </span>
                                      </div>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Interpretation
                                      </span>
                                      <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {getStep2InterpretationText(row)}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Benchmark
                                      </span>
                                      {renderStep2BenchmarkInline(row)}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
                            No mandatory requirement KPI rows returned yet.
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 3 && (
              <div style={{ marginTop: '1rem', display: 'grid', gap: '0.75rem' }}>
                <div className="card card-flat">
                  {(() => {
                    const technicalRows = detailCache.dashboardStep3?.rows || [];
                    const visibleRows = showAllTechnical ? technicalRows : technicalRows.slice(0, 5);
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.6rem', marginBottom: '0.45rem' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.82rem' }}>
                            Mandatory Requirements
                          </div>
                          {technicalRows.length > 5 && (
                            <button
                              type="button"
                              className="btn btn-outline btn-xs"
                              onClick={() => setShowAllTechnical((prev) => !prev)}
                            >
                              {showAllTechnical ? 'Show Top 5' : `Show All (${technicalRows.length})`}
                            </button>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.55rem' }}>
                          Live application telemetry
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.55rem' }}>
                          <span className="badge badge-grey">Total: {technicalRows.length}</span>
                          <span className="badge badge-grey">Showing: {visibleRows.length}</span>
                          <span className="badge badge-red">
                            FAIL: {technicalRows.filter((row) => row.result === 'FAIL').length}
                          </span>
                          <span className="badge badge-yellow">
                            NO DATA: {technicalRows.filter((row) => row.result === 'INSUFFICIENT_DATA').length}
                          </span>
                          <span className="badge badge-green">
                            PASS: {technicalRows.filter((row) => row.result === 'PASS').length}
                          </span>
                        </div>

                        {detailCache.dashboardStep3?.summary?.message && (
                          <div className="alert alert-warning" style={{ marginBottom: '0.55rem' }}>
                            {detailCache.dashboardStep3.summary.message}
                          </div>
                        )}

                        {visibleRows.length ? (
                          <div style={{ display: 'grid', gap: '0.55rem' }}>
                            {visibleRows.map((row) => {
                              const metricMeta = getStep2MetricMeta(row.metric_name);
                              const valueSourceLegend = getStep2ValueSourceLegend(row);
                              const rowStatusClass = row.result === 'PASS'
                                ? 'badge-green'
                                : row.result === 'FAIL'
                                  ? 'badge-red'
                                  : 'badge-yellow';
                              return (
                                <div
                                  key={`${row.control_id}-${row.metric_name}-${row.requirement_id || 'none'}`}
                                  style={{
                                    border: '1px solid var(--border)',
                                    borderRadius: 8,
                                    padding: '0.65rem',
                                    background: 'var(--surface)',
                                    display: 'grid',
                                    gap: '0.55rem',
                                  }}
                                >
                                  <div style={{ display: 'grid', gap: '0.15rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.79rem' }}>
                                        {row.control_title || 'Control'}
                                      </div>
                                      <span className={`badge ${rowStatusClass}`} style={{ width: 'fit-content' }}>
                                        {row.result || 'N/A'}
                                      </span>
                                    </div>
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                      {row.requirement_title || 'Requirement details are not available for this row.'}
                                    </div>
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.55rem' }}>
                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Measure
                                      </span>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 600 }}>{metricMeta.label}</span>
                                      <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {metricMeta.measure}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Value
                                      </span>
                                      <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                                        {formatStep2MetricValue(row.metric_name, row.value)}
                                      </span>
                                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'flex-start' }}>
                                        <span
                                          title={valueSourceLegend}
                                          style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            width: 16,
                                            height: 16,
                                            borderRadius: '50%',
                                            border: '1px solid var(--border)',
                                            fontSize: '0.66rem',
                                            fontWeight: 700,
                                            color: 'var(--text-secondary)',
                                            background: 'var(--surface-2)',
                                            flexShrink: 0,
                                          }}
                                        >
                                          i
                                        </span>
                                      </div>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Interpretation
                                      </span>
                                      <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {row.interpretation_text || getStep2InterpretationText(row)}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Benchmark
                                      </span>
                                      {renderStep2BenchmarkInline(row)}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
                            No technical architecture KPI rows available for this application scope.
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 4 && (
              <div style={{ marginTop: '1rem', display: 'grid', gap: '0.75rem' }}>
                <div className="card card-flat">
                  {(() => {
                    const dataReadinessRows = detailCache.dashboardStep4?.rows || [];
                    const visibleRows = showAllDataReadiness ? dataReadinessRows : dataReadinessRows.slice(0, 5);
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.6rem', marginBottom: '0.45rem' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.82rem' }}>
                            Mandatory Requirements
                          </div>
                          {dataReadinessRows.length > 5 && (
                            <button
                              type="button"
                              className="btn btn-outline btn-xs"
                              onClick={() => setShowAllDataReadiness((prev) => !prev)}
                            >
                              {showAllDataReadiness ? 'Show Top 5' : `Show All (${dataReadinessRows.length})`}
                            </button>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.55rem' }}>
                          Live application telemetry
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.55rem' }}>
                          <span className="badge badge-grey">Total: {dataReadinessRows.length}</span>
                          <span className="badge badge-grey">Showing: {visibleRows.length}</span>
                          <span className="badge badge-red">
                            FAIL: {dataReadinessRows.filter((row) => row.result === 'FAIL').length}
                          </span>
                          <span className="badge badge-yellow">
                            NO DATA: {dataReadinessRows.filter((row) => row.result === 'INSUFFICIENT_DATA').length}
                          </span>
                          <span className="badge badge-green">
                            PASS: {dataReadinessRows.filter((row) => row.result === 'PASS').length}
                          </span>
                        </div>

                        {detailCache.dashboardStep4?.summary?.message && (
                          <div className="alert alert-warning" style={{ marginBottom: '0.55rem' }}>
                            {detailCache.dashboardStep4.summary.message}
                          </div>
                        )}

                        {visibleRows.length ? (
                          <div style={{ display: 'grid', gap: '0.55rem' }}>
                            {visibleRows.map((row) => {
                              const metricMeta = getStep2MetricMeta(row.metric_name);
                              const valueSourceLegend = getStep2ValueSourceLegend(row);
                              const rowStatusClass = row.result === 'PASS'
                                ? 'badge-green'
                                : row.result === 'FAIL'
                                  ? 'badge-red'
                                  : 'badge-yellow';
                              return (
                                <div
                                  key={`${row.control_id}-${row.metric_name}-${row.requirement_id || 'none'}`}
                                  style={{
                                    border: '1px solid var(--border)',
                                    borderRadius: 8,
                                    padding: '0.65rem',
                                    background: 'var(--surface)',
                                    display: 'grid',
                                    gap: '0.55rem',
                                  }}
                                >
                                  <div style={{ display: 'grid', gap: '0.15rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.79rem' }}>
                                        {row.control_title || 'Control'}
                                      </div>
                                      <span className={`badge ${rowStatusClass}`} style={{ width: 'fit-content' }}>
                                        {row.result || 'N/A'}
                                      </span>
                                    </div>
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                      {row.requirement_title || 'Requirement details are not available for this row.'}
                                    </div>
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.55rem' }}>
                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Measure
                                      </span>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 600 }}>{metricMeta.label}</span>
                                      <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {metricMeta.measure}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Value
                                      </span>
                                      <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                                        {formatStep2MetricValue(row.metric_name, row.value)}
                                      </span>
                                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'flex-start' }}>
                                        <span
                                          title={valueSourceLegend}
                                          style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            width: 16,
                                            height: 16,
                                            borderRadius: '50%',
                                            border: '1px solid var(--border)',
                                            fontSize: '0.66rem',
                                            fontWeight: 700,
                                            color: 'var(--text-secondary)',
                                            background: 'var(--surface-2)',
                                            flexShrink: 0,
                                          }}
                                        >
                                          i
                                        </span>
                                      </div>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Interpretation
                                      </span>
                                      <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {row.interpretation_text || getStep2InterpretationText(row)}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Benchmark
                                      </span>
                                      {renderStep2BenchmarkInline(row)}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
                            No data-readiness KPI rows available for this application scope.
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 5 && (
              <div style={{ marginTop: '1rem', display: 'grid', gap: '0.75rem' }}>
                <div className="card card-flat">
                  {(() => {
                    const dataIntegrationRows = detailCache.dashboardStep5?.rows || [];
                    const visibleRows = showAllDataIntegration ? dataIntegrationRows : dataIntegrationRows.slice(0, 5);
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.6rem', marginBottom: '0.45rem' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.82rem' }}>
                            Mandatory Requirements
                          </div>
                          {dataIntegrationRows.length > 5 && (
                            <button
                              type="button"
                              className="btn btn-outline btn-xs"
                              onClick={() => setShowAllDataIntegration((prev) => !prev)}
                            >
                              {showAllDataIntegration ? 'Show Top 5' : `Show All (${dataIntegrationRows.length})`}
                            </button>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.55rem' }}>
                          Live application telemetry
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.55rem' }}>
                          <span className="badge badge-grey">Total: {dataIntegrationRows.length}</span>
                          <span className="badge badge-grey">Showing: {visibleRows.length}</span>
                          <span className="badge badge-red">
                            FAIL: {dataIntegrationRows.filter((row) => row.result === 'FAIL').length}
                          </span>
                          <span className="badge badge-yellow">
                            NO DATA: {dataIntegrationRows.filter((row) => row.result === 'INSUFFICIENT_DATA').length}
                          </span>
                          <span className="badge badge-green">
                            PASS: {dataIntegrationRows.filter((row) => row.result === 'PASS').length}
                          </span>
                        </div>

                        {detailCache.dashboardStep5?.summary?.message && (
                          <div className="alert alert-warning" style={{ marginBottom: '0.55rem' }}>
                            {detailCache.dashboardStep5.summary.message}
                          </div>
                        )}

                        {visibleRows.length ? (
                          <div style={{ display: 'grid', gap: '0.55rem' }}>
                            {visibleRows.map((row) => {
                              const metricMeta = getStep2MetricMeta(row.metric_name);
                              const valueSourceLegend = getStep2ValueSourceLegend(row);
                              const rowStatusClass = row.result === 'PASS'
                                ? 'badge-green'
                                : row.result === 'FAIL'
                                  ? 'badge-red'
                                  : 'badge-yellow';
                              return (
                                <div
                                  key={`${row.control_id}-${row.metric_name}-${row.requirement_id || 'none'}`}
                                  style={{
                                    border: '1px solid var(--border)',
                                    borderRadius: 8,
                                    padding: '0.65rem',
                                    background: 'var(--surface)',
                                    display: 'grid',
                                    gap: '0.55rem',
                                  }}
                                >
                                  <div style={{ display: 'grid', gap: '0.15rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.79rem' }}>
                                        {row.control_title || 'Control'}
                                      </div>
                                      <span className={`badge ${rowStatusClass}`} style={{ width: 'fit-content' }}>
                                        {row.result || 'N/A'}
                                      </span>
                                    </div>
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                      {row.requirement_title || 'Requirement details are not available for this row.'}
                                    </div>
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.55rem' }}>
                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Measure
                                      </span>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 600 }}>{metricMeta.label}</span>
                                      <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {metricMeta.measure}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Value
                                      </span>
                                      <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                                        {formatStep2MetricValue(row.metric_name, row.value)}
                                      </span>
                                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'flex-start' }}>
                                        <span
                                          title={valueSourceLegend}
                                          style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            width: 16,
                                            height: 16,
                                            borderRadius: '50%',
                                            border: '1px solid var(--border)',
                                            fontSize: '0.66rem',
                                            fontWeight: 700,
                                            color: 'var(--text-secondary)',
                                            background: 'var(--surface-2)',
                                            flexShrink: 0,
                                          }}
                                        >
                                          i
                                        </span>
                                      </div>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Interpretation
                                      </span>
                                      <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {row.interpretation_text || getStep2InterpretationText(row)}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Benchmark
                                      </span>
                                      {renderStep2BenchmarkInline(row)}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
                            No data-integration KPI rows available for this application scope.
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 6 && (
              <div style={{ marginTop: '1rem', display: 'grid', gap: '0.75rem' }}>
                <div className="card card-flat">
                  {(() => {
                    const securityRows = detailCache.dashboardStep6?.rows || [];
                    const visibleRows = showAllSecurity ? securityRows : securityRows.slice(0, 5);
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.6rem', marginBottom: '0.45rem' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.82rem' }}>
                            Mandatory Requirements
                          </div>
                          {securityRows.length > 5 && (
                            <button
                              type="button"
                              className="btn btn-outline btn-xs"
                              onClick={() => setShowAllSecurity((prev) => !prev)}
                            >
                              {showAllSecurity ? 'Show Top 5' : `Show All (${securityRows.length})`}
                            </button>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.55rem' }}>
                          Live application telemetry
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.55rem' }}>
                          <span className="badge badge-grey">Total: {securityRows.length}</span>
                          <span className="badge badge-grey">Showing: {visibleRows.length}</span>
                          <span className="badge badge-red">
                            FAIL: {securityRows.filter((row) => row.result === 'FAIL').length}
                          </span>
                          <span className="badge badge-yellow">
                            NO DATA: {securityRows.filter((row) => row.result === 'INSUFFICIENT_DATA').length}
                          </span>
                          <span className="badge badge-green">
                            PASS: {securityRows.filter((row) => row.result === 'PASS').length}
                          </span>
                        </div>

                        {detailCache.dashboardStep6?.summary?.message && (
                          <div className="alert alert-warning" style={{ marginBottom: '0.55rem' }}>
                            {detailCache.dashboardStep6.summary.message}
                          </div>
                        )}

                        {visibleRows.length ? (
                          <div style={{ display: 'grid', gap: '0.55rem' }}>
                            {visibleRows.map((row) => {
                              const metricMeta = getStep2MetricMeta(row.metric_name);
                              const valueSourceLegend = getStep2ValueSourceLegend(row);
                              const rowStatusClass = row.result === 'PASS'
                                ? 'badge-green'
                                : row.result === 'FAIL'
                                  ? 'badge-red'
                                  : 'badge-yellow';
                              return (
                                <div
                                  key={`${row.control_id}-${row.metric_name}-${row.requirement_id || 'none'}`}
                                  style={{
                                    border: '1px solid var(--border)',
                                    borderRadius: 8,
                                    padding: '0.65rem',
                                    background: 'var(--surface)',
                                    display: 'grid',
                                    gap: '0.55rem',
                                  }}
                                >
                                  <div style={{ display: 'grid', gap: '0.15rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.79rem' }}>
                                        {row.control_title || 'Control'}
                                      </div>
                                      <span className={`badge ${rowStatusClass}`} style={{ width: 'fit-content' }}>
                                        {row.result || 'N/A'}
                                      </span>
                                    </div>
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                      {row.requirement_title || 'Requirement details are not available for this row.'}
                                    </div>
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.55rem' }}>
                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Measure
                                      </span>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 600 }}>{metricMeta.label}</span>
                                      <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {metricMeta.measure}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Value
                                      </span>
                                      <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                                        {formatStep2MetricValue(row.metric_name, row.value)}
                                      </span>
                                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'flex-start' }}>
                                        <span
                                          title={valueSourceLegend}
                                          style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            width: 16,
                                            height: 16,
                                            borderRadius: '50%',
                                            border: '1px solid var(--border)',
                                            fontSize: '0.66rem',
                                            fontWeight: 700,
                                            color: 'var(--text-secondary)',
                                            background: 'var(--surface-2)',
                                            flexShrink: 0,
                                          }}
                                        >
                                          i
                                        </span>
                                      </div>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Interpretation
                                      </span>
                                      <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {row.interpretation_text || getStep2InterpretationText(row)}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Benchmark
                                      </span>
                                      {renderStep2BenchmarkInline(row)}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
                            No security KPI rows available for this application scope.
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}
            {!loadingStepDetail && !stepDetailError && activeStep === 7 && (
              <div style={{ marginTop: '1rem', display: 'grid', gap: '0.75rem' }}>
                <div className="card card-flat">
                  {(() => {
                    const infrastructureRows = detailCache.dashboardStep7?.rows || [];
                    const visibleRows = showAllInfrastructure ? infrastructureRows : infrastructureRows.slice(0, 5);
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.6rem', marginBottom: '0.45rem' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.82rem' }}>
                            Mandatory Requirements
                          </div>
                          {infrastructureRows.length > 5 && (
                            <button
                              type="button"
                              className="btn btn-outline btn-xs"
                              onClick={() => setShowAllInfrastructure((prev) => !prev)}
                            >
                              {showAllInfrastructure ? 'Show Top 5' : `Show All (${infrastructureRows.length})`}
                            </button>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.55rem' }}>
                          Live application telemetry
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.55rem' }}>
                          <span className="badge badge-grey">Total: {infrastructureRows.length}</span>
                          <span className="badge badge-grey">Showing: {visibleRows.length}</span>
                          <span className="badge badge-red">
                            FAIL: {infrastructureRows.filter((row) => row.result === 'FAIL').length}
                          </span>
                          <span className="badge badge-yellow">
                            NO DATA: {infrastructureRows.filter((row) => row.result === 'INSUFFICIENT_DATA').length}
                          </span>
                          <span className="badge badge-green">
                            PASS: {infrastructureRows.filter((row) => row.result === 'PASS').length}
                          </span>
                        </div>

                        {detailCache.dashboardStep7?.summary?.message && (
                          <div className="alert alert-warning" style={{ marginBottom: '0.55rem' }}>
                            {detailCache.dashboardStep7.summary.message}
                          </div>
                        )}

                        {visibleRows.length ? (
                          <div style={{ display: 'grid', gap: '0.55rem' }}>
                            {visibleRows.map((row) => {
                              const metricMeta = getStep2MetricMeta(row.metric_name);
                              const valueSourceLegend = getStep2ValueSourceLegend(row);
                              const rowStatusClass = row.result === 'PASS'
                                ? 'badge-green'
                                : row.result === 'FAIL'
                                  ? 'badge-red'
                                  : 'badge-yellow';
                              return (
                                <div
                                  key={`${row.control_id}-${row.metric_name}-${row.requirement_id || 'none'}`}
                                  style={{
                                    border: '1px solid var(--border)',
                                    borderRadius: 8,
                                    padding: '0.65rem',
                                    background: 'var(--surface)',
                                    display: 'grid',
                                    gap: '0.55rem',
                                  }}
                                >
                                  <div style={{ display: 'grid', gap: '0.15rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.79rem' }}>
                                        {row.control_title || 'Control'}
                                      </div>
                                      <span className={`badge ${rowStatusClass}`} style={{ width: 'fit-content' }}>
                                        {row.result || 'N/A'}
                                      </span>
                                    </div>
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                      {row.requirement_title || 'Requirement details are not available for this row.'}
                                    </div>
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.55rem' }}>
                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Measure
                                      </span>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 600 }}>{metricMeta.label}</span>
                                      <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {metricMeta.measure}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Value
                                      </span>
                                      <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                                        {formatStep2MetricValue(row.metric_name, row.value)}
                                      </span>
                                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'flex-start' }}>
                                        <span
                                          title={valueSourceLegend}
                                          style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            width: 16,
                                            height: 16,
                                            borderRadius: '50%',
                                            border: '1px solid var(--border)',
                                            fontSize: '0.66rem',
                                            fontWeight: 700,
                                            color: 'var(--text-secondary)',
                                            background: 'var(--surface-2)',
                                            flexShrink: 0,
                                          }}
                                        >
                                          i
                                        </span>
                                      </div>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Interpretation
                                      </span>
                                      <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {row.interpretation_text || getStep2InterpretationText(row)}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Benchmark
                                      </span>
                                      {renderStep2BenchmarkInline(row)}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
                            No infrastructure KPI rows available for this application scope.
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 8 && (
              <div style={{ marginTop: '1rem', display: 'grid', gap: '0.75rem' }}>
                <div className="card card-flat">
                  {(() => {
                    const solutionDesignRows = detailCache.dashboardStep8?.rows || [];
                    const visibleRows = showAllSolutionDesign ? solutionDesignRows : solutionDesignRows.slice(0, 5);
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.6rem', marginBottom: '0.45rem' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.82rem' }}>
                            Mandatory Requirements
                          </div>
                          {solutionDesignRows.length > 5 && (
                            <button
                              type="button"
                              className="btn btn-outline btn-xs"
                              onClick={() => setShowAllSolutionDesign((prev) => !prev)}
                            >
                              {showAllSolutionDesign ? 'Show Top 5' : `Show All (${solutionDesignRows.length})`}
                            </button>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.55rem' }}>
                          Live application telemetry
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.55rem' }}>
                          <span className="badge badge-grey">Total: {solutionDesignRows.length}</span>
                          <span className="badge badge-grey">Showing: {visibleRows.length}</span>
                          <span className="badge badge-red">
                            FAIL: {solutionDesignRows.filter((row) => row.result === 'FAIL').length}
                          </span>
                          <span className="badge badge-yellow">
                            NO DATA: {solutionDesignRows.filter((row) => row.result === 'INSUFFICIENT_DATA').length}
                          </span>
                          <span className="badge badge-green">
                            PASS: {solutionDesignRows.filter((row) => row.result === 'PASS').length}
                          </span>
                        </div>

                        {detailCache.dashboardStep8?.summary?.message && (
                          <div className="alert alert-warning" style={{ marginBottom: '0.55rem' }}>
                            {detailCache.dashboardStep8.summary.message}
                          </div>
                        )}

                        {visibleRows.length ? (
                          <div style={{ display: 'grid', gap: '0.55rem' }}>
                            {visibleRows.map((row) => {
                              const metricMeta = getStep2MetricMeta(row.metric_name);
                              const valueSourceLegend = getStep2ValueSourceLegend(row);
                              const rowStatusClass = row.result === 'PASS'
                                ? 'badge-green'
                                : row.result === 'FAIL'
                                  ? 'badge-red'
                                  : 'badge-yellow';
                              return (
                                <div
                                  key={`${row.control_id}-${row.metric_name}-${row.requirement_id || 'none'}`}
                                  style={{
                                    border: '1px solid var(--border)',
                                    borderRadius: 8,
                                    padding: '0.65rem',
                                    background: 'var(--surface)',
                                    display: 'grid',
                                    gap: '0.55rem',
                                  }}
                                >
                                  <div style={{ display: 'grid', gap: '0.15rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.79rem' }}>
                                        {row.control_title || 'Control'}
                                      </div>
                                      <span className={`badge ${rowStatusClass}`} style={{ width: 'fit-content' }}>
                                        {row.result || 'N/A'}
                                      </span>
                                    </div>
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                      {row.requirement_title || 'Requirement details are not available for this row.'}
                                    </div>
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.55rem' }}>
                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Measure
                                      </span>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 600 }}>{metricMeta.label}</span>
                                      <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {metricMeta.measure}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Value
                                      </span>
                                      <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                                        {formatStep2MetricValue(row.metric_name, row.value)}
                                      </span>
                                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'flex-start' }}>
                                        <span
                                          title={valueSourceLegend}
                                          style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            width: 16,
                                            height: 16,
                                            borderRadius: '50%',
                                            border: '1px solid var(--border)',
                                            fontSize: '0.66rem',
                                            fontWeight: 700,
                                            color: 'var(--text-secondary)',
                                            background: 'var(--surface-2)',
                                            flexShrink: 0,
                                          }}
                                        >
                                          i
                                        </span>
                                      </div>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Interpretation
                                      </span>
                                      <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {row.interpretation_text || getStep2InterpretationText(row)}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Benchmark
                                      </span>
                                      {renderStep2BenchmarkInline(row)}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
                            No solution-design KPI rows available for this application scope.
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            {!loadingStepDetail && !stepDetailError && activeStep === 9 && (
              <div style={{ marginTop: '1rem', display: 'grid', gap: '0.75rem' }}>
                <div className="card card-flat">
                  {(() => {
                    const systemPerformanceRows = detailCache.dashboardStep9?.rows || [];
                    const visibleRows = showAllSystemPerformance ? systemPerformanceRows : systemPerformanceRows.slice(0, 5);
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.6rem', marginBottom: '0.45rem' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.82rem' }}>
                            Mandatory Requirements
                          </div>
                          {systemPerformanceRows.length > 5 && (
                            <button
                              type="button"
                              className="btn btn-outline btn-xs"
                              onClick={() => setShowAllSystemPerformance((prev) => !prev)}
                            >
                              {showAllSystemPerformance ? 'Show Top 5' : `Show All (${systemPerformanceRows.length})`}
                            </button>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.55rem' }}>
                          Live application telemetry
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.55rem' }}>
                          <span className="badge badge-grey">Total: {systemPerformanceRows.length}</span>
                          <span className="badge badge-grey">Showing: {visibleRows.length}</span>
                          <span className="badge badge-red">
                            FAIL: {systemPerformanceRows.filter((row) => row.result === 'FAIL').length}
                          </span>
                          <span className="badge badge-yellow">
                            NO DATA: {systemPerformanceRows.filter((row) => row.result === 'INSUFFICIENT_DATA').length}
                          </span>
                          <span className="badge badge-green">
                            PASS: {systemPerformanceRows.filter((row) => row.result === 'PASS').length}
                          </span>
                        </div>

                        {detailCache.dashboardStep9?.summary?.message && (
                          <div className="alert alert-warning" style={{ marginBottom: '0.55rem' }}>
                            {detailCache.dashboardStep9.summary.message}
                          </div>
                        )}

                        {visibleRows.length ? (
                          <div style={{ display: 'grid', gap: '0.55rem' }}>
                            {visibleRows.map((row) => {
                              const metricMeta = getStep2MetricMeta(row.metric_name);
                              const valueSourceLegend = getStep2ValueSourceLegend(row);
                              const rowStatusClass = row.result === 'PASS'
                                ? 'badge-green'
                                : row.result === 'FAIL'
                                  ? 'badge-red'
                                  : 'badge-yellow';
                              return (
                                <div
                                  key={`${row.control_id}-${row.metric_name}-${row.requirement_id || 'none'}`}
                                  style={{
                                    border: '1px solid var(--border)',
                                    borderRadius: 8,
                                    padding: '0.65rem',
                                    background: 'var(--surface)',
                                    display: 'grid',
                                    gap: '0.55rem',
                                  }}
                                >
                                  <div style={{ display: 'grid', gap: '0.15rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.79rem' }}>
                                        {row.control_title || 'Control'}
                                      </div>
                                      <span className={`badge ${rowStatusClass}`} style={{ width: 'fit-content' }}>
                                        {row.result || 'N/A'}
                                      </span>
                                    </div>
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                      {row.requirement_title || 'Requirement details are not available for this row.'}
                                    </div>
                                  </div>

                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.55rem' }}>
                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Measure
                                      </span>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 600 }}>{metricMeta.label}</span>
                                      <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {metricMeta.measure}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Value
                                      </span>
                                      <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                                        {formatStep2MetricValue(row.metric_name, row.value)}
                                      </span>
                                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'flex-start' }}>
                                        <span
                                          title={valueSourceLegend}
                                          style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            width: 16,
                                            height: 16,
                                            borderRadius: '50%',
                                            border: '1px solid var(--border)',
                                            fontSize: '0.66rem',
                                            fontWeight: 700,
                                            color: 'var(--text-secondary)',
                                            background: 'var(--surface-2)',
                                            flexShrink: 0,
                                          }}
                                        >
                                          i
                                        </span>
                                      </div>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Interpretation
                                      </span>
                                      <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                                        {row.interpretation_text || getStep2InterpretationText(row)}
                                      </span>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.2rem' }}>
                                      <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Benchmark
                                      </span>
                                      {renderStep2BenchmarkInline(row)}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
                            No system-performance KPI rows available for this application scope.
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

GovernanceTab.propTypes = {
  requestedStep: PropTypes.shape({
    stepNum: PropTypes.number.isRequired,
    token: PropTypes.number.isRequired,
  }),
  onDashboardUiChange: PropTypes.func,
};

GovernanceTab.defaultProps = {
  requestedStep: null,
  onDashboardUiChange: null,
};













