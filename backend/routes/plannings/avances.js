const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

function requireAuth(req, res, next) {
  if (req.session && req.session.user) return next();
  return res.redirect('/login');
}

// Page principale des avances
router.get('/', requireAuth, async (req, res) => {
  try {
    console.log('📋 Chargement page avances plannings...');

    // Récupérer les plannings avec avances depuis Supabase
    const { data: avances, error } = await supabase
      .from('PlanningsDetails')
      .select(`
        *,
        Planning:Plannings(
          *,
          Employe:Employes(ID, Nom, Prenom),
          Ouvrage:Ouvrages(ID, Nom),
          Activite:Activites(ID, Nom)
        ),
        Designation:Designations(ID, NomDesignation),
        Acheteur:Employes(ID, Nom, Prenom)
      `)
      .eq('EstLivre', false)
      .order('createdAt', { ascending: false });

    if (error) {
      throw error;
    }

    res.render('plannings/avances', {
      pageTitle: 'Plannings - Avances',
      user: req.session.user,
      avances: avances || []
    });

  } catch (error) {
    console.error('❌ Erreur avances plannings:', error);
    res.status(500).render('error', {
      message: 'Erreur lors du chargement des avances',
      error: error
    });
  }
});

module.exports = router;
