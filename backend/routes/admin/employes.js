// ========== routes/admin/employes.js ==========
const express = require('express');
const router = express.Router();
const bcrypt = require('bcrypt');
const { supabase } = require('../../supabaseClient');

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
    const [employesResult, postesResult, basesResult] = await Promise.allSettled([
      supabase
        .from('employes')
        .select(`
          *,
          Poste:postes(id, nomposte),
          Base:bases(id, nom)
        `)
        .order('nom', { ascending: true })
        .order('prenom', { ascending: true }),
      supabase
        .from('postes')
        .select('*')
        .order('nomposte', { ascending: true }),
      supabase
        .from('bases')
        .select('*')
        .order('nom', { ascending: true })
    ]);

    const employes = employesResult.status === 'fulfilled' ? employesResult.value.data || [] : [];
    const postes = postesResult.status === 'fulfilled' ? postesResult.value.data || [] : [];
    const bases = basesResult.status === 'fulfilled' ? basesResult.value.data || [] : [];

    if (employesResult.status === 'rejected') {
      console.error('Erreur employes:', employesResult.reason);
    }
    if (postesResult.status === 'rejected') {
      console.error('Erreur postes:', postesResult.reason);
    }
    if (basesResult.status === 'rejected') {
      console.error('Erreur bases:', basesResult.reason);
    }

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
    const { data: existing, error: checkError } = await supabase
      .from('employes')
      .select('id')
      .eq('surnom', surnom)
      .single();

    if (checkError && checkError.code !== 'PGRST116') { // PGRST116 = pas de résultats
      throw checkError;
    }

    if (existing) {
      return res.status(400).json({ error: 'Ce surnom est déjà utilisé' });
    }

    // Hasher le mot de passe
    const hashedPassword = await bcrypt.hash(motDePasse, 10);

    // Créer l'employé
    const { data: employe, error } = await supabase
      .from('employes')
      .insert({
        prenom: prenom,
        nom: nom,
        surnom: surnom,
        motdepasse: hashedPassword,
        posteid: posteID || null,
        baseid: baseID || null,
        dateembauchage: new Date().toISOString(),
        creepar: req.session.user.ID
      })
      .select()
      .single();

    if (error) throw error;

    res.json({ success: true, employe });
  } catch (error) {
    console.error('Erreur:', error);
    res.status(500).json({ error: 'Erreur lors de la création' });
  }
});

// GET - Réinitialiser le mot de passe
router.get('/admin/employes/reset-password/:id', requireAdmin, async (req, res) => {
  try {
    const { data: employe, error } = await supabase
      .from('employes')
      .select('id, surnom')
      .eq('id', req.params.id)
      .single();

    if (error || !employe) {
      return res.redirect('/admin/employes?error=Employé non trouvé');
    }

    // Nouveau mot de passe par défaut (surnom + 123)
    const newPassword = employe.surnom + '123';
    const hashedPassword = await bcrypt.hash(newPassword, 10);

    const { error: updateError } = await supabase
      .from('employes')
      .update({ motdepasse: hashedPassword })
      .eq('id', req.params.id);

    if (updateError) throw updateError;

    res.redirect(`/admin/employes?message=Mot de passe réinitialisé: ${newPassword}`);
  } catch (error) {
    console.error('Erreur:', error);
    res.redirect('/admin/employes?error=Erreur lors de la réinitialisation');
  }
});

// GET - Désactiver un employé
router.get('/admin/employes/deactivate/:id', requireAdmin, async (req, res) => {
  try {
    const { error } = await supabase
      .from('employes')
      .update({ datedebauchage: new Date().toISOString() })
      .eq('id', req.params.id);

    if (error) throw error;

    res.redirect('/admin/employes?message=Employé désactivé');
  } catch (error) {
    console.error('Erreur:', error);
    res.redirect('/admin/employes?error=Erreur lors de la désactivation');
  }
});

// GET - Réactiver un employé
router.get('/admin/employes/activate/:id', requireAdmin, async (req, res) => {
  try {
    const { error } = await supabase
      .from('employes')
      .update({ datedebauchage: null })
      .eq('id', req.params.id);

    if (error) throw error;

    res.redirect('/admin/employes?message=Employé réactivé');
  } catch (error) {
    console.error('Erreur:', error);
    res.redirect('/admin/employes?error=Erreur lors de la réactivation');
  }
});

// GET - Exporter les employés en CSV
router.get('/admin/employes/export', requireAdmin, async (req, res) => {
  try {
    const { data: employes, error } = await supabase
      .from('employes')
      .select(`
        id,
        prenom,
        nom,
        surnom,
        dateembauchage,
        datedebauchage,
        Poste:postes(nomposte),
        Base:bases(nom)
      `);

    if (error) throw error;

    let csv = 'ID,Prénom,Nom,Surnom,Poste,Base,Date embauche,Statut\n';
    (employes || []).forEach(emp => {
      csv += `${emp.id},"${emp.prenom}","${emp.nom}","${emp.surnom}",`;
      csv += `"${emp.Poste ? emp.Poste.nomposte : ''}",`;
      csv += `"${emp.Base ? emp.Base.nom : ''}",`;
      csv += `"${emp.dateembauchage || ''}",`;
      csv += `"${emp.datedebauchage ? 'Inactif' : 'Actif'}"\n`;
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