import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTheme } from '../contexts/ThemeContext';

const HorizontalNavigation = () => {
  const theme = useTheme();
  const location = useLocation();
  const [expandedMenu, setExpandedMenu] = useState(null);
  const [dropdownPosition, setDropdownPosition] = useState({ left: 0, width: 0 });
  const [isMobile, setIsMobile] = useState(false);
  const menuRefs = useRef({});

  // Détecter la taille de l'écran
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    
    handleResize();
    window.addEventListener('resize', handleResize);
    
    return () => window.removeEventListener('resize', handleResize);
  }, []);

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
        { path: '/releves/facturation', label: 'Calcul facturation', icon: '🧮' },
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

  // Calculer la position du dropdown
  useEffect(() => {
    if (expandedMenu && menuRefs.current[expandedMenu]) {
      const rect = menuRefs.current[expandedMenu].getBoundingClientRect();
      setDropdownPosition({
        left: rect.left,
        width: Math.max(280, rect.width)
      });
    }
  }, [expandedMenu]);

  const navStyle = {
    position: 'fixed',
    top: '80px',
    left: 0,
    right: 0,
    zIndex: 100,
    background: theme.colors.background.card,
    backdropFilter: theme.glassmorphism.backdrop,
    WebkitBackdropFilter: theme.glassmorphism.backdrop,
    borderBottom: `1px solid ${theme.colors.border.primary}`,
    boxShadow: '0 4px 20px rgba(0, 0, 0, 0.1)',
    transition: theme.transitions.normal,
    width: '100vw' // Prendre toute la largeur de l'écran
  };

  const containerStyle = {
    width: '100%',
    padding: '0 1rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: isMobile ? 'flex-start' : 'center', // Centrer sur desktop, aligné à gauche sur mobile
    gap: isMobile ? '0.25rem' : '0.5rem',
    overflowX: 'auto',
    scrollbarWidth: 'none',
    WebkitScrollbarWidth: 'none',
    msOverflowStyle: 'none'
  };

  const menuItemStyle = {
    position: 'relative'
  };

  const menuButtonStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: isMobile ? '0.25rem' : '0.5rem',
    padding: isMobile ? '0.5rem 0.75rem' : '0.75rem 1rem',
    background: 'transparent',
    border: 'none',
    color: theme.colors.text.primary,
    fontSize: isMobile ? '0.75rem' : '0.875rem',
    fontWeight: '500',
    cursor: 'pointer',
    borderRadius: '8px',
    transition: theme.transitions.fast,
    whiteSpace: 'nowrap',
    minWidth: 'fit-content',
    flexShrink: 0
  };

  const activeMenuButtonStyle = {
    ...menuButtonStyle,
    background: theme.colors.background.hover,
    color: theme.colors.primary
  };

  const dropdownStyle = {
    position: 'fixed',
    top: '140px', // Header (80px) + Navbar (60px)
    left: `${dropdownPosition.left}px`,
    minWidth: `${dropdownPosition.width}px`,
    maxWidth: '400px',
    background: theme.colors.background.primary,
    backdropFilter: theme.glassmorphism.backdrop,
    WebkitBackdropFilter: theme.glassmorphism.backdrop,
    border: `1px solid ${theme.colors.border.primary}`,
    borderRadius: '12px',
    padding: '0.75rem',
    zIndex: 1000,
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.2)',
    maxHeight: '400px',
    overflowY: 'auto'
  };

  const dropdownItemStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.75rem 1rem',
    color: theme.colors.text.secondary,
    textDecoration: 'none',
    fontSize: '0.875rem',
    borderRadius: '8px',
    transition: theme.transitions.fast,
    margin: '0.125rem 0'
  };

  const activeDropdownItemStyle = {
    ...dropdownItemStyle,
    background: theme.colors.background.hover,
    color: theme.colors.primary,
    fontWeight: '500'
  };

  // Check if any item in a menu is active
  const isMenuActive = (menu) => {
    return menu.items.some(item => location.pathname === item.path);
  };

  const handleMouseEnter = (menuKey) => {
    setExpandedMenu(menuKey);
  };

  const handleMouseLeave = () => {
    // Délai pour éviter le clignotement
    setTimeout(() => {
      setExpandedMenu(null);
    }, 100);
  };

  return (
    <>
      {/* Style pour masquer la scrollbar */}
      <style>
        {`
          .navbar-container::-webkit-scrollbar {
            display: none;
          }
          .navbar-container {
            -ms-overflow-style: none;
            scrollbar-width: none;
          }
          @media (max-width: 768px) {
            .navbar-container {
              justify-content: flex-start !important;
            }
          }
        `}
      </style>
      
      <nav style={navStyle}>
        <div style={containerStyle} className="navbar-container">
          {menuItems.map((menu) => {
            const isActive = isMenuActive(menu);
            const isExpanded = expandedMenu === menu.key;
            
            return (
              <div 
                key={menu.key} 
                style={menuItemStyle}
                ref={el => menuRefs.current[menu.key] = el}
                onMouseEnter={() => handleMouseEnter(menu.key)}
              >
                <button
                  style={isActive || isExpanded ? activeMenuButtonStyle : menuButtonStyle}
                >
                  <span>{menu.icon}</span>
                  <span>{menu.title}</span>
                  <span style={{ 
                    transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                    transition: theme.transitions.fast,
                    fontSize: '0.75rem',
                    marginLeft: '0.25rem'
                  }}>
                    ▼
                  </span>
                </button>
              </div>
            );
          })}
        </div>
      </nav>

      {/* Dropdown */}
      {expandedMenu && (
        <div 
          style={dropdownStyle}
          onMouseEnter={() => setExpandedMenu(expandedMenu)}
          onMouseLeave={handleMouseLeave}
        >
          {menuItems.find(m => m.key === expandedMenu)?.items.map((item) => {
            const isItemActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                style={isItemActive ? activeDropdownItemStyle : dropdownItemStyle}
                onClick={() => setExpandedMenu(null)}
                onMouseEnter={(e) => {
                  if (!isItemActive) {
                    e.target.style.background = theme.colors.background.hover;
                    e.target.style.color = theme.colors.text.primary;
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isItemActive) {
                    e.target.style.background = 'transparent';
                    e.target.style.color = theme.colors.text.secondary;
                  }
                }}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
};

export default HorizontalNavigation;