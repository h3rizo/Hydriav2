const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

// GET: Affiche le formulaire de demande d'avance
router.get('/', async (req, res) => {
  try {
    const { data: employes, error } = await supabase
      .from('employes')
      .select('id, nom, prenom')
      .order('nom');

    if (error) throw error;

    res.render('plannings/avances', {
      user: req.session.user,
      pageTitle: "Demande d'avance sur salaire",
      employes,
      error: req.query.error,
      success: req.query.success,
      formData: {}
    });

  } catch (error) {
    console.error("❌ Erreur chargement page avances:", error);
    res.status(500).render('error', { user: req.session.user, message: `Erreur serveur: ${error.message}` });
  }
});

// POST: Traite la demande d'avance
router.post('/', async (req, res) => {
  const { employeid, montant, motif, date_avance } = req.body;

  try {
    if (!employeid || !montant || !motif || !date_avance) {
      throw new Error("Tous les champs sont obligatoires.");
    }

    const { data, error } = await supabase
      .from('avances') // Assurez-vous que cette table existe dans Supabase
      .insert([{
        employeid: parseInt(employeid),
        montant: parseFloat(montant),
        motif,
        date_demande: date_avance,
        statut: 'Demandée' // Statut par défaut
      }]);

    if (error) throw error;

    console.log('✅ Nouvelle avance enregistrée:', data);
    res.redirect('/plannings/avances?success=Demande d\'avance enregistrée avec succès !');

  } catch (error) {
    console.error("❌ Erreur lors de la création de l'avance:", error);
    // En cas d'erreur, rediriger vers le formulaire avec un message d'erreur
    res.redirect(`/plannings/avances?error=${encodeURIComponent(error.message)}`);
  }
});

module.exports = router;
