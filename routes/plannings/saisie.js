// ========== routes/plannings/saisie.js ==========
const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

// Middleware d'authentification
function requireAuth(req, res, next) {
  if (req.session && req.session.user) {
    next();
  } else {
    res.redirect('/login');
  }
}

// GET - Afficher le formulaire de saisie
router.get('/saisie', requireAuth, async (req, res) => {
  console.log('📋 Accessing /plannings/saisie route');

  try {
    // Vérifier que db est disponible
    if (!db) {
      console.error('❌ Database object not available');
      return res.status(500).send('Database not initialized');
    }

    console.log('🔍 Available models:', Object.keys(db).filter(key =>
      key !== 'sequelize' && key !== 'Sequelize' && typeof db[key] === 'object'
    ));

    // Récupérer les données nécessaires pour le formulaire
    console.log('📊 Fetching data for form...');

    const employes = db.Employes ? await db.Employes.findAll({
      order: [['Nom', 'ASC']],
      attributes: ['ID', 'Nom', 'Prenom', 'Surnom']
    }).catch(err => {
      console.error('Error fetching employes:', err.message);
      return [];
    }) : [];

    const ouvrages = db.Ouvrages ? await db.Ouvrages.findAll({
      order: [['Nom', 'ASC']]
    }).catch(err => {
      console.error('Error fetching ouvrages:', err.message);
      return [];
    }) : [];

    const activites = db.Activites ? await db.Activites.findAll({
      order: [['Nom', 'ASC']],
      include: [{
        model: db.TypesActivites,
        as: 'TypeActivite',
        attributes: ['ID', 'NomType']
      }]
    }).catch(err => {
      console.error('Error fetching activites:', err.message);
      return [];
    }) : [];

    const designations = db.Designations ? await db.Designations.findAll({
      order: [['NomDesignation', 'ASC']]
    }).catch(err => {
      console.error('Error fetching designations:', err.message);
      return [];
    }) : [];

    const plannings = db.Plannings ? await db.Plannings.findAll({
      order: [['Date', 'DESC']],
      limit: 50,
      attributes: ['ID', 'Date', 'OuvrageID', 'EmployeID', 'ActiviteID', 'Remarque', 'EstValide', 'DebitMesure'],
      include: [
        {
          model: db.Employes,
          as: 'Employe',
          attributes: ['ID', 'Nom', 'Prenom', 'Surnom'],
          required: false
        },
        {
          model: db.Activites,
          as: 'Activite',
          attributes: ['ID', 'Nom'],
          required: false
        },
        {
          model: db.Ouvrages,
          as: 'Ouvrage',
          attributes: ['ID', 'Nom'],
          required: false
        }
      ]
    }).catch(err => {
      console.error('Error fetching plannings:', err.message);
      console.error('Error details:', err.stack);
      return [];
    }) : [];

    console.log(`✅ Data fetched - Employes: ${employes.length}, Ouvrages: ${ouvrages.length}, Activites: ${activites.length}, Designations: ${designations.length}, Plannings: ${plannings.length}`);

    // Debug: Log the first planning record if available
    if (plannings.length > 0) {
      console.log('🔍 First planning data:', {
        ID: plannings[0].ID,
        Date: plannings[0].Date,
        EmployeID: plannings[0].EmployeID,
        ActiviteID: plannings[0].ActiviteID,
        OuvrageID: plannings[0].OuvrageID,
        Employe: plannings[0].Employe ? plannings[0].Employe.Nom : 'NULL',
        Activite: plannings[0].Activite ? plannings[0].Activite.Nom : 'NULL'
      });
    } else {
      console.log('⚠️ No plannings found in database');
    }

    res.render('plannings/saisie', {
      pageTitle: 'Saisie Planning',
      user: req.session.user,
      employes,
      ouvrages,
      activites,
      designations,
      plannings,
      message: req.query.message,
      error: req.query.error
    });
  } catch (error) {
    console.error('❌ Error in /saisie route:', error);

    // Fallback: render with empty data
    res.render('plannings/saisie', {
      pageTitle: 'Saisie Planning',
      user: req.session.user,
      employes: [],
      ouvrages: [],
      activites: [],
      designations: [],
      plannings: [],
      error: 'Erreur lors du chargement des données: ' + error.message
    });
  }
});

