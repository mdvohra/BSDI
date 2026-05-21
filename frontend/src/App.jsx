//import React from 'react';
//import { BrowserRouter } from 'react-router-dom';
//import axios from 'axios';
//import routes, { renderRoutes } from './routes';
//import 'leaflet/dist/leaflet.css';

//const App = () => {
 // axios.defaults.baseURL = import.meta.env.VITE_APP_API_BASE_URL_DEV;
  // axios.defaults.baseURL = import.meta.env.VITE_APP_API_BASE_URL_PROD;
//  return <BrowserRouter basename='braeinaipocweb' >{renderRoutes(routes)}</BrowserRouter>;
//};

//export default App;


import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import axios from 'axios';
import routes, { renderRoutes } from './routes';
import 'leaflet/dist/leaflet.css';

const App = () => {
  axios.defaults.baseURL = import.meta.env.VITE_APP_API_BASE_URL_DEV;

  return (
    <BrowserRouter>
      {renderRoutes(routes)}
    </BrowserRouter>
  );
};

export default App;
