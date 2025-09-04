const express = require("express");
const session = require("express-session");
const bodyParser = require("body-parser");
const path = require("path");
const bcrypt = require("bcrypt");
require("dotenv").config();

// Import the Supabase client
const { supabase } = require('./supabaseClient.js');

// Variable to track database status
let isDatabaseReady = false;

async function ensureDatabaseReady() {
  if (!isDatabaseReady) {
    try {
      // Test the connection to Supabase by fetching a small amount of data
      // CORRIGÉ : 'id' doit être en minuscules
      const { error } = await supabase.from('employes').select('id').limit(1);
      if (error) throw error;
      isDatabaseReady = true;
      console.log("✅ Database ready for use");
    } catch (dbError) {
      console.error("❌ Supabase connection failed:", dbError.message);
      isDatabaseReady = false; // Keep it false
      throw dbError;
    }
  }
}

const app = express();

const PORT = process.env.APP_PORT || 3001;

// =============================================
// CONFIGURATION DE BASE
// =============================================

app.use(
  session({
    secret: "soakoja-secret-2024",
    resave: false,
    saveUninitialized: false,
    cookie: { maxAge: 24 * 60 * 60 * 1000 }
  })
);

app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json());
app.use(express.static(path.join(__dirname, "public")));
app.use(express.static(path.join(__dirname, "../frontend/dist")));
app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));

// =============================================
// MIDDLEWARE D'AUTHENTIFICATION AMÉLIORÉ
// =============================================

function requireAuth(req, res, next) {
  // Si la base de données n'est pas initialisée, rediriger vers setup
  if (!isDatabaseReady) {
    console.log("🔒 Base de données non initialisée - redirection vers /setup-database");
    return res.redirect("/setup-database");
  }

  if (req.session && req.session.user && req.session.user.id) {
    next();
  } else {
    console.log("🔒 Accès refusé - redirection vers login");
    res.redirect("/login");
  }
}

// =============================================
// Fonction utilitaire pour compter les enregistrements avec Supabase
const safeCount = async (tableName, options = {}) => {
  try {
    // Supabase count requires a filter, but we can use a dummy one to count all
    const { count, error } = await supabase.from(tableName).select('*', { count: 'exact', head: true });
    if (error) {
      throw error;
    }
    return count || 0;
  } catch (error) {
    console.warn(`⚠️ Impossible de compter les ${tableName}: ${error.message}`);
    return 0;
  }
};

// =============================================
// ROUTES PERSONNALISÉES (conditionnelles)
// =============================================

try {
  const saisieRoutes = require('./routes/plannings/saisie');
  app.use('/plannings', saisieRoutes);
  console.log("✅ Routes plannings/saisie chargées");
} catch (error) {
  console.log(`⚠️ Routes plannings/saisie non trouvées. Erreur: ${error.message}`);
}

try {
  const livraisonRoutes = require('./routes/plannings/livraison');
  app.use('/plannings', livraisonRoutes);
  console.log("✅ Routes plannings/livraison chargées");
} catch (error) {
  console.log(`⚠️ Routes plannings/livraison non trouvées. Erreur: ${error.message}`);
}

try {
  const avancesRoutes = require('./routes/plannings/avances');
  app.use('/plannings/avances', avancesRoutes);
  console.log("✅ Routes plannings/avances chargées");
} catch (error) {
  console.log(`⚠️ Routes plannings/avances non trouvées. Erreur: ${error.message}`);
}

try {
  const suiviAvanceRoutes = require('./routes/plannings/suivi-avance');
  app.use('/plannings/suivi-avance', suiviAvanceRoutes);
  console.log("✅ Routes plannings/suivi-avance chargées");
} catch (error) {
  console.log(`⚠️ Routes plannings/suivi-avance non trouvées. Erreur: ${error.message}`);
}

