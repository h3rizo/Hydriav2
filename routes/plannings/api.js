// ========== routes/plannings/api.js ==========
const express = require('express');
const router = express.Router();
const db = require('../../models');

// Middleware pour vérifier l'authentification API
function requireApiAuth(req, res, next) {
  if (req.session && req.session.user) {
    next();
  } else {
    res.status(401).json({ error: 'Non autorisé' });
  }
}

// GET - Obtenir tous les plannings
router.get('/plannings', requireApiAuth, async (req, res) => {
  try {
    const { estValide, employeID, activiteID, dateDebut, dateFin } = req.query;
    const where = {};

    if (estValide !== undefined) where.EstValide = estValide === 'true';
    if (employeID) where.EmployeID = employeID;
    if (activiteID) where.ActiviteID = activiteID;
    if (dateDebut && dateFin) {
      where.Date = {
        [db.Sequelize.Op.between]: [dateDebut, dateFin]
      };
    }

    const plannings = await db.Plannings.findAll({
      where,
      include: [
        { model: db.Employes, as: 'Employe' },
        { model: db.Activites, as: 'Activite' },
        { model: db.Ouvrages, as: 'Ouvrage' }
      ],
      order: [['Date', 'DESC']]
    });

    res.json(plannings);
  } catch (error) {
    console.error('Erreur API:', error);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// GET - Obtenir un planning par ID
router.get('/plannings/:id', requireApiAuth, async (req, res) => {
  try {
    const planning = await db.Plannings.findByPk(req.params.id, {
      include: [
        { model: db.Employes, as: 'Employe' },
        { model: db.Activites, as: 'Activite' },
        { model: db.Ouvrages, as: 'Ouvrage' }
      ]
    });

    if (!planning) {
      return res.status(404).json({ error: 'Planning non trouvé' });
    }

    res.json(planning);
  } catch (error) {
    console.error('Erreur API:', error);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// PUT - Mettre à jour un planning
router.put('/plannings/:id', requireApiAuth, async (req, res) => {
  try {
    const [updated] = await db.Plannings.update(req.body, {
      where: { ID: req.params.id }
    });

    if (!updated) {
      return res.status(404).json({ error: 'Planning non trouvé' });
    }

    const planning = await db.Plannings.findByPk(req.params.id);
    res.json(planning);
  } catch (error) {
    console.error('Erreur API:', error);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// POST - Valider un planning
router.post('/plannings/:id/valider', requireApiAuth, async (req, res) => {
  try {
    const planning = await db.Plannings.findByPk(req.params.id);

    if (!planning) {
      return res.status(404).json({ error: 'Planning non trouvé' });
    }

    await planning.update({
      EstValide: true,
      ValidePar: req.session.user.id,
      DateValidation: new Date()
    });

    res.json({ message: 'Planning validé avec succès', planning });
  } catch (error) {
    console.error('Erreur API:', error);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// GET - Obtenir toutes les désignations
router.get('/designations', requireApiAuth, async (req, res) => {
  try {
    const designations = await db.Designations.findAll({
      attributes: ['ID', 'NomDesignation'],
      order: [['NomDesignation', 'ASC']]
    });

    res.json(designations);
  } catch (error) {
    console.error('Erreur API designations:', error);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

module.exports = router;