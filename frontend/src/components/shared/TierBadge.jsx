import PropTypes from 'prop-types';

const TIER_CONFIG = {
  High: {
    cls: 'tier-badge-high',
    label: 'High Risk',
    tooltip: 'Highest governance obligations. Domain floor rule or autonomy validation may apply.',
  },
  Common: {
    cls: 'tier-badge-common',
    label: 'Common',
    tooltip: 'Standard governance tier. Additional controls required beyond Foundation.',
  },
  Foundation: {
    cls: 'tier-badge-foundation',
    label: 'Foundation',
    tooltip: 'Baseline governance tier. 10 foundation controls apply to all applications.',
  },
};

export function TierBadge({ tier }) {
  const cfg = TIER_CONFIG[tier] || {
    cls: 'badge-grey',
    label: tier || 'Unknown',
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