// React API Routes (loaded first to take precedence)
try {
  const reactRoutes = require('./routes/api/react-routes');
  app.use('/api', reactRoutes);
  console.log("✅ Routes API React chargées avec endpoints /api/react/suivi-avances et /api/react/kanban");
} catch (error) {
  console.log(`⚠️ Routes API React non trouvées. Erreur: ${error.message}`);
}

try {
  const apiRoutes = require('./routes/plannings/api');
  app.use('/api', apiRoutes);
  console.log("✅ Routes API chargées");
} catch (error) {
  console.log(`⚠️ Routes API non trouvées. Erreur: ${error.message}`);
}

// New Planning views
try {
  const kanbanRoutes = require('./routes/plannings/kanban');
  app.use('/plannings/kanban', requireAuth, kanbanRoutes);
  console.log("✅ Routes plannings/kanban chargées");
} catch (error) {
  console.log(`⚠️ Routes plannings/kanban non trouvées. Erreur: ${error.message}`);
}

try {
  const calendrierRoutes = require('./routes/plannings/calendrier');
  app.use('/plannings/calendrier', calendrierRoutes);
  console.log("✅ Routes plannings/calendrier chargées");
} catch (error) {
  console.log(`⚠️ Routes plannings/calendrier non trouvées. Erreur: ${error.message}`);
}

try {
  const rapportRoutes = require('./routes/plannings/rapport');
  app.use('/plannings/rapport', requireAuth, rapportRoutes);
  console.log("✅ Routes plannings/rapport chargées");
} catch (error) {
  console.log(`⚠️ Routes plannings/rapport non trouvées. Erreur: ${error.message}`);
}

// Details update endpoints
try {
  const detailsRoutes = require('./routes/plannings/details');
  app.use('/plannings', requireAuth, detailsRoutes);
  console.log("✅ Routes plannings/details chargées");
} catch (error) {
  console.log(`⚠️ Routes plannings/details non trouvées, la page de détails ne fonctionnera pas. Erreur: ${error.message}`);
}

// Admin routes
try {
  const adminEmployesRoutes = require('./routes/admin/employes');
  app.use('/', adminEmployesRoutes);
  console.log("✅ Routes admin/employes chargées");
} catch (error) {
  console.log(`⚠️ Routes admin/employes non trouvées. Erreur: ${error.message}`);
}

// Business rules API
try {
  const businessRulesRoutes = require('./routes/api/business-rules');
  app.use('/api', businessRulesRoutes);
  console.log("✅ Routes API business-rules chargées");
} catch (error) {
  console.log(`⚠️ Routes API business-rules non trouvées. Erreur: ${error.message}`);
}

// Dashboard API
try {
  const dashboardRoutes = require('./routes/api/dashboard');
  app.use('/api', dashboardRoutes);
  console.log("✅ Routes API dashboard chargées");
} catch (error) {
  console.log(`⚠️ Routes API dashboard non trouvées. Erreur: ${error.message}`);
}


// =============================================
// ROUTES PRINCIPALES
// =============================================

// Route principale avec gestion améliorée
app.get("/", (req, res) => {
  // Si la base n'est pas initialisée, aller à setup
  if (!isDatabaseReady) {
    return res.redirect("/setup-database");
  }

  // Si connecté, aller au dashboard
  if (req.session && req.session.user) {
    return res.redirect("/dashboard");
  }

  // Sinon, aller à login
  res.redirect("/login");
});

// Page de connexion
app.get("/login", async (req, res) => {
  console.log("📱 Serving login page...");

  // Try to initialize database in background if not ready
  if (!isDatabaseReady) {
    ensureDatabaseReady().catch(err =>
      console.log("Background DB init failed:", err.message)
    );
  }

  // Si déjà connecté, rediriger vers dashboard
  if (req.session && req.session.user) {
    return res.redirect("/dashboard");
  }

  res.render("login", {
    error: null,
    message: req.query.message || (isDatabaseReady ? null : "Database initializing in background...")
  });
});

