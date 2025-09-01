// Dans votre fichier de routes Express
app.post('/api/plannings/update', async (req, res) => {
  try {
    const { ID, Date, EmployeID, OuvrageID, ActiviteID, Remarque } = req.body;

    if (req.body.test === true) {
      return res.json({ success: true, message: 'Route fonctionnelle' });
    }

    // Votre logique de mise à jour en base de données ici
    // Exemple avec MySQL:
    const query = 'UPDATE planning SET Date=?, EmployeID=?, OuvrageID=?, ActiviteID=?, Remarque=? WHERE ID=?';
    const [result] = await db.execute(query, [Date, EmployeID, OuvrageID, ActiviteID, Remarque, ID]);

    res.json({ success: true, message: 'Planning mis à jour' });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});