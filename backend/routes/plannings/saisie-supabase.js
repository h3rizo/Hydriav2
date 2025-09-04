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
    // Récupérer les données nécessaires pour le formulaire depuis Supabase
    console.log('📊 Fetching data for form...');

    const [employesResult, ouvragesResult, activitesResult, designationsResult, planningsResult] = await Promise.allSettled([
      supabase.from('Employes').select('ID, Nom, Prenom, Surnom').order('Nom', { ascending: true }),
      supabase.from('Ouvrages').select('*').order('Nom', { ascending: true }),
      supabase.from('Activites').select('*, TypeActivite:TypesActivites(ID, NomType)').order('Nom', { ascending: true }),
      supabase.from('Designations').select('*').order('NomDesignation', { ascending: true }),
      supabase.from('Plannings').select(`
        ID, Date, OuvrageID, EmployeID, ActiviteID, Remarque, EstValide, DebitMesure,
        Employe:Employes(ID, Nom, Prenom, Surnom),
        Activite:Activites(ID, Nom),
        Ouvrage:Ouvrages(ID, Nom)
      `).order('Date', { ascending: false }).limit(50)
    ]);

    const employes = employesResult.status === 'fulfilled' ? (employesResult.value.data || []) : [];
    const ouvrages = ouvragesResult.status === 'fulfilled' ? (ouvragesResult.value.data || []) : [];
    const activites = activitesResult.status === 'fulfilled' ? (activitesResult.value.data || []) : [];
    const designations = designationsResult.status === 'fulfilled' ? (designationsResult.value.data || []) : [];
    const plannings = planningsResult.status === 'fulfilled' ? (planningsResult.value.data || []) : [];

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

    // Créer le nouveau planning avec Supabase
    const { data: planning, error } = await supabase
      .from('Plannings')
      .insert({
        Date: date,
        EmployeID: parseInt(employeID),
        OuvrageID: ouvrageID ? parseInt(ouvrageID) : null,
        ActiviteID: parseInt(activiteID),
        Remarque: remarque || '',
        EstValide: estValide === true || estValide === 'true'
      })
      .select()
      .single();

    if (error) {
      throw error;
    }

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

    const { data: updatedPlanning, error } = await supabase
      .from('Plannings')
      .update(updateData)
      .eq('ID', id)
      .select()
      .single();

    if (error) {
      throw error;
    }

    if (!updatedPlanning) {
      return res.status(404).json({ success: false, error: 'Planning non trouvé' });
    }

    res.json({ success: true, data: updatedPlanning, message: 'Planning mis à jour avec succès' });
  } catch (error) {
    console.error('Erreur update planning:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// DELETE - Supprimer un planning
router.delete('/saisie/:id', requireAuth, async (req, res) => {
  try {
    const { id } = req.params;

    const { error } = await supabase
      .from('Plannings')
      .delete()
      .eq('ID', id);

    if (error) {
      throw error;
    }

    res.json({ success: true, message: 'Planning supprimé avec succès' });
  } catch (error) {
    console.error('Erreur delete planning:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// GET - Récupérer les détails d'un planning
router.get('/details/:id', requireAuth, async (req, res) => {
  try {
    const { id } = req.params;
    console.log(`✅ Get details for planning ${id}`);

    const { data: details, error } = await supabase
      .from('PlanningsDetails')
      .select(`
        *,
        Planning:Plannings(ID, Date),
        Designation:Designations(ID, NomDesignation),
        Acheteur:Employes(ID, Nom, Prenom),
        Magasin:Magasins(ID, Nom),
        Compte:Comptes(ID, NomCompte)
      `)
      .eq('PlanningID', id)
      .order('ID', { ascending: true });

    if (error) {
      throw error;
    }

    console.log(`✅ Found ${details.length} details for planning ${id}`);
    res.json(details || []);
  } catch (error) {
    console.error('❌ Error get details:', error);
    res.status(500).json({ error: 'Erreur lors du chargement des détails' });
  }
});

// POST - Créer un nouveau détail de planning
router.post('/details', requireAuth, async (req, res) => {
  try {
    const {
      PlanningID,
      OuvrageConstitutif,
      DesignationID,
      Quantite,
      PrixUnitaire,
      Montant,
      AcheteurID
    } = req.body;

    const { data: detail, error } = await supabase
      .from('PlanningsDetails')
      .insert({
        PlanningID: parseInt(PlanningID),
        OuvrageConstitutif,
        DesignationID: DesignationID ? parseInt(DesignationID) : null,
        Quantite: parseFloat(Quantite) || 0,
        PrixUnitaire: parseFloat(PrixUnitaire) || 0,
        Montant: parseFloat(Montant) || 0,
        AcheteurID: AcheteurID ? parseInt(AcheteurID) : null
      })
      .select()
      .single();

    if (error) {
      throw error;
    }

    console.log('✅ Detail created:', detail.ID);
    res.json({ success: true, detail });
  } catch (error) {
    console.error('❌ Error creating detail:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// PUT - Mettre à jour un détail de planning
router.put('/details/:id', requireAuth, async (req, res) => {
  try {
    const { id } = req.params;
    const updateData = { ...req.body };

    // Convertir les types appropriés
    if (updateData.Quantite !== undefined) updateData.Quantite = parseFloat(updateData.Quantite) || 0;
    if (updateData.PrixUnitaire !== undefined) updateData.PrixUnitaire = parseFloat(updateData.PrixUnitaire) || 0;
    if (updateData.Montant !== undefined) updateData.Montant = parseFloat(updateData.Montant) || 0;
    if (updateData.DesignationID !== undefined) updateData.DesignationID = updateData.DesignationID ? parseInt(updateData.DesignationID) : null;
    if (updateData.AcheteurID !== undefined) updateData.AcheteurID = updateData.AcheteurID ? parseInt(updateData.AcheteurID) : null;

    const { data: updatedDetail, error } = await supabase
      .from('PlanningsDetails')
      .update(updateData)
      .eq('ID', id)
      .select()
      .single();

    if (error) {
      throw error;
    }

    res.json({ success: true, detail: updatedDetail });
  } catch (error) {
    console.error('❌ Error updating detail:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// DELETE - Supprimer un détail de planning
router.delete('/details/:id', requireAuth, async (req, res) => {
  try {
    const { id } = req.params;

    const { error } = await supabase
      .from('PlanningsDetails')
      .delete()
      .eq('ID', id);

    if (error) {
      throw error;
    }

    res.json({ success: true });
  } catch (error) {
    console.error('❌ Error deleting detail:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

module.exports = router;