// POST login avec authentification réelle
app.post("/login", async (req, res) => {
  // On utilise le Surnom et MotDePasse comme demandé
  const { surnom, motDePasse } = req.body;
  console.log(`🔍 Login attempt with Surnom: ${surnom}`);

  try {
    await ensureDatabaseReady();

    // 1. Chercher l'employé par son Surnom
    const { data: employe, error: employeError } = await supabase
      .from('employes')
      .select(`
        id, surnom, nom, prenom, baseid, motdepasse,
        Poste:postes ( nomposte, niveaumenu ),
        Base:bases ( nom, Organisation:organisations ( nom ) )
      `)
      .eq('surnom', surnom)
      .single();

    if (employeError || !employe) {
      console.log(`❌ User not found: ${surnom}`, employeError?.message);
      return res.render("login", { error: "Surnom ou mot de passe incorrect", message: null });
    }

    // 2. Vérifier le mot de passe avec bcrypt
    const passwordValid = await bcrypt.compare(motDePasse, employe.motdepasse);

    if (passwordValid) {
      console.log(`✅ Login successful for: ${surnom}`);

      // Stocker les informations de l'utilisateur dans la session
      req.session.user = {
        id: employe.id,
        surnom: employe.surnom,
        nom: employe.nom,
        prenom: employe.prenom,
        poste: employe.Poste?.nomposte || "Non défini",
        niveauMenu: employe.Poste?.niveaumenu || 1,
        baseID: employe.baseid,
        baseName: employe.Base?.nom || "Base inconnue",
        organisationName: employe.Base?.Organisation?.nom || "Organisation inconnue"
      };

      console.log(`🎯 Session created for user: ${req.session.user.surnom} (ID: ${req.session.user.id})`);

      // Sauvegarder la session avant de rediriger
      req.session.save((err) => {
        if (err) {
          console.error(`❌ Session save error:`, err);
          return res.render("login", {
            error: "Erreur de session, veuillez réessayer",
            message: null
          });
        }
        console.log(`✅ Session saved successfully - redirecting to dashboard`);
        res.redirect("/dashboard");
      });
    } else {
      console.log(`❌ Invalid password for: ${surnom}`);
      res.render("login", { error: "Surnom ou mot de passe incorrect", message: null });
    }

  } catch (error) {
    console.error("❌ Login error:", error.message);
    res.render("login", {
      error: `Database error: ${error.message}`,
      message: null
    });
  }
});

// Logout
app.get("/logout", (req, res) => {
  const user = req.session?.user?.surnom || "Unknown";
  req.session.destroy();
  console.log(`👋 Logout: ${user}`);
  res.redirect("/login?message=Logged out successfully");
});

// Simple test route to verify server is working
app.get("/test", (req, res) => {
  res.send(`
    <h1>✅ Server is working!</h1>
    <p>Database initialized: ${isDatabaseInitialized}</p>
    <p>Models loaded: ${modelsLoaded}</p>
    <p>Time: ${new Date().toISOString()}</p>
    <a href="/login">Go to login</a>
    <br><a href="/login-fallback">Go to fallback login (no DB)</a>
  `);
});

// Fallback login page without database
app.get("/login-fallback", (req, res) => {
  res.render("login", {
    error: null,
    message: "Fallback login page (database disabled for testing)"
  });
});

// Dashboard - Serve React frontend
app.get("/dashboard", requireAuth, (req, res) => {
  console.log(`📱 Serving React dashboard for: ${req.session.user.surnom}`);
  
  // Serve the React frontend app
  res.sendFile(path.join(__dirname, '../frontend/dist/index.html'));
});

