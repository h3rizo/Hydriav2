const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

// GET: Affiche la liste de toutes les demandes d'avance
router.get('/', async (req, res) => {
  try {
    const { data: avances, error } = await supabase
      .from('avances')
      .select(`
                *,
                employes ( nom, prenom )
            `)
      .order('date_demande', { ascending: false });

    if (error) throw error;

    res.render('plannings/suivi-avance', {
      user: req.session.user,
      pageTitle: "Suivi des demandes d'avance",
      avances,
      error: req.query.error,
      success: req.query.success
    });

  } catch (error) {
    console.error("❌ Erreur chargement page suivi des avances:", error);
    res.status(500).render('error', { user: req.session.user, message: `Erreur serveur: ${error.message}` });
  }
});

// POST: Met à jour le statut d'une avance (Approuver/Rejeter)
router.post('/:id/update-status', async (req, res) => {
  const { id } = req.params;
  const { statut } = req.body;

  try {
    const { error } = await supabase
      .from('avances')
      .update({ statut, date_decision: new Date() })
      .eq('id', id);

    if (error) throw error;

    res.redirect('/plannings/suivi-avance?success=Statut mis à jour avec succès.');
  } catch (error) {
    console.error(`❌ Erreur mise à jour statut avance #${id}:`, error);
    res.redirect(`/plannings/suivi-avance?error=${encodeURIComponent(error.message)}`);
  }
});

module.exports = router;