// POST - Enregistrer un nouveau planning
router.post('/saisie', requireAuth, async (req, res) => {
  try {
    const {
      date,
      employeID,
      ouvrageID,
      activiteID,
      remarque,
      estValide
    } = req.body;

    // Créer le nouveau planning
    const planning = await db.Plannings.create({
      Date: date,
      EmployeID: parseInt(employeID),
      OuvrageID: ouvrageID ? parseInt(ouvrageID) : null,
      ActiviteID: parseInt(activiteID),
      Remarque: remarque || '',
      EstValide: estValide === true || estValide === 'true'
    });

    if (req.headers['content-type'] === 'application/json') {
      res.json({ success: true, id: planning.ID, message: 'Planning créé avec succès' });
    } else {
      res.redirect('/plannings/saisie?message=Planning créé avec succès');
    }
  } catch (error) {
    console.error('Erreur:', error);
    if (req.headers['content-type'] === 'application/json') {
      res.status(500).json({ success: false, error: error.message });
    } else {
      res.redirect('/plannings/saisie?error=Erreur lors de la création du planning');
    }
  }
});

// PUT - Modifier un planning (AJAX)
router.put('/saisie/:id', requireAuth, async (req, res) => {
  try {
    const { id } = req.params;
    const updateData = {};

    // Traiter et valider les données
    if (req.body.Date) updateData.Date = new Date(req.body.Date);
    if (req.body.EmployeID) updateData.EmployeID = parseInt(req.body.EmployeID);
    if (req.body.OuvrageID !== undefined) updateData.OuvrageID = req.body.OuvrageID ? parseInt(req.body.OuvrageID) : null;
    if (req.body.ActiviteID) updateData.ActiviteID = parseInt(req.body.ActiviteID);
    if (req.body.Remarque !== undefined) updateData.Remarque = req.body.Remarque;
    if (req.body.EstValide !== undefined) updateData.EstValide = req.body.EstValide === 'true' || req.body.EstValide === true;

    const [updatedRowsCount] = await db.Plannings.update(updateData, {
      where: { ID: id }
    });

    if (updatedRowsCount === 0) {
      return res.status(404).json({ success: false, error: 'Planning non trouvé' });
    }

    res.json({ success: true, message: 'Planning mis à jour' });
  } catch (error) {
    console.error('Erreur update:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// DELETE - Supprimer un planning (AJAX)
router.delete('/saisie/:id', requireAuth, async (req, res) => {
  try {
    const { id } = req.params;

    // Supprimer d'abord les détails associés
    await db.PlanningsDetails.destroy({
      where: { PlanningID: id }
    });

    // Puis supprimer le planning
    const deletedRowsCount = await db.Plannings.destroy({
      where: { ID: id }
    });

    if (deletedRowsCount === 0) {
      return res.status(404).json({ success: false, error: 'Planning non trouvé' });
    }

    res.json({ success: true, message: 'Planning supprimé' });
  } catch (error) {
    console.error('Erreur delete:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// GET - Récupérer les détails d'un planning
router.get('/saisie/:id/details', requireAuth, async (req, res) => {
  try {
    const { id } = req.params;
    console.log('🔍 GET planning details for ID:', id);

    if (!db.PlanningsDetails) {
      console.log('⚠️ PlanningsDetails model not available');
      return res.json([]);
    }

    const details = await db.PlanningsDetails.findAll({
      where: { PlanningID: id },
      include: [
        {
          model: db.Designations,
          as: 'Designation',
          attributes: ['ID', 'NomDesignation'],
          required: false
        },
        {
          model: db.Employes,
          as: 'Acheteur',
          attributes: ['ID', 'Nom', 'Prenom', 'Surnom'],
          required: false
        }
      ],
      order: [['ID', 'ASC']]
    }).catch(err => {
      console.error('Error in details query:', err.message);
      return [];
    });

    console.log(`✅ Found ${details.length} details for planning ${id}`);
    res.json(details);
  } catch (error) {
    console.error('❌ Error get details:', error);
    res.status(500).json({ error: 'Erreur lors du chargement des détails' });
  }
});

// POST - Créer un nouveau détail de planning
router.post('/details', requireAuth, async (req, res) => {
  try {
    if (!db.PlanningsDetails) {
      return res.status(500).json({ error: 'Modèle PlanningsDetails non disponible' });
    }

    const {
      PlanningID,
      OuvrageConstitutif,
      DesignationID,
      Quantite,
      PrixUnitaire,
      Montant,
      AcheteurID
    } = req.body;

    const detail = await db.PlanningsDetails.create({
      PlanningID: parseInt(PlanningID),
      OuvrageConstitutif,
      DesignationID: DesignationID ? parseInt(DesignationID) : null,
      Quantite: parseFloat(Quantite) || 0,
      PrixUnitaire: parseFloat(PrixUnitaire) || 0,
      Montant: parseFloat(Montant) || 0,
      AcheteurID: AcheteurID ? parseInt(AcheteurID) : null
    });

    res.json({ success: true, id: detail.ID, message: 'Détail créé avec succès' });
  } catch (error) {
    console.error('Erreur create detail:', error);
    res.status(500).json({ error: 'Erreur lors de la création du détail: ' + error.message });
  }
});

// PUT - Modifier un détail de planning
router.put('/details/:id', requireAuth, async (req, res) => {
  try {
    const { id } = req.params;
    const updateData = {};

    // Traiter les données
    if (req.body.OuvrageConstitutif !== undefined) updateData.OuvrageConstitutif = req.body.OuvrageConstitutif;
    if (req.body.DesignationID !== undefined) updateData.DesignationID = req.body.DesignationID ? parseInt(req.body.DesignationID) : null;
    if (req.body.Quantite !== undefined) updateData.Quantite = parseFloat(req.body.Quantite) || 0;
    if (req.body.PrixUnitaire !== undefined) updateData.PrixUnitaire = parseFloat(req.body.PrixUnitaire) || 0;
    if (req.body.Montant !== undefined) updateData.Montant = parseFloat(req.body.Montant) || 0;
    if (req.body.AcheteurID !== undefined) updateData.AcheteurID = req.body.AcheteurID ? parseInt(req.body.AcheteurID) : null;

    const [updatedRowsCount] = await db.PlanningsDetails.update(updateData, {
      where: { ID: id }
    });

    if (updatedRowsCount === 0) {
      return res.status(404).json({ success: false, error: 'Détail non trouvé' });
    }

    res.json({ success: true, message: 'Détail mis à jour' });
  } catch (error) {
    console.error('Erreur update detail:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// DELETE - Supprimer un détail de planning
router.delete('/details/:id', requireAuth, async (req, res) => {
  try {
    const { id } = req.params;

    if (!db.PlanningsDetails) {
      return res.status(500).json({ error: 'Modèle PlanningsDetails non disponible' });
    }

    const deletedRowsCount = await db.PlanningsDetails.destroy({
      where: { ID: id }
    });

    if (deletedRowsCount === 0) {
      return res.status(404).json({ success: false, error: 'Détail non trouvé' });
    }

    res.json({ success: true, message: 'Détail supprimé' });
  } catch (error) {
    console.error('Erreur delete detail:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// GET - API pour récupérer les désignations (pour les dropdowns)
router.get('/api/designations', requireAuth, async (req, res) => {
  try {
    const designations = db.Designations ? await db.Designations.findAll({
      attributes: ['ID', 'NomDesignation'],
      order: [['NomDesignation', 'ASC']]
    }).catch(() => []) : [];

    res.json(designations);
  } catch (error) {
    console.error('Erreur get designations:', error);
    res.status(500).json({ error: 'Erreur lors du chargement des désignations' });
  }
});

module.exports = router;