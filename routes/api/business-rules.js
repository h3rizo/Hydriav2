const express = require('express');
const router = express.Router();
const db = require('../../models');

// Route pour récupérer une activité par ID
router.get('/activites/:id', async (req, res) => {
  try {
    const activite = await db.Activites.findByPk(req.params.id, {
      include: [{ model: db.TypesActivites, as: 'TypeActivite' }]
    });
    res.json(activite);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Route pour récupérer activités par poste
router.get('/activites/by-poste/:posteId', async (req, res) => {
  try {
    const activites = await db.Activites.findAll({
      include: [{
        model: db.ActivitesPostes,
        where: { PosteID: req.params.posteId }
      }]
    });
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
    const planning = await db.Plannings.findByPk(ID);
    if (!planning) {
      return res.status(404).json({ success: false, error: 'Planning non trouvé' });
    }
    
    // Préparer les données de mise à jour
    const updateData = {};
    if (Date) updateData.Date = Date;
    if (EmployeID) updateData.EmployeID = EmployeID;
    if (OuvrageID) updateData.OuvrageID = OuvrageID;
    if (ActiviteID) updateData.ActiviteID = ActiviteID;
    if (Remarque !== undefined) updateData.Remarque = Remarque;
    
    // Mettre à jour le planning
    await planning.update(updateData);
    
    console.log(`✅ Planning ${ID} mis à jour avec succès`);
    res.json({ success: true, message: 'Planning mis à jour avec succès' });
    
  } catch (error) {
    console.error('❌ Erreur lors de la mise à jour du planning:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Ajouter les autres routes nécessaires...

module.exports = router;