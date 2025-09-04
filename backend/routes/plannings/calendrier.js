const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

function requireAuth(req, res, next) {
  if (req.session && req.session.user) return next();
  return res.redirect('/login');
}

// Helper pour obtenir le premier et le dernier jour du mois
const getMonthBounds = (year, month) => {
  const startOfMonth = new Date(year, month, 1);
  const endOfMonth = new Date(year, month + 1, 0);
  endOfMonth.setHours(23, 59, 59, 999); // Inclure toute la journée
  return { startOfMonth, endOfMonth };
};

// GET: Affiche la vue calendrier
router.get('/', requireAuth, async (req, res) => {
  try {
    const today = new Date();
    const year = parseInt(req.query.year) || today.getFullYear();
    const month = req.query.month ? parseInt(req.query.month) - 1 : today.getMonth();

    const { startOfMonth, endOfMonth } = getMonthBounds(year, month);

    // Récupérer les plannings pour le mois sélectionné
    const { data: plannings, error } = await supabase
      .from('plannings')
      .select(`
                id,
                date,
                remarque,
                Employe:employes ( prenom, nom )
            `)
      .gte('date', startOfMonth.toISOString())
      .lte('date', endOfMonth.toISOString())
      .order('date', { ascending: true });

    if (error) throw error;

    // Organiser les plannings par jour
    const eventsByDay = {};
    plannings.forEach(p => {
      const day = new Date(p.date).getDate();
      if (!eventsByDay[day]) {
        eventsByDay[day] = [];
      }
      eventsByDay[day].push(p);
    });

    res.render('plannings/calendrier', {
      user: req.session.user,
      pageTitle: "Calendrier des plannings",
      year,
      month, // 0-indexed
      eventsByDay,
      error: null
    });

  } catch (error) {
    console.error("❌ Erreur lors du chargement du calendrier:", error);
    res.status(500).render('error', { user: req.session.user, message: `Erreur serveur: ${error.message}` });
  }
});

module.exports = router;