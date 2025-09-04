const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient'); // Remonter pour trouver le client supabase

function requireAuth(req, res, next) {
  if (req.session && req.session.user) return next();
  return res.redirect('/login');
}

// Affiche la page du rapport avec les filtres et les résultats
router.get('/', requireAuth, async (req, res) => {
  try {
    const { dateDebut, dateFin, employeId } = req.query;

    // 1. Récupérer la liste des employés pour le filtre
    const { data: employes, error: employesError } = await supabase
      .from('employes')
      .select('id, nom, prenom')
      .order('nom', { ascending: true });

    if (employesError) throw employesError;

    // 2. Construire la requête pour les plannings
    let query = supabase
      .from('plannings')
      .select(`
        id,
        date,
        remarque,
        estvalide,
        debitmesure,
        Employe:employes ( nom, prenom ),
        Ouvrage:ouvrages ( nom ),
        Activite:activites ( nom )
      `);

    // Appliquer les filtres s'ils sont fournis
    if (dateDebut) {
      query = query.gte('date', dateDebut);
    }
    if (dateFin) {
      // La date de fin doit inclure toute la journée
      const finJournee = new Date(dateFin);
      finJournee.setHours(23, 59, 59, 999);
      query = query.lte('date', finJournee.toISOString());
    }
    if (employeId) {
      query = query.eq('employeid', employeId);
    }

    // Exécuter la requête
    const { data: plannings, error: planningsError } = await query
      .order('date', { ascending: false });

    if (planningsError) throw planningsError;

    // 3. Rendre la vue avec les données
    res.render('plannings/rapport', {
      user: req.session.user,
      pageTitle: "Rapport d'activités",
      plannings: plannings || [],
      employes: employes || [],
      filters: req.query // Pour pré-remplir le formulaire
    });

  } catch (error) {
    console.error("❌ Erreur lors de la génération du rapport:", error);
    res.status(500).render('plannings/rapport', {
      user: req.session.user,
      pageTitle: "Rapport d'activités",
      plannings: [],
      employes: [],
      filters: {},
      error: `Erreur serveur: ${error.message}`
    });
  }
});

module.exports = router;
