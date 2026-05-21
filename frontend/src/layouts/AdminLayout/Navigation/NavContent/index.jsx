import PropTypes from 'prop-types';
import React from 'react';
import { ListGroup } from 'react-bootstrap';
import PerfectScrollbar from 'react-perfect-scrollbar';
import {useLocation} from 'react-router-dom';
import NavGroup from './NavGroup';
import NavCard from './NavCard';
import Historycard from './Historycard';

const NavContent = ({ navigation }) => {
  const location = useLocation();
  const navigationItems = navigation.filter((item) => {
    if (item.roles) {
      return item.roles.includes(localStorage.getItem('role'));
    }
    return true;
  }
  );
  const navItems = navigationItems.map((item) => {
    switch (item.type) {
      case 'group':
        return <NavGroup key={'nav-group-' + item.id} group={item} />;
      default:
        return false;
    }
  });

  let mainContent = '';

  mainContent = (
    <div className="navbar-content datta-scroll">
      <PerfectScrollbar>
        <ListGroup variant="flush" as="ul" bsPrefix=" " className="nav pcoded-inner-navbar" id="nav-ps-next">
          {navItems}
        </ListGroup>
        {/* <NavCard /> */}
        {/* render history card only if the current page is /app/pdfquery */}
        {
          location.pathname === '/app/pdfquery' ? <Historycard /> : null
        }
      </PerfectScrollbar>
    </div>
  );

  return <React.Fragment>{mainContent}</React.Fragment>;
};

NavContent.propTypes = {
  navigation: PropTypes.array
};

export default NavContent;
