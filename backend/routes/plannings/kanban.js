const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

// Route pour afficher la page kanban
router.get('/', async (req, res) => {
  try {
    res.render('plannings/kanban', {
      user: req.session.user,
      pageTitle: 'Vue Kanban'
    });
  } catch (error) {
    console.error('Erreur lors du rendu kanban:', error);
    res.status(500).render('error', { error: 'Erreur lors du chargement du kanban' });
  }
});

// Route pour fournir les données JSON du kanban
router.get('/data', async (req, res) => {
  try {
    // Récupérer les plannings avec leurs relations depuis Supabase
    const { data: plannings, error: planningsError } = await supabase
      .from('Plannings')
      .select(`
        ID,
        Date,
        Bilan,
        SuiteADonner,
        Employe:Employes(ID, Nom, Prenom),
        Ouvrage:Ouvrages(ID, Nom, TypeOuvrageID),
        TypeOuvrage:TypesOuvrages(ID, NomType)
      `)
      .order('Date', { ascending: false })
      .limit(100);

    if (planningsError) {
      throw planningsError;
    }

    // Récupérer les types d'ouvrages
    const { data: types, error: typesError } = await supabase
      .from('TypesOuvrages')
      .select('ID, NomType')
      .order('NomType', { ascending: true });

    if (typesError) {
      throw typesError;
    }

    // Formatter les données pour le kanban
    const formattedCards = (plannings || []).map(card => ({
      id: card.ID,
      ouvrageNom: card.Ouvrage?.Nom || 'Ouvrage inconnu',
      employeNom: `${card.Employe?.Prenom || ''} ${card.Employe?.Nom || ''}`.trim() || 'Employé inconnu',
      date: card.Date,
      typeOuvrageId: card.Ouvrage?.TypeOuvrageID || card.TypeOuvrage?.ID || 1,
      Bilan: card.Bilan || '',
      SuiteADonner: card.SuiteADonner || ''
    }));

    const formattedTypes = (types || []).map(type => ({
      id: type.ID,
      nom: type.NomType
    }));

    console.log(`Données kanban: ${formattedCards.length} cartes, ${formattedTypes.length} types`);

    res.json({
      cards: formattedCards,
      types: formattedTypes
    });

  } catch (error) {
    console.error('Erreur lors de la récupération des données kanban:', error);
    res.status(500).json({
      error: 'Erreur serveur lors de la récupération des données',
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

module.exports = router;