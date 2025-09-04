import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTheme } from '../contexts/ThemeContext';

const Navigation = ({ isCollapsed = false }) => {
  const theme = useTheme();
  const location = useLocation();
  const [expandedMenus, setExpandedMenus] = useState({});

  const toggleMenu = (menuKey) => {
    setExpandedMenus(prev => ({
      ...prev,
      [menuKey]: !prev[menuKey]
    }));
  };

  const menuItems = [
    {
      key: 'planning',
      title: 'Planning',
      icon: '📋',
      items: [
        { path: '/plannings/nouveau', label: 'Saisie planning', icon: '✏️' },
        { path: '/plannings/livraisons', label: 'Livraisons', icon: '🚚' },
        { path: '/plannings/avances', label: 'Avances', icon: '💰' },
        { path: '/plannings/retour', label: 'Retour', icon: '↩️' },
        { path: '/plannings/livraison-retour', label: 'Livraison', icon: '🔄' },
        { path: '/plannings/retour-avance', label: 'Retour avance', icon: '💸' },
        { path: '/plannings/retour-indemnites', label: 'Retour d\'indemnités', icon: '💼' },
        { path: '/plannings/retour-frais', label: 'Retour de frais de déplacements', icon: '🚗' }
      ]
    },
    {
      key: 'rapports',
      title: 'Rapport et vues',
      icon: '📊',
      items: [
        { path: '/rapports/saisie', label: 'Saisie rapport', icon: '📝' },
        { path: '/plannings/kanban', label: 'Vue Kanban', icon: '📌' },
        { path: '/plannings/calendrier', label: 'Vue calendrier', icon: '🗓️' },
        { path: '/rapports/vue', label: 'Vue rapport', icon: '📈' },
        { path: '/suivi-avances', label: 'Suivi avance', icon: '📋' }
      ]
    },
    {
      key: 'paiement',
      title: 'Paiement forfaitaire',
      icon: '💳',
      items: [
        { path: '/paiement/saisie', label: 'Saisie', icon: '✍️' },
        { path: '/paiement/suivi', label: 'Suivi', icon: '👀' }
      ]
    },
    {
      key: 'demandes',
      title: 'Demandes BP',
      icon: '📄',
      items: [
        { path: '/demandes/saisie', label: 'Saisie', icon: '📝' },
        { path: '/demandes/suivi', label: 'Suivi demandes', icon: '📊' }
      ]
    },
    {
      key: 'releves',
      title: 'Relevés',
      icon: '📏',
      items: [
        { path: '/releves/saisie', label: 'Saisie', icon: '✏️' },
        { path: '/releves/facturation', label: 'calcul facturation', icon: '🧮' },
        { path: '/releves/encaissement', label: 'Encaissement', icon: '💰' },
        { path: '/releves/suivi-encaissement', label: 'Suivi encaissement', icon: '📈' },
        { path: '/releves/compteurs', label: 'Saisie relevés compteurs de têtes', icon: '⏱️' }
      ]
    },
    {
      key: 'cartes',
      title: 'Cartes sociales',
      icon: '🎫',
      items: [
        { path: '/cartes/saisie', label: 'Saisie', icon: '✏️' },
        { path: '/cartes/facturation', label: 'Facturation et encaissement', icon: '💳' },
        { path: '/cartes/suivi', label: 'Suivi', icon: '👀' }
      ]
    },
    {
      key: 'stocks',
      title: 'Achats et stocks',
      icon: '📦',
      items: [
        { path: '/stocks/inventaires', label: 'Saisie inventaires', icon: '📋' },
        { path: '/stocks/theoriques', label: 'Calcul stocks théoriques', icon: '🧮' },
        { path: '/stocks/achats', label: 'Calcul achats', icon: '🛒' },
        { path: '/stocks/devis', label: 'Demande de devis', icon: '💬' },
        { path: '/stocks/commande', label: 'Bon de commande', icon: '📋' },
        { path: '/stocks/suivi-achats', label: 'Suivi/ saisie achats', icon: '📊' },
        { path: '/stocks/reception', label: 'Réception', icon: '📦' },
        { path: '/stocks/rapprochement', label: 'Rapprochement inventaires / stocks', icon: '🔗' },
        { path: '/stocks/transferts', label: 'Transferts stock', icon: '🔄' }
      ]
    },
    {
      key: 'admin',
      title: 'Admin',
      icon: '⚙️',
      items: [
        { path: '/admin/parametres', label: 'Paramètres par ouvrages', icon: '🔧' },
        { path: '/admin/employes', label: 'Employés', icon: '👥' },
        { path: '/admin/salaires', label: 'Salaires', icon: '💰' }
      ]
    },
    {
      key: 'diamex',
      title: 'Charge DiameX',
      icon: '🔄',
      items: [
        { path: '/diamex/charger', label: 'Charger', icon: '⬆️' },
        { path: '/diamex/ecarts-hydria', label: 'Trouver écarts Hydria / DiameX', icon: '🔍' },
        { path: '/diamex/numeros-hydria', label: 'Trouver numéros DiameX dans Hydria qui n\'existent pas dans DiameX', icon: '🔍' }
      ]
    }
  ];

  const navStyle = {
    width: isCollapsed ? '60px' : '280px',
    height: 'calc(100vh - 80px)',
    position: 'fixed',
    top: '80px',
    left: 0,
    background: theme.colors.background.card,
    backdropFilter: theme.glassmorphism.backdrop,
    WebkitBackdropFilter: theme.glassmorphism.backdrop,
    borderRight: `1px solid ${theme.colors.border.primary}`,
    overflowY: 'auto',
    overflowX: 'hidden',
    zIndex: 100,
    transition: theme.transitions.normal,
    padding: '1rem 0'
  };

  const menuItemStyle = {
    marginBottom: '0.5rem'
  };

  const menuHeaderStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.75rem 1rem',
    cursor: 'pointer',
    color: theme.colors.text.primary,
    fontSize: '0.875rem',
    fontWeight: '600',
    borderRadius: '8px',
    margin: '0 0.5rem',
    transition: theme.transitions.fast,
    background: 'transparent'
  };

  const submenuStyle = {
    paddingLeft: isCollapsed ? '0' : '2rem',
    marginTop: '0.25rem'
  };

  const submenuItemStyle = {
    display: 'block',
    padding: '0.5rem 1rem',
    color: theme.colors.text.secondary,
    textDecoration: 'none',
    fontSize: '0.825rem',
    borderRadius: '6px',
    margin: '0.25rem 0.5rem',
    transition: theme.transitions.fast
  };

  const activeSubmenuItemStyle = {
    ...submenuItemStyle,
    background: theme.colors.background.hover,
    color: theme.colors.primary,
    fontWeight: '500',
    borderLeft: `3px solid ${theme.colors.primary}`
  };

  return (
    <nav style={navStyle}>
      <div style={{ padding: '0 0.5rem' }}>
        {menuItems.map((menu) => (
          <div key={menu.key} style={menuItemStyle}>
            <div
              style={menuHeaderStyle}
              onClick={() => !isCollapsed && toggleMenu(menu.key)}
              onMouseEnter={(e) => {
                if (!isCollapsed) {
                  e.target.style.background = theme.colors.background.hover;
                }
              }}
              onMouseLeave={(e) => {
                if (!isCollapsed) {
                  e.target.style.background = 'transparent';
                }
              }}
            >
              <span style={{ fontSize: '1rem', minWidth: '20px' }}>
                {menu.icon}
              </span>
              {!isCollapsed && (
                <>
                  <span style={{ flex: 1 }}>{menu.title}</span>
                  <span style={{ 
                    transform: expandedMenus[menu.key] ? 'rotate(90deg)' : 'rotate(0deg)',
                    transition: theme.transitions.fast,
                    fontSize: '0.75rem'
                  }}>
                    ▶
                  </span>
                </>
              )}
            </div>
            
            {!isCollapsed && expandedMenus[menu.key] && (
              <div style={submenuStyle}>
                {menu.items.map((item) => {
                  const isActive = location.pathname === item.path;
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      style={isActive ? activeSubmenuItemStyle : submenuItemStyle}
                      onMouseEnter={(e) => {
                        if (!isActive) {
                          e.target.style.background = theme.colors.background.hover;
                          e.target.style.color = theme.colors.text.primary;
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!isActive) {
                          e.target.style.background = 'transparent';
                          e.target.style.color = theme.colors.text.secondary;
                        }
                      }}
                    >
                      <span style={{ marginRight: '0.5rem' }}>{item.icon}</span>
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            )}
            
            {/* Collapsed menu tooltip */}
            {isCollapsed && (
              <div style={{
                position: 'absolute',
                left: '65px',
                top: '0',
                background: theme.colors.background.primary,
                border: `1px solid ${theme.colors.border.primary}`,
                borderRadius: '8px',
                padding: '0.5rem',
                minWidth: '200px',
                zIndex: 1000,
                display: 'none',
                boxShadow: theme.glassmorphism.shadow
              }}
              className="menu-tooltip">
                <div style={{ fontWeight: '600', marginBottom: '0.5rem', color: theme.colors.text.primary }}>
                  {menu.title}
                </div>
                {menu.items.map((item) => (
                  <Link
                    key={item.path}
                    to={item.path}
                    style={{
                      display: 'block',
                      padding: '0.25rem 0',
                      color: theme.colors.text.secondary,
                      textDecoration: 'none',
                      fontSize: '0.75rem'
                    }}
                  >
                    {item.icon} {item.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </nav>
  );
};

export default Navigation;