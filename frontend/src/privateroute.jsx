// import React from 'react';
// import { Route, Navigate } from 'react-router-dom';

// const PrivateRoute = ({ component: Component, ...rest }) => (
//   <Route
//     {...rest}
//     element={localStorage.getItem('token') ? <Component /> : <Navigate to="/login" />}
//   />
// );

// export default PrivateRoute;


import React from 'react';
import { Navigate } from 'react-router-dom';

const PrivateRoute = ({ children }) => {
  const isAuthenticated = localStorage.getItem('token');
  return isAuthenticated ? children : <Navigate to="/login" />;
};

export default PrivateRoute;
