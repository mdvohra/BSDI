import React, { Suspense, Fragment, lazy,useEffect,useState,useContext } from 'react';
import { Routes, Route, Navigate,useNavigate } from 'react-router-dom';
import Loader from './components/Loader/Loader';
import AdminLayout from './layouts/AdminLayout';
import PrivateRoute from './privateroute';
import { BASE_URL } from './config/constant';
import axios from 'axios';
import { ConfigContext } from './contexts/ConfigContext';
// import SatelliteImage from 'views/sataliteImage';
import SatelliteImage from "./views/sataliteImage";
// export const renderRoutes = (routes = []) => (
//   <Suspense fallback={<Loader />}>
//     <Routes>
//       {routes.map((route, i) => {
//         const Guard = route.guard || Fragment;
//         const Layout = route.layout || Fragment;
//         const Element = route.element;

//         return (
//           <Route
//             key={i}
//             path={route.path}
//             element={
//               <Guard>
//                 <Layout>{route.routes ? renderRoutes(route.routes) : <Element props={true} />}</Layout>
//               </Guard>
//             }
//           />
//         );
//       })}
//     </Routes>
//   </Suspense>
// );


const getUserRole = () => {
  return localStorage.getItem('role');
};


export const renderRoutes = (routes = []) => {
  const configContext = useContext(ConfigContext);
  const [dun,setDun] = useState([]);
  const { dispatch } = configContext;
  const getUserChats = () => {
    axios.get('Chata/GetChats/1').then((response) => {
      dispatch({ type: 'USER_CHATS', userChats: response.data.$values });
    }
    );
  };
  // getUserChats();
  useEffect(() => {
    getUserChats();
  }
  , [dun]);
  const [userRole, setUserRole] = useState(getUserRole());
  const accessibleRoutes = routes.filter(route => {
    return !route.roles || route.roles.includes(userRole); // If no roles defined, allow everyone
  });
  const [usableRoutes, setUsableRoutes] = useState(accessibleRoutes);
  // useEffect(() => {
  //   const userRole = getUserRole();
  //   if (!userRole) {
  //     // If there is no user role, redirect to the login page
  //     return <Navigate to="/login" />;
  //   }
  //   setUserRole(userRole);
  //   const accessibleRoutes = routes.filter(route => {
  //     return !route.roles || route.roles.includes(userRole); // If no roles defined, allow everyone
  //   });
  //   setUsableRoutes(accessibleRoutes);
  // }
  // , []);

  return(
  <Suspense fallback={<Loader />}>
    <Routes>
      {usableRoutes.map((route, i) => {
        const Guard = route.guard || Fragment;
        const Layout = route.layout || Fragment;
        const Element = route.element;

        return (
          <Route
            key={i}
            path={route.path}
            element={
              <Guard>
                <Layout>
                  {/* Check if the route requires authentication */}
                  {route.requiresAuth ? (
                    <PrivateRoute>
                      {route.routes ? renderRoutes(route.routes) : <Element />}
                    </PrivateRoute>
                  ) : (
                    route.routes ? renderRoutes(route.routes) : <Element />
                  )}
                </Layout>
              </Guard>
            }
          />
        );
      })}
    </Routes>
  </Suspense>
  );
};

