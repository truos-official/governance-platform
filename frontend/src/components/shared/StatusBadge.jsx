import PropTypes from 'prop-types';

export function StatusBadge({ result }) {
  const map = {
    PASS: { cls: 'status-pass', label: 'Pass' },
    FAIL: { cls: 'status-fail', label: 'Fail' },
    INSUFFICIENT_DATA: { cls: 'status-insufficient', label: 'No Data' },
  };
  const cfg = map[result] || { cls: 'badge-grey', label: result };
  return <span className={`badge ${cfg.cls}`}>{cfg.label}</span>;
}

StatusBadge.propTypes = {
  result: PropTypes.string,
};
