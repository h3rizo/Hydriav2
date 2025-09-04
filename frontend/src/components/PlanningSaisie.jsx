import React, { useState, useEffect } from 'react';
import axios from 'axios';

const PlanningSaisie = () => {
  const [formData, setFormData] = useState({
    DatePlanning: '',
    IDEmploye: '',
    IDOuvrage: '',
    IDOrganisation: '',
    IDPoste: '',
    EstEnCours: false,
    EstTermine: false,
    EstLivre: false,
    Bilan: '',
    SuiteADonner: ''
  });

  const [options, setOptions] = useState({
    employes: [],
    ouvrages: [],
    organisations: [],
    postes: []
  });

  const [filteredOptions, setFilteredOptions] = useState({
    ouvrages: [],
    postes: []
  });

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  useEffect(() => {
    fetchInitialData();
  }, []);

  useEffect(() => {
    // Filtrer les ouvrages selon l'organisation sélectionnée
    if (formData.IDOrganisation) {
      const filtered = options.ouvrages.filter(ouvrage => 
        ouvrage.IDOrganisation == formData.IDOrganisation
      );
      setFilteredOptions(prev => ({
        ...prev,
        ouvrages: filtered
      }));
      // Reset l'ouvrage si il n'est plus valide
      if (formData.IDOuvrage && !filtered.find(o => o.id == formData.IDOuvrage)) {
        setFormData(prev => ({ ...prev, IDOuvrage: '' }));
      }
    } else {
      setFilteredOptions(prev => ({ ...prev, ouvrages: [] }));
      setFormData(prev => ({ ...prev, IDOuvrage: '' }));
    }
  }, [formData.IDOrganisation, options.ouvrages]);

  useEffect(() => {
    // Filtrer les postes selon l'ouvrage sélectionné
    if (formData.IDOuvrage) {
      const filtered = options.postes.filter(poste => 
        poste.IDOuvrage == formData.IDOuvrage
      );
      setFilteredOptions(prev => ({
        ...prev,
        postes: filtered
      }));
      // Reset le poste si il n'est plus valide
      if (formData.IDPoste && !filtered.find(p => p.id == formData.IDPoste)) {
        setFormData(prev => ({ ...prev, IDPoste: '' }));
      }
    } else {
      setFilteredOptions(prev => ({ ...prev, postes: [] }));
      setFormData(prev => ({ ...prev, IDPoste: '' }));
    }
  }, [formData.IDOuvrage, options.postes]);

  const fetchInitialData = async () => {
    try {
      const [employesRes, ouvragesRes, organisationsRes, postesRes] = await Promise.all([
        axios.get('/api/employes', { withCredentials: true }),
        axios.get('/api/ouvrages', { withCredentials: true }),
        axios.get('/api/organisations', { withCredentials: true }),
        axios.get('/api/postes', { withCredentials: true })
      ]);

      setOptions({
        employes: employesRes.data || [],
        ouvrages: ouvragesRes.data || [],
        organisations: organisationsRes.data || [],
        postes: postesRes.data || []
      });
    } catch (error) {
      console.error('Erreur lors du chargement des données:', error);
      setMessage({
        type: 'error',
        text: 'Erreur lors du chargement des données de référence'
      });
    }
  };

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage({ type: '', text: '' });

    try {
      const response = await axios.post('/api/plannings', formData, {
        headers: { 'Content-Type': 'application/json' },
        withCredentials: true
      });

      if (response.status === 201) {
        setMessage({
          type: 'success',
          text: 'Planning créé avec succès !'
        });
        
        // Reset du formulaire
        setFormData({
          DatePlanning: '',
          IDEmploye: '',
          IDOuvrage: '',
          IDOrganisation: '',
          IDPoste: '',
          EstEnCours: false,
          EstTermine: false,
          EstLivre: false,
          Bilan: '',
          SuiteADonner: ''
        });
      }
    } catch (error) {
      console.error('Erreur lors de la création:', error);
      setMessage({
        type: 'error',
        text: error.response?.data?.error || 'Erreur lors de la création du planning'
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      padding: '2rem',
      background: 'linear-gradient(135deg, #0F0C29 0%, #1A1441 25%, #24174C 75%, #2D1F57 100%)',
      minHeight: '100vh',
      color: '#ffffff'
    }}>
      <header style={{ marginBottom: '2rem', textAlign: 'center' }}>
        <h1 style={{
          fontSize: '2.5rem',
          fontWeight: '300',
          margin: '0 0 0.5rem 0',
          textShadow: '0 2px 4px rgba(0,0,0,0.3)'
        }}>
          ✏️ Nouveau Planning
        </h1>
        <p style={{
          color: 'rgba(255, 255, 255, 0.8)',
          fontSize: '1.1rem',
          margin: 0
        }}>
          Création d'un planning de travail
        </p>
      </header>

      {/* Messages */}
      {message.text && (
        <div style={{
          padding: '1rem',
          borderRadius: '8px',
          marginBottom: '2rem',
          textAlign: 'center',
          background: message.type === 'success' 
            ? 'rgba(40, 167, 69, 0.1)' 
            : 'rgba(220, 53, 69, 0.1)',
          border: `1px solid ${message.type === 'success' ? '#28a745' : '#dc3545'}`,
          color: message.type === 'success' ? '#28a745' : '#dc3545'
        }}>
          {message.type === 'success' ? '✅' : '⚠️'} {message.text}
        </div>
      )}

      <div style={{ maxWidth: '800px', margin: '0 auto' }}>
        <form onSubmit={handleSubmit} style={{
          background: 'rgba(255, 255, 255, 0.05)',
          backdropFilter: 'blur(10px)',
          borderRadius: '16px',
          padding: '2rem',
          border: '1px solid rgba(255, 255, 255, 0.1)'
        }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '1.5rem',
            marginBottom: '2rem'
          }}>
            {/* Date du Planning */}
            <div>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '500',
                color: '#fff'
              }}>
                📅 Date du Planning *
              </label>
              <input
                type="date"
                name="DatePlanning"
                value={formData.DatePlanning}
                onChange={handleInputChange}
                required
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#fff',
                  fontSize: '1rem'
                }}
              />
            </div>

            {/* Employé */}
            <div>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '500',
                color: '#fff'
              }}>
                👤 Employé *
              </label>
              <select
                name="IDEmploye"
                value={formData.IDEmploye}
                onChange={handleInputChange}
                required
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#fff',
                  fontSize: '1rem'
                }}
              >
                <option value="">Sélectionner un employé</option>
                {options.employes.map(employe => (
                  <option key={employe.id} value={employe.id} style={{background: '#1A1441', color: '#fff'}}>
                    {employe.prenom} {employe.nom}
                  </option>
                ))}
              </select>
            </div>

            {/* Organisation */}
            <div>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '500',
                color: '#fff'
              }}>
                🏢 Organisation *
              </label>
              <select
                name="IDOrganisation"
                value={formData.IDOrganisation}
                onChange={handleInputChange}
                required
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#fff',
                  fontSize: '1rem'
                }}
              >
                <option value="">Sélectionner une organisation</option>
                {options.organisations.map(org => (
                  <option key={org.id} value={org.id} style={{background: '#1A1441', color: '#fff'}}>
                    {org.nom}
                  </option>
                ))}
              </select>
            </div>

            {/* Ouvrage */}
            <div>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '500',
                color: '#fff'
              }}>
                🏗️ Ouvrage *
              </label>
              <select
                name="IDOuvrage"
                value={formData.IDOuvrage}
                onChange={handleInputChange}
                required
                disabled={!formData.IDOrganisation}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#fff',
                  fontSize: '1rem',
                  opacity: formData.IDOrganisation ? 1 : 0.5
                }}
              >
                <option value="">Sélectionner un ouvrage</option>
                {filteredOptions.ouvrages.map(ouvrage => (
                  <option key={ouvrage.id} value={ouvrage.id} style={{background: '#1A1441', color: '#fff'}}>
                    {ouvrage.nom}
                  </option>
                ))}
              </select>
            </div>

            {/* Poste */}
            <div>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '500',
                color: '#fff'
              }}>
                📍 Poste
              </label>
              <select
                name="IDPoste"
                value={formData.IDPoste}
                onChange={handleInputChange}
                disabled={!formData.IDOuvrage}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#fff',
                  fontSize: '1rem',
                  opacity: formData.IDOuvrage ? 1 : 0.5
                }}
              >
                <option value="">Sélectionner un poste</option>
                {filteredOptions.postes.map(poste => (
                  <option key={poste.id} value={poste.id} style={{background: '#1A1441', color: '#fff'}}>
                    {poste.nom}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Statut */}
          <div style={{ marginBottom: '2rem' }}>
            <h3 style={{ color: '#fff', marginBottom: '1rem' }}>📊 Statut du Planning</h3>
            <div style={{
              display: 'flex',
              gap: '2rem',
              flexWrap: 'wrap'
            }}>
              <label style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                cursor: 'pointer',
                color: '#fff'
              }}>
                <input
                  type="checkbox"
                  name="EstEnCours"
                  checked={formData.EstEnCours}
                  onChange={handleInputChange}
                  style={{ transform: 'scale(1.2)' }}
                />
                ⏳ En cours
              </label>
              
              <label style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                cursor: 'pointer',
                color: '#fff'
              }}>
                <input
                  type="checkbox"
                  name="EstTermine"
                  checked={formData.EstTermine}
                  onChange={handleInputChange}
                  style={{ transform: 'scale(1.2)' }}
                />
                ✅ Terminé
              </label>
              
              <label style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                cursor: 'pointer',
                color: '#fff'
              }}>
                <input
                  type="checkbox"
                  name="EstLivre"
                  checked={formData.EstLivre}
                  onChange={handleInputChange}
                  style={{ transform: 'scale(1.2)' }}
                />
                📦 Livré
              </label>
            </div>
          </div>

          {/* Bilan et Suite à donner */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))',
            gap: '1.5rem',
            marginBottom: '2rem'
          }}>
            <div>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '500',
                color: '#fff'
              }}>
                📝 Bilan
              </label>
              <textarea
                name="Bilan"
                value={formData.Bilan}
                onChange={handleInputChange}
                rows="5"
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#fff',
                  fontSize: '1rem',
                  resize: 'vertical'
                }}
                placeholder="Décrivez le bilan des activités..."
              />
            </div>

            <div>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '500',
                color: '#fff'
              }}>
                🎯 Suite à donner
              </label>
              <textarea
                name="SuiteADonner"
                value={formData.SuiteADonner}
                onChange={handleInputChange}
                rows="5"
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#fff',
                  fontSize: '1rem',
                  resize: 'vertical'
                }}
                placeholder="Indiquez les actions à suivre..."
              />
            </div>
          </div>

          {/* Boutons */}
          <div style={{
            display: 'flex',
            gap: '1rem',
            justifyContent: 'center'
          }}>
            <button
              type="button"
              onClick={() => setFormData({
                DatePlanning: '',
                IDEmploye: '',
                IDOuvrage: '',
                IDOrganisation: '',
                IDPoste: '',
                EstEnCours: false,
                EstTermine: false,
                EstLivre: false,
                Bilan: '',
                SuiteADonner: ''
              })}
              style={{
                padding: '1rem 2rem',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                background: 'transparent',
                color: '#fff',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '1rem',
                transition: 'all 0.2s ease'
              }}
              onMouseEnter={(e) => e.target.style.background = 'rgba(255, 255, 255, 0.1)'}
              onMouseLeave={(e) => e.target.style.background = 'transparent'}
            >
              🔄 Réinitialiser
            </button>

            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '1rem 2rem',
                border: 'none',
                background: loading ? '#6c757d' : '#28a745',
                color: '#fff',
                borderRadius: '8px',
                cursor: loading ? 'not-allowed' : 'pointer',
                fontSize: '1rem',
                transition: 'all 0.2s ease',
                opacity: loading ? 0.7 : 1
              }}
              onMouseEnter={(e) => !loading && (e.target.style.background = '#218838')}
              onMouseLeave={(e) => !loading && (e.target.style.background = '#28a745')}
            >
              {loading ? '⏳ Création...' : '💾 Créer le Planning'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default PlanningSaisie;