import { FALLBACK_UI_CONFIG } from './contexts/UiConfigContext';

/**
 * Sidebar + breadcrumb menu from backend-driven GeoAI UI flags.
 * When only Object Detection is enabled, the sidebar uses a flat item (no Solutions / GIS nesting).
 * @param {typeof FALLBACK_UI_CONFIG} uiConfig
 */
export function buildMenuItems(uiConfig = FALLBACK_UI_CONFIG) {
  const gisChildren = [
    {
      id: 'Object Detection',
      title: 'Object Detection',
      type: 'item',
      url: '/app/sataliteimage',
      roles: ['admin', 'user'],
    },
  ];

  if (uiConfig.show_super_resolution) {
    gisChildren.push({
      id: 'Super Resolution',
      title: 'Super Resolution',
      type: 'item',
      url: '/app/superResolution',
      roles: ['admin', 'user'],
    });
  }
  if (uiConfig.show_lulc) {
    gisChildren.push({
      id: 'LULC',
      title: 'LULC',
      type: 'item',
      url: '/app/lulc',
      roles: ['admin', 'user'],
    });
  }
  if (uiConfig.show_analysis) {
    gisChildren.push({
      id: 'Analysis',
      title: 'Analysis',
      type: 'item',
      url: '/app/analysis',
      roles: ['admin', 'user'],
    });
  }

  const solutionsNested = {
    id: 'solutions',
    title: 'Solutions',
    type: 'collapse',
    icon: 'feather icon-menu',
    roles: ['admin', 'user'],
    children: [
      {
        id: 'gis analytics',
        title: 'GIS Solutions',
        type: 'collapse',
        roles: ['admin', 'user'],
        children: gisChildren,
      },
    ],
  };

  const configItem = {
    id: 'config',
    title: 'Config',
    type: 'item',
    icon: 'feather icon-settings',
    url: '/app/config/',
    roles: ['admin', 'user'],
  };

  /** Single GIS entry (typical gov demo): flat link, no Solutions → GIS Solutions nesting */
  const onlyObjectDetection =
    gisChildren.length === 1 && gisChildren[0].id === 'Object Detection';

  let productsChildren;
  let productsGroupTitle;

  if (onlyObjectDetection) {
    productsChildren = [
      {
        id: 'object_detection_nav',
        title: 'Object Detection',
        type: 'item',
        icon: 'feather icon-map',
        url: '/app/sataliteimage',
        roles: ['admin', 'user'],
      },
    ];
    if (uiConfig.show_config_page) {
      productsChildren.push(configItem);
    }
    productsGroupTitle =
      productsChildren.length === 1 && !uiConfig.show_config_page ? 'Mapping' : 'Services';
  } else {
    productsChildren = [solutionsNested];
    if (uiConfig.show_config_page) {
      productsChildren.push(configItem);
    }
    productsGroupTitle = 'Products & Services';
  }

  return {
    items: [
      {
        id: 'dashboard',
        title: 'Home',
        type: 'group',
        icon: 'icon-navigation',
        roles: ['admin', 'user'],
        children: [
          {
            id: 'admindashboard',
            title: 'Dashboard',
            type: 'item',
            icon: 'feather icon-home',
            url: '/app/admin/dashboard/',
            roles: ['admin'],
          },
          {
            id: 'userdashboard',
            title: 'Dashboard',
            type: 'item',
            icon: 'feather icon-home',
            url: '/app/userdashboard/',
            roles: ['user'],
          },
        ],
      },
      {
        id: 'Products & Services',
        title: productsGroupTitle,
        type: 'group',
        icon: 'icon-navigation',
        roles: ['admin', 'user'],
        children: productsChildren,
      },
      {
        id: 'Admin Operations',
        title: 'Admin Operations',
        type: 'group',
        icon: 'icon-group',
        roles: ['admin'],
        children: [
          {
            id: 'Add Tenant',
            title: 'Add Tenant',
            type: 'item',
            icon: 'feather icon-user-plus',
            url: '/app/addtenant/',
            roles: ['admin'],
          },
          {
            id: 'Add User Role',
            title: 'Add User Role',
            type: 'item',
            icon: 'feather icon-users',
            url: '/app/adduserrole/',
            roles: ['admin'],
          },
          {
            id: 'Add Use Cases',
            title: 'Add Use Cases',
            type: 'item',
            icon: 'feather icon-plus',
            url: '/app/addusecase/',
            roles: ['admin'],
          },
          {
            id: 'Add User',
            title: 'Add User',
            type: 'item',
            icon: 'feather icon-user-plus',
            url: '/app/adduser/',
            roles: ['admin'],
          },
        ],
      },
    ],
  };
}

/** Static fallback for imports that do not have UiConfig yet (prefer buildMenuItems + useUiConfig). */
const menuItems = buildMenuItems(FALLBACK_UI_CONFIG);
export default menuItems;
