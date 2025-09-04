import React from 'react';
import { Link } from 'react-router-dom';
import { useTheme } from '../contexts/ThemeContext';

const Header = ({ 
  userInfo = {
    organisation: 'SOAKOJA',
    employeName: 'Admin',
    poste: 'Administrateur',
    niveauMenu: 'Complet'
  }
}) => {
  const theme = useTheme();

  const headerStyle = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 1000,
    background: theme.colors.background.card,
    backdropFilter: theme.glassmorphism.backdrop,
    WebkitBackdropFilter: theme.glassmorphism.backdrop,
    borderBottom: `1px solid ${theme.colors.border.primary}`,
    boxShadow: theme.glassmorphism.shadow,
    padding: '0.75rem 0',
    transition: theme.transitions.normal
  };

  const containerStyle = {
    maxWidth: '1200px',
    margin: '0 auto',
    padding: '0 1rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
    flexWrap: 'wrap'
  };

  const logoStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    textDecoration: 'none',
    color: theme.colors.text.primary,
    fontWeight: '600',
    fontSize: '1.25rem'
  };

  const userInfoStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    color: theme.colors.text.secondary,
    fontSize: '0.875rem',
    flexWrap: 'wrap'
  };

  const userDetailStyle = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '0.25rem'
  };

  const actionButtonsStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem'
  };

  const buttonStyle = {
    background: theme.colors.background.hover,
    backdropFilter: 'blur(12px)',
    WebkitBackdropFilter: 'blur(12px)',
    border: `1px solid ${theme.colors.border.primary}`,
    borderRadius: '8px',
    padding: '0.5rem 1rem',
    color: theme.colors.text.primary,
    textDecoration: 'none',
    fontSize: '0.875rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: theme.transitions.fast,
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    position: 'relative',
    overflow: 'hidden'
  };

  const themeToggleStyle = {
    ...buttonStyle,
    minWidth: '100px',
    justifyContent: 'center'
  };

  return (
    <header style={headerStyle}>
      <div style={containerStyle}>
        {/* Logo et nom organisation */}
        <Link to="/" style={logoStyle}>
          <span style={{ fontSize: '1.5rem' }}>💧</span>
          <span>{userInfo.organisation}</span>
        </Link>

        {/* Informations utilisateur - caché sur mobile */}
        <div style={{
          ...userInfoStyle,
          display: window.innerWidth < 768 ? 'none' : 'flex'
        }}>
          <div style={userDetailStyle}>
            <span style={{ fontWeight: '500', color: theme.colors.text.primary }}>
              {userInfo.employeName}
            </span>
            <span style={{ fontSize: '0.75rem' }}>{userInfo.poste}</span>
          </div>
          <div style={{
            width: '1px',
            height: '2rem',
            background: theme.colors.border.primary
          }} />
          <div style={userDetailStyle}>
            <span style={{ fontSize: '0.75rem', opacity: 0.8 }}>Niveau</span>
            <span style={{ fontWeight: '500', color: theme.colors.primary }}>
              {userInfo.niveauMenu}
            </span>
          </div>
        </div>

        {/* Boutons d'action */}
        <div style={actionButtonsStyle}>
          <Link 
            to="/" 
            style={buttonStyle}
            onMouseEnter={(e) => {
              e.target.style.background = theme.colors.background.active;
              e.target.style.borderColor = theme.colors.border.accent;
              e.target.style.transform = 'translateY(-1px)';
            }}
            onMouseLeave={(e) => {
              e.target.style.background = theme.colors.background.hover;
              e.target.style.borderColor = theme.colors.border.primary;
              e.target.style.transform = 'translateY(0)';
            }}
          >
            <span>🏠</span>
            <span className="hidden md:inline">Dashboard</span>
          </Link>

          <button
            onClick={theme.toggleTheme}
            style={themeToggleStyle}
            onMouseEnter={(e) => {
              e.target.style.background = theme.colors.background.active;
              e.target.style.borderColor = theme.colors.border.accent;
              e.target.style.transform = 'translateY(-1px)';
            }}
            onMouseLeave={(e) => {
              e.target.style.background = theme.colors.background.hover;
              e.target.style.borderColor = theme.colors.border.primary;
              e.target.style.transform = 'translateY(0)';
            }}
          >
            <span style={{ fontSize: '1rem' }}>
              {theme.isDarkMode ? '☀️' : '🌙'}
            </span>
            <span style={{ fontSize: '0.75rem' }}>
              {theme.isDarkMode ? 'Clair' : 'Sombre'}
            </span>
          </button>
        </div>
      </div>

      {/* Mobile user info - shown below header on small screens */}
      <div style={{
        display: window.innerWidth < 768 ? 'block' : 'none',
        borderTop: `1px solid ${theme.colors.border.primary}`,
        padding: '0.5rem 1rem',
        background: theme.colors.background.secondary,
        textAlign: 'center',
        fontSize: '0.75rem',
        color: theme.colors.text.secondary
      }}>
        <span style={{ fontWeight: '500', color: theme.colors.text.primary }}>
          {userInfo.employeName}
        </span>
        {' - '}
        <span>{userInfo.poste}</span>
        {' - '}
        <span style={{ color: theme.colors.primary }}>
          Niveau {userInfo.niveauMenu}
        </span>
      </div>
    </header>
  );
};

export default Header;