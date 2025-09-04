import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useTheme } from '../contexts/ThemeContext';

// Composant StatCard réutilisable
const StatCard = ({ title, value, icon, color, theme }) => {
  const [isHovered, setIsHovered] = useState(false);
  
  return (
    <div 
      className="glass-card"
      style={{
        background: theme.colors.background.card,
        padding: '1.5rem',
        textAlign: 'center',
        border: `1px solid ${color}`,
        transform: isHovered ? 'translateY(-4px)' : 'translateY(0)',
        borderColor: isHovered ? theme.colors.border.accent : color,
        cursor: 'pointer'
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>{icon}</div>
      <h3 style={{ 
        fontSize: '2.5rem', 
        margin: '0.5rem 0', 
        color: theme.colors.text.primary,
        fontWeight: '700'
      }}>{value}</h3>
      <p style={{ 
        margin: 0, 
        color: theme.colors.text.secondary,
        fontSize: '0.875rem',
        fontWeight: '500'
      }}>{title}</p>
    </div>
  );
};

const SimpleDashboard = () => {
  const theme = useTheme();
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        console.log('Fetching dashboard data...');
        const response = await axios.get('/api/dashboard', { withCredentials: true });
        console.log('Dashboard response:', response.data);
        setDashboardData(response.data);
      } catch (err) {
        console.error('Dashboard error:', err);
        setError(`Erreur ${err.response?.status || 'réseau'}: ${err.response?.data?.error || err.message}`);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) return (
    <div className="animate-fadeIn" style={{ 
      display: 'flex', 
      flexDirection: 'column',
      justifyContent: 'center', 
      alignItems: 'center', 
      height: '400px',
      color: theme.colors.text.primary,
      gap: '1rem'
    }}>
      <div className="animate-pulse" style={{ fontSize: '3rem' }}>🔄</div>
      <p style={{ fontSize: '1.125rem', fontWeight: '500' }}>Chargement du dashboard...</p>
    </div>
  );
  
  if (error) return (
    <div className="animate-fadeIn glass-card" style={{ 
      color: '#ef4444', 
      textAlign: 'center', 
      padding: '2rem',
      background: 'rgba(239, 68, 68, 0.1)',
      border: '1px solid #ef4444',
      backdropFilter: theme.glassmorphism.backdrop
    }}>
      <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>⚠️</div>
      <p style={{ margin: 0, fontSize: '1rem' }}>{error}</p>
    </div>
  );

  return (
    <div className="animate-fadeIn" style={{ 
      color: theme.colors.text.primary,
      maxWidth: '1200px',
      margin: '0 auto'
    }}>
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <h1 style={{ 
          fontSize: '2.5rem', 
          fontWeight: '700', 
          marginBottom: '0.5rem',
          background: `linear-gradient(135deg, ${theme.colors.primary}, ${theme.colors.secondary})`,
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text'
        }}>Dashboard Principal</h1>
        <p style={{ 
          color: theme.colors.text.secondary,
          fontSize: '1.125rem'
        }}>Vue d'ensemble de votre système de gestion d'eau</p>
      </div>

      {/* Cartes de statistiques */}
      <section className="grid grid-cols-auto gap-6 mb-8">
        <StatCard 
          title="Employés" 
          value={dashboardData?.stats?.employes || 0} 
          icon="👥" 
          color={theme.colors.accent}
          theme={theme}
        />
        <StatCard 
          title="Ouvrages" 
          value={dashboardData?.stats?.ouvrages || 0} 
          icon="🏗️" 
          color={theme.colors.secondary}
          theme={theme}
        />
        <StatCard 
          title="Plannings" 
          value={dashboardData?.stats?.plannings || 0} 
          icon="🗓️" 
          color={theme.colors.primary}
          theme={theme}
        />
      </section>

      {/* Section graphique */}
      <section className="glass-card" style={{ 
        background: theme.colors.background.card,
        padding: '2rem',
        backdropFilter: theme.glassmorphism.backdrop,
        border: `1px solid ${theme.colors.border.primary}`
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <span style={{ fontSize: '1.5rem' }}>📊</span>
          <h2 style={{ 
            color: theme.colors.text.primary, 
            fontSize: '1.5rem',
            fontWeight: '600',
            margin: 0
          }}>Données des Plannings</h2>
        </div>
        
        <div className="glass-card" style={{
          background: theme.colors.background.hover,
          padding: '1.5rem',
          border: `1px solid ${theme.colors.border.secondary}`,
          textAlign: 'center'
        }}>
          <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>📈</div>
          <p style={{ 
            color: theme.colors.text.secondary,
            marginBottom: '1rem',
            fontSize: '1rem'
          }}>
            Graphique Chart.js sera intégré ici prochainement.
          </p>
          {dashboardData?.chartData && (
            <div style={{
              background: theme.colors.background.secondary,
              padding: '1rem',
              borderRadius: '8px',
              textAlign: 'left',
              fontSize: '0.875rem'
            }}>
              <p><strong>Labels:</strong> {dashboardData.chartData.labels?.join(', ')}</p>
              <p><strong>Données:</strong> {dashboardData.chartData.data?.join(', ')}</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

export default SimpleDashboard;