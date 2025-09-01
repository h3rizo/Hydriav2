const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

// GET: Affiche la page de détails d'un planning
router.get('/:id/details', async (req, res) => {
  const { id } = req.params;
  try {
    // Récupérer le planning principal et ses détails en une seule requête
    const { data: planning, error } = await supabase
      .from('plannings')
      .select(`
                *,
                Employe:employes ( nom, prenom ),
                Ouvrage:ouvrages ( nom ),
                Activite:activites ( nom ),
                planningsdetails ( bilan, suiteadonner )
            `)
      .eq('id', id)
      .single();

    if (error) throw error;

    if (!planning) {
      return res.status(404).render('error', { user: req.session.user, message: "Planning introuvable" });
    }

    // Les détails sont dans un tableau, même s'il n'y a qu'un seul résultat
    const details = planning.planningsdetails[0] || {};

    res.render('plannings/details', {
      user: req.session.user,
      pageTitle: `Détails du planning #${planning.id}`,
      planning,
      details,
      error: req.query.error,
      success: req.query.success
    });

  } catch (error) {
    console.error(`❌ Erreur lors du chargement des détails du planning #${id}:`, error);
    res.status(500).render('error', { user: req.session.user, message: `Erreur serveur: ${error.message}` });
  }
});

// POST: Met à jour les détails (Bilan, Suite à donner)
router.post('/:id/details', async (req, res) => {
  const { id } = req.params;
  const { bilan, suiteadonner } = req.body;

  try {
    // Utiliser upsert pour créer/mettre à jour les détails.
    const { error } = await supabase
      .from('planningsdetails')
      .upsert({ planningid: parseInt(id), bilan, suiteadonner }, { onConflict: 'planningid' });

    if (error) throw error;

    console.log(`✅ Détails du planning #${id} mis à jour avec succès.`);
    res.redirect(`/plannings/${id}/details?success=Détails enregistrés avec succès !`);

  } catch (error) {
    console.error(`❌ Erreur lors de la mise à jour des détails du planning #${id}:`, error);
    res.redirect(`/plannings/${id}/details?error=${encodeURIComponent(error.message)}`);
  }
});

module.exports = router;