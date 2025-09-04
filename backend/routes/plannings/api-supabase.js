// ========== routes/plannings/api.js ==========
const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

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

    let query = supabase
      .from('Plannings')
      .select(`
        *,
        Employe:Employes(ID, Nom, Prenom),
        Activite:Activites(ID, Nom),
        Ouvrage:Ouvrages(ID, Nom)
      `);

    // Appliquer les filtres
    if (estValide !== undefined) query = query.eq('EstValide', estValide === 'true');
    if (employeID) query = query.eq('EmployeID', employeID);
    if (activiteID) query = query.eq('ActiviteID', activiteID);
    if (dateDebut) query = query.gte('Date', dateDebut);
    if (dateFin) query = query.lte('Date', dateFin);

    const { data: plannings, error } = await query.order('Date', { ascending: false });

    if (error) {
      throw error;
    }

    res.json(plannings || []);
  } catch (error) {
    console.error('Erreur API:', error);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// GET - Obtenir un planning par ID
router.get('/plannings/:id', requireApiAuth, async (req, res) => {
  try {
    const { data: planning, error } = await supabase
      .from('Plannings')
      .select(`
        *,
        Employe:Employes(ID, Nom, Prenom),
        Activite:Activites(ID, Nom),
        Ouvrage:Ouvrages(ID, Nom)
      `)
      .eq('ID', req.params.id)
      .single();

    if (error) {
      throw error;
    }

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
    const { data: planning, error } = await supabase
      .from('Plannings')
      .update(req.body)
      .eq('ID', req.params.id)
      .select()
      .single();

    if (error) {
      throw error;
    }

    if (!planning) {
      return res.status(404).json({ error: 'Planning non trouvé' });
    }

    res.json(planning);
  } catch (error) {
    console.error('Erreur API:', error);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// POST - Valider un planning
router.post('/plannings/:id/valider', requireApiAuth, async (req, res) => {
  try {
    const { data: planning, error } = await supabase
      .from('Plannings')
      .update({
        EstValide: true,
        ValidePar: req.session.user.id,
        DateValidation: new Date().toISOString()
      })
      .eq('ID', req.params.id)
      .select()
      .single();

    if (error) {
      throw error;
    }

    if (!planning) {
      return res.status(404).json({ error: 'Planning non trouvé' });
    }

    res.json({ message: 'Planning validé avec succès', planning });
  } catch (error) {
    console.error('Erreur API:', error);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// GET - Obtenir toutes les désignations
router.get('/designations', requireApiAuth, async (req, res) => {
  try {
    const { data: designations, error } = await supabase
      .from('Designations')
      .select('ID, NomDesignation')
      .order('NomDesignation', { ascending: true });

    if (error) {
      throw error;
    }

    res.json(designations || []);
  } catch (error) {
    console.error('Erreur API designations:', error);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

module.exports = router;