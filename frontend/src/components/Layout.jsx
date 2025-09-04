import React from 'react';
import { useTheme } from '../contexts/ThemeContext';
import Header from './Header';
import HorizontalNavigation from './HorizontalNavigation';

const Layout = ({ children, userInfo }) => {
  const theme = useTheme();

  const layoutStyle = {
    minHeight: '100vh',
    background: theme.colors.background.gradient,
    color: theme.colors.text.primary,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", sans-serif',
    transition: theme.transitions.normal
  };

  const mainStyle = {
    marginTop: '140px', // Header (80px) + HorizontalNavigation (60px)
    padding: '2rem',
    minHeight: 'calc(100vh - 140px)',
    position: 'relative'
  };

  const mobileMainStyle = {
    ...mainStyle,
    padding: '1rem',
    marginTop: '140px' // Same for mobile since we're using horizontal nav
  };

  const isMobile = window.innerWidth < 768;

  return (
    <div style={layoutStyle}>
      <Header userInfo={userInfo} />
      <HorizontalNavigation />

      <main style={isMobile ? mobileMainStyle : mainStyle}>
        {children}
      </main>
    </div>
  );
};

export default Layout;