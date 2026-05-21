import React, { useState, useEffect } from 'react';
import { ListGroup } from 'react-bootstrap';
import { Link, useLocation } from 'react-router-dom';

import { buildMenuItems } from '../../../menu-items';
import { useUiConfig } from '../../../contexts/UiConfigContext';
import { BASE_TITLE } from '../../../config/constant';

const normPath = (p) => (p || '').replace(/\/+$/, '') || '/';

const Breadcrumb = () => {
  const location = useLocation();
  const { uiConfig } = useUiConfig();
  const role = localStorage.getItem('role');
  const [main, setMain] = useState([]);
  const [item, setItem] = useState([]);

  useEffect(() => {
    const navigation = buildMenuItems(uiConfig);
    setMain(null);
    setItem(null);
    const path = normPath(location.pathname);

    const getCollapse = (node) => {
      if (!node || !node.children) return;
      node.children.forEach((child) => {
        if (child.type === 'collapse') {
          getCollapse(child);
        } else if (child.type === 'item' && child.url) {
          if (path === normPath(child.url)) {
            setMain(node);
            setItem(child);
          }
        }
      });
    };

    navigation.items.forEach((group) => {
      if (group.type === 'group' && group.children) {
        group.children.forEach((child) => {
          if (child.type === 'collapse') {
            getCollapse(child);
          } else if (child.type === 'item' && child.url && path === normPath(child.url)) {
            setMain(group);
            setItem(child);
          }
        });
      }
    });
  }, [location.pathname, uiConfig]);

  let mainContent;
  let itemContent;
  let breadcrumbContent = '';
  let title = '';

  if (main && (main.type === 'collapse' || main.type === 'group')) {
    mainContent = (
      <ListGroup.Item as="li" bsPrefix=" " className="breadcrumb-item">
        <Link to="#">{main.title}</Link>
      </ListGroup.Item>
    );
  }

  if (item && item.type === 'item') {
    title = item.title;
    itemContent = (
      <ListGroup.Item as="li" bsPrefix=" " className="breadcrumb-item">
        <Link to="#">{title}</Link>
      </ListGroup.Item>
    );

    if (item.breadcrumbs !== false) {
      breadcrumbContent = (
        <div className="page-header">
          <div className="page-block">
            <div className="row align-items-center">
              <div className="col-md-12">
                <div className="page-header-title" />
                <ListGroup as="ul" bsPrefix=" " className="breadcrumb">
                  <ListGroup.Item as="li" bsPrefix=" " className="breadcrumb-item">
                    <Link
                      to={role === 'admin' ? '/app/admin/dashboard/' : '/app/userdashboard/'}
                    >
                      <i className="feather icon-home" />
                    </Link>
                  </ListGroup.Item>
                  {mainContent}
                  {itemContent}
                </ListGroup>
              </div>
            </div>
          </div>
        </div>
      );
    }

    document.title = title + BASE_TITLE;
  }

  return <React.Fragment>{breadcrumbContent}</React.Fragment>;
};

export default Breadcrumb;
