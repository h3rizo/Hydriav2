const express = require('express');
const router = express.Router();
const { supabase } = require('../supabaseClient');

function requireAuth(req, res, next) {
  if (req.session && req.session.user) return next();
  // Pour une API, on renvoie une erreur 401 Unauthorized au lieu de rediriger
  return res.status(401).json({ success: false, message: 'Authentification requise.' });
}

router.get('/api/dashboard', requireAuth, async (req, res) => {
  try {
    console.log('📊 API: Chargement des données du dashboard...');

    // 1. Récupérer les statistiques générales (employés, ouvrages, etc.)
    const [employesCount, ouvragesCount, planningsCount] = await Promise.all([
      supabase.from('employes').select('*', { count: 'exact', head: true }),
      supabase.from('ouvrages').select('*', { count: 'exact', head: true }),
      supabase.from('plannings').select('*', { count: 'exact', head: true })
    ]);

    const stats = {
      employes: employesCount.count || 0,
      ouvrages: ouvragesCount.count || 0,
      plannings: planningsCount.count || 0,
    };

    // 2. Récupérer les données pour le graphique (ex: plannings des 6 derniers mois)
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);

    const { data: recentPlannings, error: planningsError } = await supabase
      .from('plannings')
      .select('date')
      .gte('date', sixMonthsAgo.toISOString());

    if (planningsError) throw planningsError;

    // 3. Agréger les données par mois pour le graphique
    const planningsByMonth = recentPlannings.reduce((acc, planning) => {
      const month = new Date(planning.date).toLocaleString('fr-FR', { month: 'long', year: 'numeric' });
      acc[month] = (acc[month] || 0) + 1;
      return acc;
    }, {});

    // Formatter pour Chart.js
    const chartData = {
      labels: Object.keys(planningsByMonth),
      data: Object.values(planningsByMonth),
    };

    res.json({
      success: true,
      stats,
      chartData,
    });

  } catch (error) {
    console.error('❌ Erreur API Dashboard:', error);
    res.status(500).json({ success: false, message: 'Erreur serveur lors de la récupération des données du dashboard.', error: error.message });
  }
});

module.exports = router;