// Route pour initialiser manuellement la base
app.get("/setup-database", async (req, res) => {
  console.log("🔧 Page de vérification de la connexion Supabase...");

  if (isDatabaseReady) {
    return res.send(`
    <!DOCTYPE html>
      <html lang="fr">
        <head>
          <meta charset="UTF-8">
            <title>Base de données déjà initialisée</title>
            <style>
              body {font-family: Arial, sans-serif; padding: 50px;}
              .container {max-width: 800px; margin: 0 auto;}
              .success {color: green;}
              .btn {display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 10px 5px;}
              .btn:hover {background: #0056b3;}
              ul {text-align: left;}
            </style>
        </head>
        <body>
          <div class="container">
            <h1 class="success">✅ Connexion à Supabase réussie !</h1>
            <p>La connexion à la base de données Supabase est fonctionnelle.</p>
            <div>
              <a href="/login" class="btn">🔐 Page de connexion</a>
              <a href="/" class="btn">🏠 Accueil</a>
            </div>
          </div>
        </body>
      </html>
    `);
  }

  // Tentative d'initialisation
  const success = await ensureDatabaseReady().catch(() => false);

  if (success) {
    res.send(`
    <!DOCTYPE html>
      <html lang="fr">
        <head>
          <meta charset="UTF-8">
            <title>Initialisation réussie</title>
            <style>
              body {font-family: Arial, sans-serif; padding: 50px;}
              .container {max-width: 800px; margin: 0 auto;}
              .success {color: green;}
              .info {background: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0;}
              .btn {display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 10px 5px;}
              .btn:hover {background: #0056b3;}
              ul {text-align: left;}
            </style>
        </head>
        <body>
          <div class="container">
            <h1 class="success">✅ Connexion à Supabase établie avec succès !</h1>
            <div class="info">
              <h3>Étapes suivantes:</h3>
              <ol>
                <li>Assurez-vous que vos tables sont créées dans le tableau de bord Supabase.</li>
                <li>Utilisez le script <code>import-csv.js</code> pour importer vos données.</li>
              </ol>
            </div>
            <h3>Comptes de test (après import):</h3>
            <ul>
              <li><strong>Tsilavina</strong> / IA</li>
              <li><strong>admin</strong> / admin</li>
            </ul>
            <div>
              <a href="/login" class="btn">🔐 Aller à la page de connexion</a>
              <a href="/" class="btn">🏠 Retour à l'accueil</a>
            </div>
          </div>
        </body>
      </html>
    `);
  } else {
    res.send(`
    <!DOCTYPE html>
      <html lang="fr">
        <head>
          <meta charset="UTF-8">
            <title>Erreur d'initialisation</title>
            <style>
              body {font-family: Arial, sans-serif; padding: 50px;}
              .container {max-width: 800px; margin: 0 auto;}
              .error {color: red;}
              .warning {background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;}
              .btn {display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 10px 5px;}
              .btn:hover {background: #0056b3;}
              ul {text-align: left;}
            </style>
        </head>
        <body>
          <div class="container">
            <h1 class="error">⚠️ Problème lors de l'initialisation</h1>
            <p>Impossible de se connecter à la base de données Supabase.</p>
            <div class="warning">
              <h3>Vérifiez:</h3>
              <ol>
                <li>Le fichier <code>.env</code> contient les bonnes valeurs pour <code>SUPABASE_URL</code> et <code>SUPABASE_SERVICE_KEY</code>.</li>
                <li>Votre connexion internet est active.</li>
                <li>Les clés API de Supabase sont correctes.</li>
              </ol>
            </div>
            <div>
              <button onclick="window.location.reload()" class="btn">🔄 Réessayer</button>
              <a href="/login" class="btn">🔐 Essayer de se connecter quand même</a>
            </div>
          </div>
        </body>
      </html>
    `);
  }
});

// =============================================
// API ROUTES - PLANNINGS UPDATE
// =============================================

