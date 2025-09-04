const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

function requireAuth(req, res, next) {
  if (req.session && req.session.user) return next();
  return res.redirect('/login');
}

// Page principale du suivi des avances
router.get('/', requireAuth, async (req, res) => {
  try {
    console.log('📊 Chargement page suivi des avances...');
    console.log('User session:', req.session.user);

    // Récupérer les statistiques des avances
    const [avancesEnCoursResult, avancesLivreesResult, totalAvancesResult] = await Promise.allSettled([
      supabase.from('planningsdetails').select('*', { count: 'exact', head: true }).eq('estlivre', false),
      supabase.from('planningsdetails').select('*', { count: 'exact', head: true }).eq('estlivre', true),
      supabase.from('planningsdetails').select('*', { count: 'exact', head: true })
    ]);

    const stats = {
      avances_en_cours: avancesEnCoursResult.status === 'fulfilled' ? (avancesEnCoursResult.value.count || 0) : 0,
      avances_livrees: avancesLivreesResult.status === 'fulfilled' ? (avancesLivreesResult.value.count || 0) : 0,
      total_avances: totalAvancesResult.status === 'fulfilled' ? (totalAvancesResult.value.count || 0) : 0
    };

    console.log('Stats:', stats);

    // Récupérer le détail des avances avec statut
    const { data: suiviAvances, error } = await supabase
      .from('planningsdetails')
      .select(`
        *,
        planning:plannings(
          *,
          employe:employes(id, nom, prenom),
          ouvrage:ouvrages(id, nom)
        ),
        designation:designations(id, nom),
        acheteur:employes(id, nom, prenom)
      `)
      .order('createdat', { ascending: false })
      .limit(50);

    if (error) {
      console.error('❌ Supabase error:', error);
      throw error;
    }

    console.log('Suivi avances data length:', suiviAvances ? suiviAvances.length : 0);

    res.render('plannings/suivi-avance', {
      pageTitle: 'Suivi des Avances',
      user: req.session.user,
      stats,
      suiviAvances: suiviAvances || []
    });

  } catch (error) {
    console.error('❌ Erreur suivi avances plannings:', error);
    // Log detailed error information
    const errorDetails = {
      message: error.message,
      stack: error.stack,
      name: error.name
    };
    
    res.status(500).render('error', {
      message: 'Erreur lors du chargement du suivi des avances',
      error: errorDetails,
      user: req.session ? req.session.user : null
    });
  }
});

module.exports = router;