import PropTypes from 'prop-types';
import GovernanceTab from './GovernanceTab.jsx';

export default function DashboardsTab({ requestedStep, onDashboardUiChange }) {
  return <GovernanceTab requestedStep={requestedStep} onDashboardUiChange={onDashboardUiChange} />;
}

DashboardsTab.propTypes = {
  requestedStep: PropTypes.shape({
    stepNum: PropTypes.number,
    token: PropTypes.number,
  }),
  onDashboardUiChange: PropTypes.func,
};

DashboardsTab.defaultProps = {
  requestedStep: null,
  onDashboardUiChange: null,
};