const routes = [
  {
    exact: 'true',
    path: '/login',
    element: lazy(() => import('./views/auth/authentication/userlogin')),
    requiresAuth: false,
  },
  {
    exact: 'true',
    path: '/signup',
    element: lazy(() => import('./views/auth/authentication/signup')),
    requiresAuth: false,
  },
  {
    exact: 'true',
    path: '/passwordreset/mail',
    element: lazy(() => import('./views/auth/authentication/getmailforpass')),
    requiresAuth: false,
  },
  {
    exact: 'true',
    path: '/resetpassword/:token',
    element: lazy(() => import('./views/auth/authentication/resetpassword')),
    requiresAuth: false,
  },
  {
    exact: 'true',
    path: '/Home',
    element: lazy(() => import('./views/landingpage')),
    requiresAuth: false,
  },
  {
    path: '*',
    layout: AdminLayout,
    routes: [
      {
        exact: 'true',
        path: '/app/admin/dashboard',
        element: lazy(() => import('./views/dashboard')),
        requiresAuth: true,
        roles: ['admin']
      },
      {
        exact: 'true',
        path: '/app/userdashboard',
        element: lazy(() => import('./views/userdashboard')),
        requiresAuth: true,
        roles: ['user']
      },
      {
        exact: 'true',
        path: '/app/pdfquery',
        element: lazy(() => import('./views/pdfquery')),
        requiresAuth: true,
        roles: ['admin', 'user']
      },
      {
        exact: 'true',
        path: '/app/sataliteimage',
        element: lazy(() => import('./views/sataliteImage')),
        requiresAuth: true,
        roles: ['admin', 'user']
      },
      {
        exact: 'true',
        path: '/app/superResolution',
        element: lazy(() => import('./views/superResolution')),
        requiresAuth: true,
        roles: ['admin', 'user']
      },
      {
        exact: 'true',
        path: '/app/lulc',
        element: lazy(() => import('./views/lulc')),
        requiresAuth: true,
        roles: ['admin', 'user']
      },
      {
        exact: 'true',
        path: '/app/analysis',
        element: lazy(() => import('./views/analysis')),
        requiresAuth: true,
        roles: ['admin', 'user']
      },
      {
        exact: 'true',
        path: '/app/config/',
        element: lazy(() => import('./views/config')),
        requiresAuth: true,
        roles: ['admin', 'user']
      },
      {
        exact: 'true',
        path: '/app/addtenant',
        element: lazy(() => import('./views/Tenant')),
        requiresAuth: true,
        roles: ['admin']
      },
      {
        exact: 'true',
        path: '/app/adduserrole/',
        element: lazy(() => import('./views/userrole')),
        requiresAuth: true,
        roles: ['admin']
      },
      {
        exact: 'true',
        path: '/app/addusecase/',
        element: lazy(() => import('./views/usecases')),
        requiresAuth: true,
        roles: ['admin']
      },
      {
        exact: 'true',
        path: '/app/adduser/',
        element: lazy(() => import('./views/adduser')),
        requiresAuth: true,
        roles: ['admin']
      },
      // {
      //   exact: 'true',
      //   path: '/basic/button',
      //   element: lazy(() => import('./views/ui-elements/basic/BasicButton'))
      // },
      // {
      //   exact: 'true',
      //   path: '/basic/badges',
      //   element: lazy(() => import('./views/ui-elements/basic/BasicBadges'))
      // },
      // {
      //   exact: 'true',
      //   path: '/basic/breadcrumb-paging',
      //   element: lazy(() => import('./views/ui-elements/basic/BasicBreadcrumb'))
      // },
      // {
      //   exact: 'true',
      //   path: '/basic/collapse',
      //   element: lazy(() => import('./views/ui-elements/basic/BasicCollapse'))
      // },
      // {
      //   exact: 'true',
      //   path: '/basic/tabs-pills',
      //   element: lazy(() => import('./views/ui-elements/basic/BasicTabsPills'))
      // },
      // {
      //   exact: 'true',
      //   path: '/basic/typography',
      //   element: lazy(() => import('./views/ui-elements/basic/BasicTypography'))
      // },
      // {
      //   exact: 'true',
      //   path: '/forms/form-basic',
      //   element: lazy(() => import('./views/forms/FormsElements'))
      // },
      // {
      //   exact: 'true',
      //   path: '/tables/bootstrap',
      //   element: lazy(() => import('./views/tables/BootstrapTable'))
      // },
      // {
      //   exact: 'true',
      //   path: '/charts/nvd3',
      //   element: lazy(() => import('./views/charts/nvd3-chart'))
      // },
      // {
      //   exact: 'true',
      //   path: '/sample-page',
      //   element: lazy(() => import('./views/extra/SamplePage'))
      // },
      {
        path: '*',
        exact: 'true',
        element: () => <Navigate to={BASE_URL} />,
        requiresAuth: true,
      }
    ]
  }
];

export default routes;
