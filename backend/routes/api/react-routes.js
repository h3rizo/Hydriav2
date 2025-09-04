const express = require('express');
const router = express.Router();
const { requireAuth, requireApiAuth } = require('../../middleware/auth');
const { supabase } = require('../../supabaseClient');

// Route pour obtenir les données du suivi des avances
router.get('/react/suivi-avances', async (req, res) => {
  try {
    console.log('📊 API React Suivi Avances: Chargement des données...');

    // Pour l'instant, retourner des données de test car nous n'avons pas encore la table planningsdetails
    const stats = {
      avances_en_cours: 5,
      avances_livrees: 12,
      total_avances: 17
    };

    const suiviAvances = [
      {
        id: 1,
        montant: 50000,
        estlivre: false,
        planning: {
          date: '2025-01-15',
          employe: { nom: 'Rakoto', prenom: 'Jean' },
          ouvrage: { nom: 'Forage Antsirabe' }
        },
        designation: { nom: 'Matériaux construction' },
        acheteur: { nom: 'Andriani', prenom: 'Marie' }
      },
      {
        id: 2,
        montant: 75000,
        estlivre: true,
        planning: {
          date: '2025-01-10',
          employe: { nom: 'Rasofy', prenom: 'Paul' },
          ouvrage: { nom: 'Réhabilitation Fianarantsoa' }
        },
        designation: { nom: 'Outils spécialisés' },
        acheteur: { nom: 'Hery', prenom: 'Luc' }
      }
    ];

    res.json({
      success: true,
      stats,
      suiviAvances
    });

  } catch (error) {
    console.error('❌ Erreur Suivi Avances API:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Erreur lors du chargement du suivi des avances'
    });
  }
});

// Route pour obtenir les données du Kanban  
router.get('/react/kanban', async (req, res) => {
  try {
    console.log('📋 API React Kanban: Chargement des données...');

    // Données de test pour le Kanban
    const plannings = [
      {
        id: 1,
        DatePlanning: '2025-01-15',
        EstEnCours: false,
        EstTermine: false,
        EstLivre: false,
        Bilan: 'Début des travaux de forage',
        SuiteADonner: 'Continuer le forage jusqu\'à 30 mètres',
        employe: { id: 1, nom: 'Rakoto', prenom: 'Jean' },
        ouvrage: { id: 1, nom: 'Forage Antsirabe' },
        organisation: { id: 1, nom: 'JIRAMA Antsirabe' }
      },
      {
        id: 2,
        DatePlanning: '2025-01-10',
        EstEnCours: true,
        EstTermine: false,
        EstLivre: false,
        Bilan: 'Installation des équipements en cours',
        SuiteADonner: 'Finaliser l\'installation électrique',
        employe: { id: 2, nom: 'Rasofy', prenom: 'Paul' },
        ouvrage: { id: 2, nom: 'Réhabilitation Fianarantsoa' },
        organisation: { id: 2, nom: 'JIRAMA Fianarantsoa' }
      },
      {
        id: 3,
        DatePlanning: '2025-01-05',
        EstEnCours: false,
        EstTermine: true,
        EstLivre: false,
        Bilan: 'Travaux de maçonnerie terminés',
        SuiteADonner: 'Procéder aux tests de qualité',
        employe: { id: 3, nom: 'Andriani', prenom: 'Marie' },
        ouvrage: { id: 3, nom: 'Construction Mahajanga' },
        organisation: { id: 3, nom: 'JIRAMA Mahajanga' }
      },
      {
        id: 4,
        DatePlanning: '2025-01-01',
        EstEnCours: false,
        EstTermine: true,
        EstLivre: true,
        Bilan: 'Projet livré avec succès',
        SuiteADonner: 'Maintenance préventive dans 6 mois',
        employe: { id: 4, nom: 'Hery', prenom: 'Luc' },
        ouvrage: { id: 4, nom: 'Extension Toamasina' },
        organisation: { id: 4, nom: 'JIRAMA Toamasina' }
      }
    ];

    res.json({
      success: true,
      plannings: plannings || []
    });
  } catch (error) {
    console.error('Erreur kanban API:', error);
    res.status(500).json({
      success: false,
      error: 'Erreur lors du chargement du kanban'
    });
  }
});

