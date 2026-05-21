import React from 'react';
import { createRoot } from 'react-dom/client';
import 'leaflet/dist/leaflet.css';

import { ConfigProvider } from './contexts/ConfigContext';
import { UiConfigProvider } from './contexts/UiConfigContext';

import './index.scss';
import App from './App';
import reportWebVitals from './reportWebVitals';

const container = document.getElementById('root');
const root = createRoot(container);
root.render(
  <ConfigProvider>
    <UiConfigProvider>
      <App />
    </UiConfigProvider>
  </ConfigProvider>
);

reportWebVitals();
