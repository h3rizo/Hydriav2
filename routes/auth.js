const express = require("express");
const bcrypt = require("bcrypt");
const router = express.Router();

module.exports = (db) => {
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
    // Vérifier d'abord si l'objet db est valide
    if (!db || !db.sequelize) {
      console.log("⚠️ db.sequelize non défini sur /login");
      return res.send(`
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <title>Erreur de configuration</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 50px; text-align: center; }
                .container { max-width: 600px; margin: 0 auto; }
                .error { color: #dc3545; }
                .btn { display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 10px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="error">⚠️ Erreur de configuration de la base de données</h1>
                <p>Les modèles de base de données ne sont pas chargés correctement.</p>
                <p><strong>Actions à effectuer :</strong></p>
                <ol style="text-align: left; max-width: 400px; margin: 20px auto;">
                    <li>Redémarrer le serveur</li>
                    <li>Vérifier que MySQL est démarré</li>
                    <li>Vérifier models/index.js</li>
                </ol>
                <a href="/setup-database" class="btn">Initialiser la base</a>
                <button onclick="window.location.reload()" class="btn">🔄 Réessayer</button>
            </div>
        </body>
        </html>
      `);
    }

    // Test de la connexion DB d'abord
    try {
      await db.sequelize.authenticate();
      console.log("✅ Connexion DB établie pour /login");
    } catch (error) {
      console.log("⚠️ Erreur DB sur /login:", error.message);
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
                <p>Impossible de se connecter à MySQL. Vérifiez que :</p>
                <ul style="text-align: left; max-width: 400px; margin: 20px auto;">
                    <li>MySQL/MariaDB est démarré</li>
                    <li>Le port 3307 est disponible</li>
                    <li>La base 'hydriav2_clean' existe</li>
                    <li>L'utilisateur 'root' a accès</li>
                </ul>
                <p><strong>Erreur:</strong> ${error.message}</p>
                <a href="/setup-database" class="btn">Initialiser la base</a>
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
      const employe = await db.Employes.findOne({
        where: { Surnom: surnom },
        include: [
          { model: db.Postes, as: "Poste" },
          { model: db.Bases, as: "Base" }
        ]
      });

      console.log("🔍 Utilisateur trouvé en base:", employe ? "OUI" : "NON");

      if (employe) {
        console.log("🔍 Hash en base:", employe.MotDePasse);
        console.log("🔍 Le hash commence par $2b$ ?", employe.MotDePasse.startsWith("$2b$"));

        let passwordValid = false;

        // Vérifier si le mot de passe est hashé ou en clair
        if (employe.MotDePasse.startsWith("$2b$")) {
          // Mot de passe hashé - utiliser bcrypt.compare
          passwordValid = await bcrypt.compare(motDePasse, employe.MotDePasse);
          console.log("🔍 Vérification avec bcrypt:", passwordValid ? "VALIDE" : "INVALIDE");
        } else {
          // Mot de passe en clair - comparaison directe (temporaire)
          passwordValid = motDePasse === employe.MotDePasse;
          console.log("🔍 Vérification en clair:", passwordValid ? "VALIDE" : "INVALIDE");

          if (passwordValid) {
            console.log("⚠️ ATTENTION: Mot de passe en clair détecté pour", surnom);
            console.log("💡 Recommandation: Hasher ce mot de passe");
          }
        }

        if (passwordValid) {
          console.log("✅ Connexion réussie pour:", surnom);

          req.session.user = {
            ID: employe.ID,
            Surnom: employe.Surnom,
            Nom: employe.Nom,
            Prenom: employe.Prenom,
            Poste: employe.Poste?.NomPoste || "Non défini",
            niveauMenu: employe.Poste?.NiveauMenu || 1,
            BaseID: employe.BaseID,
            Base: employe.Base?.Nom || "Base principale"
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

      const employes = await db.Employes.findAll();
      let updated = 0;

      for (const employe of employes) {
        // Si le mot de passe ne commence pas par $2b$, il n'est pas hashé
        if (!employe.MotDePasse.startsWith("$2b$")) {
          const hash = await bcrypt.hash(employe.MotDePasse, 10);
          await employe.update({ MotDePasse: hash });
          console.log(`✅ Mot de passe hashé pour: ${employe.Surnom}`);
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

  return { router, requireAuth };
};
