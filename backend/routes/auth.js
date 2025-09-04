const express = require("express");
const bcrypt = require("bcrypt");
const router = express.Router();
const { supabase } = require("../supabaseClient");

// Middleware pour vérifier l'authentification
const requireAuth = (req, res, next) => {
  if (req.session.user) {
    next();
  } else {
    res.redirect("/login");
  }
};

// Page de connexion
router.get("/login", async (req, res) => {
  // Test de la connexion Supabase d'abord
  try {
    const { data, error } = await supabase.from('employes').select('count').limit(1);
    if (error) throw error;
    console.log("✅ Connexion Supabase établie pour /login");
  } catch (error) {
    console.log("⚠️ Erreur Supabase sur /login:", error.message);
    return res.send(`
      <!DOCTYPE html>
      <html lang="fr">
      <head>
          <meta charset="UTF-8">
          <title>Erreur base de données</title>
          <style>
              body { font-family: Arial, sans-serif; padding: 50px; text-align: center; }
              .container { max-width: 600px; margin: 0 auto; }
              .error { color: #dc3545; }
              .btn { display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 10px; }
          </style>
      </head>
      <body>
          <div class="container">
              <h1 class="error">⚠️ Erreur de connexion à la base de données</h1>
              <p>Impossible de se connecter à Supabase. Vérifiez que :</p>
              <ul style="text-align: left; max-width: 400px; margin: 20px auto;">
                  <li>Supabase est configuré correctement</li>
                  <li>Les variables d'environnement sont définies</li>
                  <li>La base de données est accessible</li>
              </ul>
              <p><strong>Erreur:</strong> ${error.message}</p>
              <button onclick="window.location.reload()" class="btn">🔄 Réessayer</button>
          </div>
      </body>
      </html>
    `);
  }

  // Si déjà connecté, rediriger vers dashboard
  if (req.session && req.session.user) {
    return res.redirect("/dashboard");
  }

  // Afficher le formulaire de connexion
  res.render("login", { error: null, message: req.query.message || null });
});

// Traitement de la connexion
router.post("/login", async (req, res) => {
  const { surnom, motDePasse } = req.body;
  console.log("🔐 Tentative de connexion pour:", surnom);
  console.log("🔍 Mot de passe reçu:", motDePasse);

  try {
    // Chercher l'employé avec toutes les informations nécessaires
    const { data: employe, error } = await supabase
      .from('employes')
      .select(`
        id,
        surnom,
        nom,
        prenom,
        motdepasse,
        baseid,
        Poste:postes(nomposte, niveaumenu),
        Base:bases(nom)
      `)
      .eq('surnom', surnom)
      .single();

    if (error && error.code !== 'PGRST116') {
      throw error;
    }

    console.log("🔍 Utilisateur trouvé en base:", employe ? "OUI" : "NON");

    if (employe) {
      console.log("🔍 Hash en base:", employe.motdepasse);
      console.log("🔍 Le hash commence par $2b$ ?", employe.motdepasse.startsWith("$2b$"));

      let passwordValid = false;

      // Vérifier si le mot de passe est hashé ou en clair
      if (employe.motdepasse.startsWith("$2b$")) {
        // Mot de passe hashé - utiliser bcrypt.compare
        passwordValid = await bcrypt.compare(motDePasse, employe.motdepasse);
        console.log("🔍 Vérification avec bcrypt:", passwordValid ? "VALIDE" : "INVALIDE");
      } else {
        // Mot de passe en clair - comparaison directe (temporaire)
        passwordValid = motDePasse === employe.motdepasse;
        console.log("🔍 Vérification en clair:", passwordValid ? "VALIDE" : "INVALIDE");

        if (passwordValid) {
          console.log("⚠️ ATTENTION: Mot de passe en clair détecté pour", surnom);
          console.log("💡 Recommandation: Hasher ce mot de passe");
        }
      }

      if (passwordValid) {
        console.log("✅ Connexion réussie pour:", surnom);

        req.session.user = {
          ID: employe.id,
          Surnom: employe.surnom,
          Nom: employe.nom,
          Prenom: employe.prenom,
          Poste: employe.Poste?.nomposte || "Non défini",
          niveauMenu: employe.Poste?.niveaumenu || 1,
          BaseID: employe.baseid,
          Base: employe.Base?.nom || "Base principale"
        };

        res.redirect("/dashboard");
      } else {
        console.log("❌ Mot de passe incorrect pour:", surnom);
        res.render("login", { error: "Identifiants incorrects" });
      }
    } else {
      console.log("❌ Utilisateur non trouvé:", surnom);
      res.render("login", { error: "Identifiants incorrects" });
    }
  } catch (error) {
    console.error("❌ Erreur lors de la connexion:", error);
    res.render("login", { error: "Erreur serveur" });
  }
});

// Route de déconnexion
router.get("/logout", (req, res) => {
  const user = req.session.user?.surnom || "Utilisateur";
  req.session.destroy();
  console.log("👋 Déconnexion de:", user);
  res.redirect("/login");
});

// Route utilitaire pour hasher les mots de passe existants
router.post("/admin/hash-passwords", requireAuth, async (req, res) => {
  try {
    console.log("🔧 Début du hashage des mots de passe en clair...");

    const { data: employes, error } = await supabase
      .from('employes')
      .select('id, surnom, motdepasse');

    if (error) throw error;

    let updated = 0;

    for (const employe of employes) {
      // Si le mot de passe ne commence pas par $2b$, il n'est pas hashé
      if (!employe.motdepasse.startsWith("$2b$")) {
        const hash = await bcrypt.hash(employe.motdepasse, 10);

        const { error: updateError } = await supabase
          .from('employes')
          .update({ motdepasse: hash })
          .eq('id', employe.id);

        if (updateError) {
          console.error(`❌ Erreur pour ${employe.surnom}:`, updateError);
          continue;
        }

        console.log(`✅ Mot de passe hashé pour: ${employe.surnom}`);
        updated++;
      }
    }

    console.log(`🔧 ${updated} mots de passe mis à jour`);
    res.json({ success: true, updated });
  } catch (error) {
    console.error("❌ Erreur lors du hashage:", error);
    res.status(500).json({ success: false, error: error.message });
  }
});

module.exports = { router, requireAuth };