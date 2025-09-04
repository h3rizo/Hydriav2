import React, { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export const ThemeProvider = ({ children }) => {
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('soakoja-theme');
    return saved ? JSON.parse(saved) : true; // Default to dark mode
  });

  useEffect(() => {
    localStorage.setItem('soakoja-theme', JSON.stringify(isDarkMode));
    document.documentElement.setAttribute('data-theme', isDarkMode ? 'dark' : 'light');
  }, [isDarkMode]);

  const toggleTheme = () => {
    setIsDarkMode(prev => !prev);
  };

  const theme = {
    isDarkMode,
    toggleTheme,
    colors: isDarkMode ? {
      // Dark mode colors
      primary: '#6366f1',
      secondary: '#8b5cf6',
      accent: '#06b6d4',
      background: {
        gradient: 'linear-gradient(135deg, #0F0C29 0%, #24243e 25%, #2b1f48 75%, #302050 100%)',
        primary: 'rgba(15, 12, 41, 0.95)',
        secondary: 'rgba(30, 27, 75, 0.7)',
        card: 'rgba(255, 255, 255, 0.08)',
        hover: 'rgba(255, 255, 255, 0.12)',
        active: 'rgba(255, 255, 255, 0.16)'
      },
      text: {
        primary: '#ffffff',
        secondary: 'rgba(255, 255, 255, 0.8)',
        muted: 'rgba(255, 255, 255, 0.6)'
      },
      border: {
        primary: 'rgba(255, 255, 255, 0.1)',
        secondary: 'rgba(255, 255, 255, 0.08)',
        accent: 'rgba(99, 102, 241, 0.5)'
      }
    } : {
      // Light mode colors
      primary: '#4f46e5',
      secondary: '#7c3aed',
      accent: '#0891b2',
      background: {
        gradient: 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 25%, #cbd5e1 75%, #94a3b8 100%)',
        primary: 'rgba(248, 250, 252, 0.95)',
        secondary: 'rgba(226, 232, 240, 0.8)',
        card: 'rgba(255, 255, 255, 0.6)',
        hover: 'rgba(255, 255, 255, 0.8)',
        active: 'rgba(255, 255, 255, 0.9)'
      },
      text: {
        primary: '#1f2937',
        secondary: 'rgba(31, 41, 55, 0.8)',
        muted: 'rgba(31, 41, 55, 0.6)'
      },
      border: {
        primary: 'rgba(31, 41, 55, 0.1)',
        secondary: 'rgba(31, 41, 55, 0.08)',
        accent: 'rgba(79, 70, 229, 0.3)'
      }
    },
    glassmorphism: {
      backdrop: 'blur(20px)',
      border: '1px solid rgba(255, 255, 255, 0.1)',
      shadow: '0 8px 32px rgba(0, 0, 0, 0.1)'
    },
    transitions: {
      fast: '0.15s ease',
      normal: '0.3s ease',
      slow: '0.5s ease'
    },
    breakpoints: {
      mobile: '640px',
      tablet: '768px',
      desktop: '1024px',
      wide: '1280px'
    }
  };

  return (
    <ThemeContext.Provider value={theme}>
      {children}
    </ThemeContext.Provider>
  );
};