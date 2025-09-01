const express = require('express');
const router = express.Router();

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
    // Récupérer les modèles depuis la base
    const db = require('../../models/index.js');

    if (!db || !db.Plannings) {
      return res.status(500).json({
        error: 'Base de données non disponible'
      });
    }

    // Récupérer les plannings avec leurs relations
    const cards = await db.Plannings.findAll({
      include: [
        {
          model: db.Employes,
          as: 'Employe',
          attributes: ['ID', 'Nom', 'Prenom']
        },
        {
          model: db.Ouvrages,
          as: 'Ouvrage',
          attributes: ['ID', 'Nom']
        },
        {
          model: db.TypesOuvrages,
          as: 'TypeOuvrage',
          attributes: ['ID', 'Nom']
        }
      ],
      order: [['Date', 'DESC']],
      limit: 100
    });

    // Récupérer les types d'ouvrages
    const types = await db.TypesOuvrages.findAll({
      attributes: ['ID', 'Nom'],
      order: [['Nom', 'ASC']]
    });

    // Formatter les données pour le kanban
    const formattedCards = cards.map(card => ({
      id: card.ID,
      ouvrageNom: card.Ouvrage?.Nom || 'Ouvrage inconnu',
      employeNom: `${card.Employe?.Prenom || ''} ${card.Employe?.Nom || ''}`.trim() || 'Employé inconnu',
      date: card.Date,
      typeOuvrageId: card.TypeOuvrage?.ID || 1,
      Bilan: card.Bilan || '',
      SuiteADonner: card.SuiteADonner || ''
    }));

    const formattedTypes = types.map(type => ({
      id: type.ID,
      nom: type.Nom
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