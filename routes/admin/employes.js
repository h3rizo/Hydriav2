// ========== routes/admin/employes.js ==========
const express = require('express');
const router = express.Router();
const bcrypt = require('bcrypt');
const db = require('../../models');

// Middleware pour vérifier les droits admin
function requireAdmin(req, res, next) {
  if (req.session && req.session.user && req.session.user.niveauMenu >= 4) {
    next();
  } else {
    res.status(403).render('error', {
      error: 'Accès non autorisé. Niveau administrateur requis.',
      user: req.session.user
    });
  }
}

// GET - Liste des employés
router.get('/admin/employes', requireAdmin, async (req, res) => {
  try {
    const [employes, postes, bases] = await Promise.all([
      db.Employes.findAll({
        include: [
          { model: db.Postes, as: 'Poste' },
          { model: db.Bases, as: 'Base' }
        ],
        order: [['Nom', 'ASC'], ['Prenom', 'ASC']]
      }),
      db.Postes.findAll({ order: [['NomPoste', 'ASC']] }),
      db.Bases.findAll({ order: [['Nom', 'ASC']] })
    ]);

    res.render('admin/employes', {
      pageTitle: 'Gestion des Employés',
      user: req.session.user,
      employes,
      postes,
      bases,
      message: req.query.message,
      error: req.query.error
    });
  } catch (error) {
    console.error('Erreur:', error);
    res.render('error', {
      error: 'Erreur lors du chargement des employés',
      user: req.session.user
    });
  }
});

// POST - Ajouter un employé
router.post('/admin/employes/add', requireAdmin, async (req, res) => {
  try {
    const { prenom, nom, surnom, motDePasse, posteID, baseID } = req.body;

    // Vérifier si le surnom existe déjà
    const existing = await db.Employes.findOne({ where: { Surnom: surnom } });
    if (existing) {
      return res.status(400).json({ error: 'Ce surnom est déjà utilisé' });
    }

    // Hasher le mot de passe
    const hashedPassword = await bcrypt.hash(motDePasse, 10);

    // Créer l'employé
    const employe = await db.Employes.create({
      Prenom: prenom,
      Nom: nom,
      Surnom: surnom,
      MotDePasse: hashedPassword,
      PosteID: posteID || null,
      BaseID: baseID || null,
      DateEmbauchage: new Date(),
      CreePar: req.session.user.id
    });

    res.json({ success: true, employe });
  } catch (error) {
    console.error('Erreur:', error);
    res.status(500).json({ error: 'Erreur lors de la création' });
  }
});

// GET - Réinitialiser le mot de passe
router.get('/admin/employes/reset-password/:id', requireAdmin, async (req, res) => {
  try {
    const employe = await db.Employes.findByPk(req.params.id);
    if (!employe) {
      return res.redirect('/admin/employes?error=Employé non trouvé');
    }

    // Nouveau mot de passe par défaut (surnom + 123)
    const newPassword = employe.Surnom + '123';
    const hashedPassword = await bcrypt.hash(newPassword, 10);

    await employe.update({ MotDePasse: hashedPassword });

    res.redirect(`/admin/employes?message=Mot de passe réinitialisé: ${newPassword}`);
  } catch (error) {
    console.error('Erreur:', error);
    res.redirect('/admin/employes?error=Erreur lors de la réinitialisation');
  }
});

// GET - Désactiver un employé
router.get('/admin/employes/deactivate/:id', requireAdmin, async (req, res) => {
  try {
    await db.Employes.update(
      { DateDebauchage: new Date() },
      { where: { ID: req.params.id } }
    );
    res.redirect('/admin/employes?message=Employé désactivé');
  } catch (error) {
    console.error('Erreur:', error);
    res.redirect('/admin/employes?error=Erreur lors de la désactivation');
  }
});

// GET - Réactiver un employé
router.get('/admin/employes/activate/:id', requireAdmin, async (req, res) => {
  try {
    await db.Employes.update(
      { DateDebauchage: null },
      { where: { ID: req.params.id } }
    );
    res.redirect('/admin/employes?message=Employé réactivé');
  } catch (error) {
    console.error('Erreur:', error);
    res.redirect('/admin/employes?error=Erreur lors de la réactivation');
  }
});

// GET - Exporter les employés en CSV
router.get('/admin/employes/export', requireAdmin, async (req, res) => {
  try {
    const employes = await db.Employes.findAll({
      include: [
        { model: db.Postes, as: 'Poste' },
        { model: db.Bases, as: 'Base' }
      ]
    });

    let csv = 'ID,Prénom,Nom,Surnom,Poste,Base,Date embauche,Statut\n';
    employes.forEach(emp => {
      csv += `${emp.ID},"${emp.Prenom}","${emp.Nom}","${emp.Surnom}",`;
      csv += `"${emp.Poste ? emp.Poste.NomPoste : ''}",`;
      csv += `"${emp.Base ? emp.Base.Nom : ''}",`;
      csv += `"${emp.DateEmbauchage || ''}",`;
      csv += `"${emp.DateDebauchage ? 'Inactif' : 'Actif'}"\n`;
    });

    res.setHeader('Content-Type', 'text/csv; charset=utf-8');
    res.setHeader('Content-Disposition', 'attachment; filename=employes.csv');
    res.send('\ufeff' + csv); // BOM pour Excel
  } catch (error) {
    console.error('Erreur:', error);
    res.redirect('/admin/employes?error=Erreur lors de l\'export');
  }
});

module.exports = router;