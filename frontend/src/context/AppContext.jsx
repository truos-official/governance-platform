import { createContext, useContext, useState } from 'react';
import PropTypes from 'prop-types';

const AppContext = createContext(null);

// Role hierarchy
export const ROLES = {
  SECRETARIAT_ADMIN: 'secretariat_admin',
  DIVISION_ADMIN: 'division_admin',
  APPLICATION_OWNER: 'application_owner',
  EXPERT_CONTRIBUTOR: 'expert_contributor',
  REVIEWER: 'reviewer',
};

// Hardcoded for Phase 5 — DB-backed in Phase 6
const ROLE_MAP = {
  'tristan.gitman@un.org': ROLES.SECRETARIAT_ADMIN,
};

export function AppProvider({ children }) {
  const [selectedAppId, setSelectedAppId] = useState(null);
  const [selectedApp, setSelectedApp] = useState(null);
  const [currentUser] = useState({
    email: 'tristan.gitman@un.org',
    name: 'Tristan Gitman',
    role: ROLES.SECRETARIAT_ADMIN,
  });

  const role = ROLE_MAP[currentUser.email] || ROLES.APPLICATION_OWNER;

  const canAdmin = role === ROLES.SECRETARIAT_ADMIN || role === ROLES.DIVISION_ADMIN;
  const isSecretariatAdmin = role === ROLES.SECRETARIAT_ADMIN;

  const selectApp = (app) => {
    setSelectedApp(app);
    setSelectedAppId(app?.id || null);
  };

  return (
    <AppContext.Provider value={{
      selectedApp, selectedAppId, selectApp,
      currentUser: { ...currentUser, role },
      canAdmin, isSecretariatAdmin,
    }}>
      {children}
    </AppContext.Provider>
  );
}

export const useApp = () => useContext(AppContext);

AppProvider.propTypes = {
  children: PropTypes.node.isRequired,
};
