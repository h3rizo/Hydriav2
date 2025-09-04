import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useTheme } from '../contexts/ThemeContext';

// Composant pour afficher une carte de statistique
const StatCard = ({ title, value, color, icon, theme }) => {
  const [isHovered, setIsHovered] = useState(false);
  
  return (
    <div 
      className="glass-card"
      style={{
        background: theme.colors.background.card,
        border: `2px solid ${color}`,
        padding: '1.5rem',
        textAlign: 'center',
        transform: isHovered ? 'translateY(-4px)' : 'translateY(0)',
        borderColor: isHovered ? theme.colors.border.accent : color,
        cursor: 'pointer'
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>{icon}</div>
      <h3 style={{ 
        margin: '0 0 0.5rem 0', 
        color, 
        fontSize: '2.5rem', 
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

const SuiviAvances = () => {
  const theme = useTheme();
  const [data, setData] = useState({ stats: {}, suiviAvances: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      console.log('🔄 Fetching suivi avances data...');
      
      // Appel à l'API backend React
      const response = await axios.get('/api/react/suivi-avances', {
        headers: {
          'Content-Type': 'application/json'
        },
        withCredentials: true // Pour inclure les cookies de session
      });
      
      console.log('📊 Suivi avances response:', response.data);
      
      if (response.data.success) {
        setData(response.data);
        setError(null);
      } else {
        throw new Error(response.data.message || 'Erreur lors du chargement des données');
      }
    } catch (err) {
      console.error('❌ Suivi avances error:', err);
      console.error('Error response:', err.response);
      
      if (err.response?.status === 401) {
        setError('Session expirée. Veuillez vous reconnecter.');
      } else if (err.response?.status === 404) {
        setError('API suivi avances non trouvée. Vérifiez le serveur backend.');
      } else {
        setError(`Erreur ${err.response?.status || 'réseau'}: ${err.response?.data?.error || err.message}`);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
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
        <p style={{ fontSize: '1.125rem', fontWeight: '500' }}>Chargement des données du suivi...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="animate-fadeIn glass-card" style={{
        color: '#ef4444', 
        background: 'rgba(239, 68, 68, 0.1)',
        border: '1px solid #ef4444',
        padding: '2rem',
        textAlign: 'center',
        backdropFilter: theme.glassmorphism.backdrop
      }}>
        <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>⚠️</div>
        <p style={{ margin: 0, fontSize: '1rem' }}>{error}</p>
      </div>
    );
  }

  return (
    <div className="animate-fadeIn" style={{ 
      color: theme.colors.text.primary,
      maxWidth: '1200px',
      margin: '0 auto'
    }}>
      <header style={{ marginBottom: '3rem', textAlign: 'center', position: 'relative' }}>
        <h1 style={{ 
          fontSize: '2.5rem', 
          fontWeight: '700', 
          marginBottom: '0.5rem',
          background: `linear-gradient(135deg, ${theme.colors.primary}, ${theme.colors.secondary})`,
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text'
        }}>
          📊 Suivi des Avances
        </h1>
        <p style={{ 
          margin: 0, 
          color: theme.colors.text.secondary, 
          fontSize: '1.125rem' 
        }}>
          Vue d'ensemble des avances sur les plannings
        </p>
        <button 
          className="glass-button"
          onClick={fetchData}
          disabled={loading}
          style={{
            position: 'absolute',
            top: '0',
            right: '0',
            background: theme.colors.background.hover,
            border: `1px solid ${theme.colors.border.primary}`,
            color: theme.colors.text.primary,
            cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: '0.875rem',
            opacity: loading ? 0.6 : 1
          }}
          onMouseEnter={(e) => {
            if (!loading) {
              e.target.style.background = theme.colors.background.active;
              e.target.style.borderColor = theme.colors.border.accent;
            }
          }}
          onMouseLeave={(e) => {
            if (!loading) {
              e.target.style.background = theme.colors.background.hover;
              e.target.style.borderColor = theme.colors.border.primary;
            }
          }}
        >
          {loading ? '🔄 Actualisation...' : '🔄 Actualiser'}
        </button>
      </header>

      {/* Cartes de statistiques */}
      <section className="grid grid-cols-auto gap-6 mb-8">
        <StatCard 
          title="Avances en cours" 
          value={data.stats.avances_en_cours || 0} 
          color={theme.colors.secondary}
          icon="⏳"
          theme={theme}
        />
        <StatCard 
          title="Avances livrées" 
          value={data.stats.avances_livrees || 0} 
          color={theme.colors.primary}
          icon="✅"
          theme={theme}
        />
        <StatCard 
          title="Total des avances" 
          value={data.stats.total_avances || 0} 
          color={theme.colors.accent}
          icon="📋"
          theme={theme}
        />
      </section>

      {/* Tableau des avances */}
      <section className="glass-card" style={{
        background: theme.colors.background.card,
        padding: '2rem',
        backdropFilter: theme.glassmorphism.backdrop,
        border: `1px solid ${theme.colors.border.primary}`
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <span style={{ fontSize: '1.5rem' }}>📝</span>
          <h2 style={{ 
            color: theme.colors.text.primary, 
            fontSize: '1.5rem',
            fontWeight: '600',
            margin: 0
          }}>Dernières Avances Enregistrées</h2>
        </div>
        
        {data.suiviAvances && data.suiviAvances.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ 
              width: '100%', 
              borderCollapse: 'collapse',
              fontSize: '0.9rem'
            }}>
              <thead>
                <tr style={{ 
                  background: theme.colors.background.hover,
                  borderBottom: `2px solid ${theme.colors.border.primary}`
                }}>
                  <th style={{ padding: '1rem', textAlign: 'left', color: theme.colors.text.primary, fontWeight: '600' }}>Date Planning</th>
                  <th style={{ padding: '1rem', textAlign: 'left', color: theme.colors.text.primary, fontWeight: '600' }}>Employé</th>
                  <th style={{ padding: '1rem', textAlign: 'left', color: theme.colors.text.primary, fontWeight: '600' }}>Ouvrage</th>
                  <th style={{ padding: '1rem', textAlign: 'left', color: theme.colors.text.primary, fontWeight: '600' }}>Désignation</th>
                  <th style={{ padding: '1rem', textAlign: 'left', color: theme.colors.text.primary, fontWeight: '600' }}>Montant</th>
                  <th style={{ padding: '1rem', textAlign: 'left', color: theme.colors.text.primary, fontWeight: '600' }}>Acheteur</th>
                  <th style={{ padding: '1rem', textAlign: 'left', color: theme.colors.text.primary, fontWeight: '600' }}>Statut</th>
                </tr>
              </thead>
              <tbody>
                {data.suiviAvances.map((avance, index) => (
                  <tr key={avance.id || index} style={{ 
                    borderBottom: `1px solid ${theme.colors.border.primary}`,
                    transition: 'background-color 0.2s ease'
                  }}
                  onMouseEnter={(e) => e.target.closest('tr').style.backgroundColor = theme.colors.background.hover}
                  onMouseLeave={(e) => e.target.closest('tr').style.backgroundColor = 'transparent'}>
                    <td style={{ padding: '1rem', color: theme.colors.text.secondary }}>
                      {avance.planning?.date 
                        ? new Date(avance.planning.date).toLocaleDateString('fr-FR')
                        : 'N/A'
                      }
                    </td>
                    <td style={{ padding: '1rem', color: theme.colors.text.secondary }}>
                      {avance.planning?.employe 
                        ? `${avance.planning.employe.prenom || ''} ${avance.planning.employe.nom || ''}`.trim()
                        : 'N/A'
                      }
                    </td>
                    <td style={{ padding: '1rem', color: theme.colors.text.secondary }}>
                      {avance.planning?.ouvrage?.nom || 'N/A'}
                    </td>
                    <td style={{ padding: '1rem', color: theme.colors.text.secondary }}>
                      {avance.designation?.nom || 'N/A'}
                    </td>
                    <td style={{ padding: '1rem', color: theme.colors.text.secondary }}>
                      {avance.montant 
                        ? `${avance.montant.toLocaleString('fr-FR')} Ar` 
                        : 'N/A'
                      }
                    </td>
                    <td style={{ padding: '1rem', color: theme.colors.text.secondary }}>
                      {avance.acheteur 
                        ? `${avance.acheteur.prenom || ''} ${avance.acheteur.nom || ''}`.trim()
                        : 'N/A'
                      }
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <span style={{
                        padding: '0.4rem 0.8rem',
                        borderRadius: '20px',
                        color: 'white',
                        fontSize: '0.8rem',
                        fontWeight: '500',
                        background: avance.estlivre ? '#28a745' : '#ffc107',
                        textShadow: '0 1px 2px rgba(0,0,0,0.3)'
                      }}>
                        {avance.estlivre ? '✅ Livré' : '⏳ En cours'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="glass-card" style={{
            textAlign: 'center',
            padding: '2rem',
            color: theme.colors.text.secondary,
            fontSize: '1.1rem',
            background: theme.colors.background.hover,
            border: `1px solid ${theme.colors.border.secondary}`
          }}>
            <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>📋</div>
            <p>Aucune avance trouvée</p>
          </div>
        )}
      </section>
    </div>
  );
};

export default SuiviAvances;
