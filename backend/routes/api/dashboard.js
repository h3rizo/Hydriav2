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

// GET - API endpoint pour les données du tableau de bord
router.get('/dashboard/stats', requireApiAuth, async (req, res) => {
  try {
    console.log('📊 API: Chargement des données du tableau de bord...');

    // Chargement des statistiques
    const [
      { count: ouvrages_actifs }, { count: points_eau_actifs }, { count: employes_actifs }, { count: bases_total },
      { count: villages_total }, { count: communes_total }, { count: districts_total }, { count: regions_total },
      { count: organisations_total }, { count: plannings_en_cours }, { count: plannings_valides },
      { count: cartes_sociales }, { count: gestionnaires_total }, { data: plannings_recents }
    ] = await Promise.all([
      supabase.from('ouvrages').select('*', { count: 'exact', head: true }),
      supabase.from('pointseau').select('*', { count: 'exact', head: true }),
      supabase.from('employes').select('*', { count: 'exact', head: true }).is('datedebauchage', null),
      supabase.from('bases').select('*', { count: 'exact', head: true }),
      supabase.from('villages').select('*', { count: 'exact', head: true }),
      supabase.from('communes').select('*', { count: 'exact', head: true }),
      supabase.from('districts').select('*', { count: 'exact', head: true }),
      supabase.from('regions').select('*', { count: 'exact', head: true }),
      supabase.from('organisations').select('*', { count: 'exact', head: true }),
      supabase.from('plannings').select('*', { count: 'exact', head: true }).eq('estvalide', false),
      supabase.from('plannings').select('*', { count: 'exact', head: true }).eq('estvalide', true),
      supabase.from('cartessociales').select('*', { count: 'exact', head: true }),
      supabase.from('gestionnaires').select('*', { count: 'exact', head: true }),
      supabase.from('plannings').select(`
        id, date, remarque, estvalide,
        Employe:employes ( nom, prenom ),
        Activite:activites ( nom )
      `).limit(5).order('date', { ascending: false })
    ]);

    const stats = {
      ouvrages_actifs, points_eau_actifs, employes_actifs, bases_total,
      villages_total, communes_total, districts_total, regions_total,
      organisations_total, plannings_en_cours, plannings_valides,
      cartes_sociales, cartes_sociales_actives: cartes_sociales,
      gestionnaires_total
    };

    res.json({
      success: true,
      stats,
      plannings_recents: plannings_recents || []
    });

  } catch (error) {
    console.error('❌ Erreur dashboard API:', error);
    res.status(500).json({ 
      success: false, 
      message: 'Erreur serveur lors de la récupération des données du tableau de bord.', 
      error: error.message 
    });
  }
});

// Route de test simple
router.get('/test', (req, res) => {
  res.json({ 
    success: true, 
    message: 'API accessible', 
    timestamp: new Date().toISOString() 
  });
});

// Route pour React Dashboard - format simplifié (temporairement sans auth pour debug)
router.get('/dashboard', async (req, res) => {
  try {
    console.log('📊 API React Dashboard: Chargement des données...');

    // Statistiques de base
    const [employesResult, ouvragesResult, planningsResult] = await Promise.all([
      supabase.from('employes').select('*', { count: 'exact', head: true }),
      supabase.from('ouvrages').select('*', { count: 'exact', head: true }),
      supabase.from('plannings').select('*', { count: 'exact', head: true })
    ]);

    const stats = {
      employes: employesResult.count || 0,
      ouvrages: ouvragesResult.count || 0,
      plannings: planningsResult.count || 0
    };

    // Données pour le graphique (derniers 6 mois)
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);

    const { data: recentPlannings } = await supabase
      .from('plannings')
      .select('dateplanning')
      .gte('dateplanning', sixMonthsAgo.toISOString())
      .not('dateplanning', 'is', null);

    // Grouper par mois
    const monthlyData = {};
    if (recentPlannings) {
      recentPlannings.forEach(p => {
        if (p.dateplanning) {
          const date = new Date(p.dateplanning);
          const monthKey = date.toLocaleDateString('fr-FR', { month: 'short', year: 'numeric' });
          monthlyData[monthKey] = (monthlyData[monthKey] || 0) + 1;
        }
      });
    }

    const chartData = {
      labels: Object.keys(monthlyData),
      data: Object.values(monthlyData)
    };

    res.json({
      success: true,
      stats,
      chartData
    });

  } catch (error) {
    console.error('❌ Erreur React Dashboard API:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Erreur lors du chargement du dashboard'
    });
  }
});

module.exports = router;