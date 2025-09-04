const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

function requireAuth(req, res, next) {
  if (req.session && req.session.user) return next();
  return res.redirect('/login');
}

router.get('/livraison', requireAuth, async (req, res) => {
  try {
    // Récupérer les données de livraison depuis Supabase
    const { data: livraisons, error } = await supabase
      .from('PlanningsDetails')
      .select(`
        *,
        Planning:Plannings(
          *,
          Employe:Employes(ID, Nom, Prenom),
          Ouvrage:Ouvrages(ID, Nom)
        ),
        Designation:Designations(ID, NomDesignation)
      `)
      .eq('EstLivre', true)
      .order('createdAt', { ascending: false })
      .limit(100);

    if (error) {
      throw error;
    }

    res.render('plannings/livraison', {
      user: req.session.user,
      pageTitle: 'Plannings - Livraison',
      livraisons: livraisons || []
    });
  } catch (error) {
    console.error('❌ Erreur livraison:', error);
    res.status(500).render('error', {
      message: 'Erreur lors du chargement des livraisons',
      error: error
    });
  }
});

module.exports = router;