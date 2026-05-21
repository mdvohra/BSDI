import PropTypes from 'prop-types';
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { getApiBaseUrl } from '../config/apiBase';

/** When /api/ui-config fails, hide optional modules (gov-safe). */
export const FALLBACK_UI_CONFIG = {
  show_super_resolution: false,
  show_lulc: false,
  show_analysis: false,
  show_lulc_fields: false,
  show_detection_threshold: true,
  show_config_page: false,
  default_inference_threshold: 0.3,
};

const UiConfigContext = createContext({
  uiConfig: FALLBACK_UI_CONFIG,
  loading: true,
  error: null,
  reload: () => {},
});

export function UiConfigProvider({ children }) {
  const [uiConfig, setUiConfig] = useState(FALLBACK_UI_CONFIG);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = () => {
    setLoading(true);
    setError(null);
    const url = `${getApiBaseUrl()}/api/ui-config`;
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`ui-config ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setUiConfig({
          show_super_resolution: Boolean(data.show_super_resolution),
          show_lulc: Boolean(data.show_lulc),
          show_analysis: Boolean(data.show_analysis),
          show_lulc_fields: Boolean(data.show_lulc_fields),
          show_detection_threshold: Boolean(data.show_detection_threshold),
          show_config_page: Boolean(data.show_config_page),
          default_inference_threshold:
            typeof data.default_inference_threshold === 'number' &&
            Number.isFinite(data.default_inference_threshold)
              ? data.default_inference_threshold
              : FALLBACK_UI_CONFIG.default_inference_threshold,
        });
      })
      .catch((e) => {
        setError(e);
        setUiConfig(FALLBACK_UI_CONFIG);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const value = useMemo(
    () => ({
      uiConfig,
      loading,
      error,
      reload: load,
    }),
    [uiConfig, loading, error]
  );

  return <UiConfigContext.Provider value={value}>{children}</UiConfigContext.Provider>;
}

UiConfigProvider.propTypes = {
  children: PropTypes.node,
};

export function useUiConfig() {
  return useContext(UiConfigContext);
}

export { UiConfigContext };
