import PropTypes from 'prop-types';
import React from 'react';
import { Navigate } from 'react-router-dom';
import Loader from './Loader/Loader';
import { useUiConfig } from '../contexts/UiConfigContext';

/**
 * Redirects to role dashboard when a GeoAI UI flag from backend/.env is off.
 */
export default function UiScopedView({ flag, children }) {
  const { uiConfig, loading } = useUiConfig();
  const role = typeof localStorage !== 'undefined' ? localStorage.getItem('role') : null;
  const home =
    role === 'admin' ? '/app/admin/dashboard/' : '/app/userdashboard/';

  if (loading) {
    return <Loader />;
  }
  if (!uiConfig[flag]) {
    return <Navigate to={home} replace />;
  }
  return children;
}

UiScopedView.propTypes = {
  flag: PropTypes.string.isRequired,
  children: PropTypes.node.isRequired,
};
