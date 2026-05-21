import React, { useContext } from 'react';

import { ConfigContext } from '../../../contexts/ConfigContext';
import { useUiConfig } from '../../../contexts/UiConfigContext';
import useWindowSize from '../../../hooks/useWindowSize';
import { buildMenuItems } from '../../../menu-items';

import NavLogo from './NavLogo';
import NavContent from './NavContent';

const Navigation = () => {
  const configContext = useContext(ConfigContext);
  const { uiConfig } = useUiConfig();
  const navigation = buildMenuItems(uiConfig);
  const { collapseMenu } = configContext.state;
  const windowSize = useWindowSize();

  let navClass = ['pcoded-navbar'];

  navClass = [...navClass];

  if (windowSize.width < 992 && collapseMenu) {
    navClass = [...navClass, 'mob-open'];
  } else if (collapseMenu) {
    navClass = [...navClass, 'navbar-collapsed'];
  }

  let navBarClass = ['navbar-wrapper'];

  let navContent = (
    <div className={navBarClass.join(' ')}>
      <NavLogo />
      <NavContent navigation={navigation.items} />
    </div>
  );
  if (windowSize.width < 992) {
    navContent = (
      <div className="navbar-wrapper">
        <NavLogo />
        <NavContent navigation={navigation.items} />
      </div>
    );
  }
  return (
    <React.Fragment>
      <nav className={navClass.join(' ')}>{navContent}</nav>
    </React.Fragment>
  );
};

export default Navigation;