// Route API de mise à jour des plannings
app.post('/api/plannings/update', async (req, res) => {
  try {
    console.log('Requête de mise à jour planning reçue:', req.body);

    const { ID, Date: dateValue, EmployeID, OuvrageID, ActiviteID, Remarque, debitmesure } = req.body;

    // Test de connectivité
    if (req.body.test === true) {
      return res.json({
        success: true,
        message: 'Route de sauvegarde fonctionnelle'
      });
    }

    // S'assurer que la base de données est prête
    await ensureDatabaseReady();

    if (!supabase) {
      return res.status(500).json({
        success: false,
        error: 'Client Supabase non disponible'
      });
    }

    // Validation des données requises
    if (!ID) {
      return res.status(400).json({
        success: false,
        error: 'id du planning requis'
      });
    }

    if (!dateValue || !EmployeID) {
      return res.status(400).json({
        success: false,
        error: 'Date et EmployeID sont requis'
      });
    }

    // Convertir les valeurs vides en NULL pour la base de données
    const cleanData = {
      date: dateValue || null,
      employeid: parseInt(EmployeID) || null,
      ouvrageid: OuvrageID ? parseInt(OuvrageID) : null,
      activiteid: ActiviteID ? parseInt(ActiviteID) : null,
      remarque: Remarque || null,
      debitmesure: debitmesure ? parseFloat(debitmesure) : null
    };

    console.log('Données nettoyées:', cleanData);

    // Utiliser Supabase pour la mise à jour
    const { data, error } = await supabase.from('plannings').update(cleanData).eq('id', parseInt(ID));

    if (error) {
      throw error;
    }

    // Vérifier que la ligne existe bien après la mise à jour
    const { data: checkData, error: checkError } = await supabase.from('plannings').select('id').eq('id', parseInt(ID)).single();
    if (checkError || !checkData) {
      return res.status(404).json({
        success: false,
        error: `Planning avec id ${ID} introuvable`
      });
    }

    console.log(`Planning ${ID} mis à jour avec succès`);

    // Réponse de succès
    res.json({
      success: true,
      message: 'Planning mis à jour avec succès',
      planningId: parseInt(ID)
    });

  } catch (error) {
    console.error('Erreur lors de la mise à jour du planning:', error);

    // Gérer les erreurs spécifiques de Supabase
    let errorMessage = 'Erreur serveur lors de la mise à jour';

    if (error.code) { // Supabase errors have codes
      if (error.code === '23503') { // foreign_key_violation
        errorMessage = 'Référence invalide (EmployeID, OuvrageID ou ActiviteID inexistant)';
      } else if (error.code === '23505') { // unique_violation
        errorMessage = 'Violation de contrainte unique.';
      }
    } else if (error.message.includes('fetch')) {
      errorMessage = 'Erreur de connexion à la base de données';
    }

    res.status(500).json({
      success: false,
      error: errorMessage,
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

// Route GET pour récupérer un planning spécifique avec ses détails
app.get('/api/plannings/:id', async (req, res) => {
  try {
    const { id } = req.params;
    console.log(`Récupération du planning complet ${id}`);

    // S'assurer que la base de données est prête
    await ensureDatabaseReady();

    // Récupérer le planning avec tous ses détails
    // CORRIGÉ : Noms de tables et colonnes en minuscules
    const { data: planning, error } = await supabase
      .from('plannings')
      .select(`
        *,
        Employe:employes ( id, nom, prenom, surnom ),
        Ouvrage:ouvrages ( id, nom ),
        Activite:activites ( id, nom )
      `)
      .eq('id', parseInt(id))
      .single();

    if (error) throw error;

    if (!planning) {
      return res.status(404).json({
        success: false,
        error: 'Planning introuvable'
      });
    }

    console.log(`Planning trouvé:`, {
      id: planning.id,
      bilan: planning.bilan ? `${planning.bilan.length} caractères` : 'vide',
      suiteadonner: planning.suiteadonner ? `${planning.suiteadonner.length} caractères` : 'vide'
    });

    res.json({
      success: true,
      ...planning,
      bilan: planning.bilan || '',
      suiteadonner: planning.suiteadonner || ''
    });

  } catch (error) {
    console.error('Erreur lors de la récupération du planning:', error);
    res.status(500).json({
      success: false,
      error: 'Erreur serveur',
      details: error.message
    });
  }
});

// Route GET pour récupérer les détails d'un planning
app.get('/api/plannings/:id/details', async (req, res) => { // Utilisé par le modal du Kanban
  try {
    const { id } = req.params;
    console.log(`Récupération des détails pour planning ${id}`);

    // S'assurer que la base de données est prête
    await ensureDatabaseReady();

    // Récupérer les détails associés au planning
    const { data: details, error } = await supabase
      .from('planningsdetails')
      .select('bilan, suiteadonner')
      .eq('planningid', parseInt(id))
      .single();

    if (error && error.code !== 'PGRST116') { // Ignore "exact one row" error if no details exist
      throw error;
    }

    res.json({
      success: true,
      bilan: details?.bilan || '',
      suiteadonner: details?.suiteadonner || ''
    });

  } catch (error) {
    console.error('Erreur lors de la récupération des détails:', error);
    res.status(500).json({
      success: false,
      error: 'Erreur serveur'
    });
  }
});


// =============================================
// ERROR HANDLERS
// =============================================

// Route 404
app.use((req, res) => {
  res.status(404).send(`
    <!DOCTYPE html>
      <html lang="fr">
        <head>
          <meta charset="UTF-8">
            <title>Page non trouvée</title>
            <style>
              body {font-family: Arial, sans-serif; padding: 50px; text-align: center;}
              .container {max-width: 600px; margin: 0 auto;}
              h1 {color: #dc3545;}
              .btn {display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 10px;}
            </style>
        </head>
        <body>
          <div class="container">
            <h1>404 - Page non trouvée</h1>
            <p>La page <strong>${req.url}</strong> n'existe pas.</p>
            <a href="/" class="btn">Retour à l'accueil</a>
          </div>
        </body>
      </html>
  `);
});

// Gestionnaire d'erreurs global
app.use((err, req, res, next) => {
  console.error("⚠️ Erreur globale:", err);
  res.status(500).send(`
    <!DOCTYPE html>
      <html lang="fr">
        <head>
          <meta charset="UTF-8">
            <title>Erreur serveur</title>
            <style>
              body {font-family: Arial, sans-serif; padding: 50px; text-align: center;}
              .container {max-width: 600px; margin: 0 auto;}
              h1 {color: #dc3545;}
              .btn {display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 10px;}
            </style>
        </head>
        <body>
          <div class="container">
            <h1>500 - Erreur serveur</h1>
            <p>Une erreur inattendue est survenue.</p>
            <a href="/" class="btn">Retour à l'accueil</a>
          </div>
        </body>
      </html>
  `);
});

// =============================================
// DÉMARRAGE DU SERVEUR
// =============================================

async function startServer() {
  console.log("🚀 Démarrage du serveur Soakoja...");
  console.log("📍 Port configuré:", PORT);
  console.log("📍 Variable NODE_ENV:", process.env.NODE_ENV || 'non définie');

  // Démarrer le serveur
  app.listen(PORT, async () => {
    console.log("=".repeat(50));
    console.log("🌐 Serveur Soakoja démarré");
    console.log(`📍 Accès: http://localhost:${PORT}`);
    console.log(`📍 Login: http://localhost:${PORT}/login`);
    console.log("🚀 Using Supabase for database backend.");

    // Tentative d'initialisation en arrière-plan
    console.log("🔧 Tentative de connexion à Supabase en arrière-plan...");
    try {
      await ensureDatabaseReady();
      console.log("✅ Base de données: Connectée à Supabase");
    } catch (error) {
      console.log("⚠️ Base de données: Non connectée:", error.message);
      console.log(`🔧 Visitez: http://localhost:${PORT}/setup-database pour vérifier la connexion`);
    }
    console.log("=".repeat(50));
  });
}

// Démarrer l'application
startServer().catch(error => {
  console.error("❌ Erreur fatale au démarrage:", error);
  process.exit(1);
});

module.exports = app;
