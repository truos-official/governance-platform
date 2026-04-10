import PropTypes from 'prop-types';

const RISK_TIER_MAP = {
  High: 'High',
  Common: 'Medium',
  Foundation: 'Low',
  Medium: 'Medium',
  Low: 'Low',
};

export function normalizeRiskTier(tier) {
  if (!tier) {
    return null;
  }
  return RISK_TIER_MAP[tier] || tier;
}

const TIER_CONFIG = {
  High: {
    cls: 'tier-badge-high',
    label: 'High Risk',
    tooltip: 'Highest governance obligations. Domain floor rule or autonomy validation may apply.',
  },
  Medium: {
    cls: 'tier-badge-common',
    label: 'Medium Risk',
    tooltip: 'Standard governance tier. Additional controls required beyond baseline.',
  },
  Low: {
    cls: 'tier-badge-foundation',
    label: 'Low Risk',
    tooltip: 'Baseline governance tier. Core controls apply to all applications.',
  },
};

export function TierBadge({ tier }) {
  const normalized = normalizeRiskTier(tier);
  const cfg = TIER_CONFIG[normalized] || {
    cls: 'badge-grey',
    label: normalized || tier || 'Unknown',
    tooltip: 'Tier not yet assigned.',
  };

  return (
    <span className={`badge ${cfg.cls}`} title={cfg.tooltip}>
      {cfg.label}
    </span>
  );
}

export function StatusBadge({ result }) {
  const map = {
    PASS: { cls: 'status-pass', label: 'Pass' },
    FAIL: { cls: 'status-fail', label: 'Fail' },
    INSUFFICIENT_DATA: { cls: 'status-insufficient', label: 'No Data' },
  };
  const cfg = map[result] || { cls: 'badge-grey', label: result };
  return <span className={`badge ${cfg.cls}`}>{cfg.label}</span>;
}

export function Tooltip({ text, children }) {
  return (
    <span className="tooltip-wrapper">
      {children}
      <span className="tooltip-icon">?</span>
      <span className="tooltip-box">{text}</span>
    </span>
  );
}

TierBadge.propTypes = {
  tier: PropTypes.string,
};

StatusBadge.propTypes = {
  result: PropTypes.string,
};

Tooltip.propTypes = {
  text: PropTypes.string.isRequired,
  children: PropTypes.node,
};
