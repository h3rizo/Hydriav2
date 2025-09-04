const express = require('express');
const router = express.Router();
const { supabase } = require('../../../supabaseClient');

// Route pour mettre à jour un planning
router.post('/update', async (req, res) => {
  try {
    const { ID, Date, EmployeID, OuvrageID, ActiviteID, Remarque } = req.body;

    if (req.body.test === true) {
      return res.json({ success: true, message: 'Route fonctionnelle' });
    }

    // Validation des données
    if (!ID) {
      return res.status(400).json({ success: false, error: 'ID du planning requis' });
    }

    // Préparer les données de mise à jour
    const updateData = {};
    if (Date) updateData.date = Date;
    if (EmployeID) updateData.employeid = EmployeID;
    if (OuvrageID) updateData.ouvrageid = OuvrageID;
    if (ActiviteID) updateData.activiteid = ActiviteID;
    if (Remarque !== undefined) updateData.remarque = Remarque;

    // Mettre à jour le planning
    const { error } = await supabase
      .from('plannings')
      .update(updateData)
      .eq('id', ID);

    if (error) throw error;

    res.json({ success: true, message: 'Planning mis à jour' });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

module.exports = router;