// Route pour obtenir les employés
router.get('/employes', async (req, res) => {
  try {
    const { data: employes, error } = await supabase
      .from('employes')
      .select('id, nom, prenom')
      .order('nom');

    if (error) throw error;

    res.json(employes || []);
  } catch (error) {
    console.error('Erreur employés API:', error);
    res.status(500).json({
      error: 'Erreur lors du chargement des employés'
    });
  }
});

// Route pour obtenir les organisations
router.get('/organisations', async (req, res) => {
  try {
    const { data: organisations, error } = await supabase
      .from('organisations')
      .select('id, nom')
      .order('nom');

    if (error) throw error;

    res.json(organisations || []);
  } catch (error) {
    console.error('Erreur organisations API:', error);
    res.status(500).json({
      error: 'Erreur lors du chargement des organisations'
    });
  }
});

// Route pour obtenir les ouvrages
router.get('/ouvrages', async (req, res) => {
  try {
    const { data: ouvrages, error } = await supabase
      .from('ouvrages')
      .select('id, nom')
      .order('nom');

    if (error) throw error;

    res.json(ouvrages || []);
  } catch (error) {
    console.error('Erreur ouvrages API:', error);
    res.status(500).json({
      error: 'Erreur lors du chargement des ouvrages'
    });
  }
});

// Route pour obtenir les postes
router.get('/postes', async (req, res) => {
  try {
    const { data: postes, error } = await supabase
      .from('postes')
      .select('id, nom')
      .order('nom');

    if (error) throw error;

    res.json(postes || []);
  } catch (error) {
    console.error('Erreur postes API:', error);
    res.status(500).json({
      error: 'Erreur lors du chargement des postes'
    });
  }
});

// Route pour créer un nouveau planning
router.post('/plannings', async (req, res) => {
  try {
    console.log('Création de planning:', req.body);

    const {
      DatePlanning,
      IDEmploye,
      IDOuvrage,
      IDOrganisation,
      IDPoste,
      EstEnCours,
      EstTermine,
      EstLivre,
      Bilan,
      SuiteADonner
    } = req.body;

    // Validation
    if (!DatePlanning || !IDEmploye || !IDOrganisation) {
      return res.status(400).json({
        error: 'Date, employé et organisation sont requis'
      });
    }

    const planningData = {
      dateplanning: DatePlanning,
      employeid: parseInt(IDEmploye),
      ouvrageid: IDOuvrage ? parseInt(IDOuvrage) : null,
      posteid: IDPoste ? parseInt(IDPoste) : null,
      estencours: EstEnCours || false,
      esttermine: EstTermine || false,
      estlivre: EstLivre || false,
      bilan: Bilan || null,
      suiteadonner: SuiteADonner || null,
      dateCreation: new Date().toISOString()
    };

    const { data, error } = await supabase
      .from('plannings')
      .insert([planningData])
      .select()
      .single();

    if (error) {
      console.error('Erreur Supabase création planning:', error);
      throw error;
    }

    res.status(201).json({
      success: true,
      planning: data,
      message: 'Planning créé avec succès'
    });
  } catch (error) {
    console.error('Erreur création planning:', error);
    res.status(500).json({
      error: error.message || 'Erreur lors de la création du planning'
    });
  }
});

// Route pour mettre à jour les détails d'un planning (bilan/suite)
router.put('/plannings/:id/details', async (req, res) => {
  try {
    const { id } = req.params;
    const { Bilan, SuiteADonner } = req.body;

    console.log(`Mise à jour détails planning ${id}:`, { Bilan, SuiteADonner });

    const { data, error } = await supabase
      .from('plannings')
      .update({
        bilan: Bilan,
        suiteadonner: SuiteADonner
      })
      .eq('id', id)
      .select()
      .single();

    if (error) {
      console.error('Erreur Supabase mise à jour:', error);
      throw error;
    }

    res.json({
      success: true,
      planning: data,
      message: 'Planning mis à jour avec succès'
    });
  } catch (error) {
    console.error('Erreur mise à jour planning:', error);
    res.status(500).json({
      error: error.message || 'Erreur lors de la mise à jour'
    });
  }
});

module.exports = router;