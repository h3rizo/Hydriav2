const express = require('express');
const router = express.Router();
const { supabase } = require('../../supabaseClient');

// Route pour récupérer une activité par ID
router.get('/activites/:id', async (req, res) => {
  try {
    const { data: activite, error } = await supabase
      .from('activites')
      .select(`
        *,
        TypeActivite:typesactivites(*)
      `)
      .eq('id', req.params.id)
      .single();

    if (error) throw error;

    res.json(activite);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Route pour récupérer activités par poste
router.get('/activites/by-poste/:posteId', async (req, res) => {
  try {
    const { data: activites, error } = await supabase
      .from('activites')
      .select(`
        *,
        ActivitesPostes:activitespostes!inner(posteid)
      `)
      .eq('ActivitesPostes.posteid', req.params.posteId);

    if (error) throw error;

    res.json(activites);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Route pour mettre à jour un planning
router.post('/plannings/update', async (req, res) => {
  try {
    const { ID, Date, EmployeID, OuvrageID, ActiviteID, Remarque } = req.body;

    // Validation des données
    if (!ID) {
      return res.status(400).json({ success: false, error: 'ID du planning requis' });
    }

    // Rechercher le planning existant
    const { data: planning, error: findError } = await supabase
      .from('plannings')
      .select('id')
      .eq('id', ID)
      .single();

    if (findError || !planning) {
      return res.status(404).json({ success: false, error: 'Planning non trouvé' });
    }

    // Préparer les données de mise à jour
    const updateData = {};
    if (Date) updateData.date = Date;
    if (EmployeID) updateData.employeid = EmployeID;
    if (OuvrageID) updateData.ouvrageid = OuvrageID;
    if (ActiviteID) updateData.activiteid = ActiviteID;
    if (Remarque !== undefined) updateData.remarque = Remarque;

    // Mettre à jour le planning
    const { error: updateError } = await supabase
      .from('plannings')
      .update(updateData)
      .eq('id', ID);

    if (updateError) throw updateError;

    console.log(`✅ Planning ${ID} mis à jour avec succès`);
    res.json({ success: true, message: 'Planning mis à jour avec succès' });

  } catch (error) {
    console.error('❌ Erreur lors de la mise à jour du planning:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Ajouter les autres routes nécessaires...

module.exports = router;