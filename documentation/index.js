const { Sequelize, DataTypes } = require("sequelize");
const fs = require("fs");
const path = require("path");

// Charger les variables d'environnement
require("dotenv").config();

// 1. Initialiser la connexion Sequelize pour MySQL - CONFIGURATION CORRIGÉE
const sequelize = new Sequelize({
  dialect: "mysql",
  host: process.env.DB_HOST || "localhost",
  port: process.env.DB_PORT || 3307,  // Maintenir 3307 selon votre configuration
  database: "hydriav2_clean",         // Forcé à hydriav2_clean
  username: process.env.DB_USER || "root",
  password: process.env.DB_PASS || "",

  // Configuration du pool de connexions MySQL
  pool: {
    max: 10,
    min: 0,
    acquire: 30000,
    idle: 10000,
    evict: 1000,
    handleDisconnects: true
  },

  // Configuration MySQL spécifique - SIMPLIFIÉE
  dialectOptions: {
    charset: "utf8mb4",
    collate: "utf8mb4_unicode_ci"
    // Supprimé les options qui causent des warnings
  },

  // Timezone
  timezone: "+03:00", // Madagascar timezone (UTC+3)

  // Logging - toujours activer pour debug
  logging: (sql, timing) => console.log(`🔍 [${new Date().toISOString()}] SQL: ${sql.replace(/Executed \(default\): /, '')}${timing ? ` (${timing}ms)` : ""}`),

  // Benchmark des requêtes
  benchmark: true,

  // Options par défaut pour tous les modèles - SIMPLIFIÉES
  define: {
    timestamps: true,
    underscored: false,
    freezeTableName: true,
    charset: "utf8mb4",
    collate: "utf8mb4_unicode_ci",
    paranoid: false,
    version: false
    // Supprimé les hooks qui peuvent causer des problèmes
  },

  // Retry automatique des connexions - SIMPLIFIÉ
  retry: {
    max: 3,
    timeout: 5000,
    match: [
      Sequelize.ConnectionError,
      Sequelize.ConnectionTimedOutError,
      Sequelize.TimeoutError
    ]
  }
});

const db = {};

// 2. Charger dynamiquement tous les modèles de ce dossier - AVEC MEILLEURE GESTION D'ERREUR

console.log("🚀 Initialisation de la base de données MySQL...");

const modelFiles = fs.readdirSync(__dirname)
  .filter((file) => {
    return (
      file.indexOf(".") !== 0 &&
      file !== "index.js" &&
      file.slice(-3) === ".js" &&
      !file.includes(".test.") &&
      !file.includes(".spec.")
    );
  });

console.log(`📁 ${modelFiles.length} fichiers de modèles trouvés: ${modelFiles.join(', ')}`);

modelFiles.forEach((file) => {
  console.log(`📄 Chargement du modèle: ${file}`);
  try {
    const modelDefiner = require(path.join(__dirname, file));

    // Vérifier que c'est bien une fonction
    if (typeof modelDefiner !== 'function') {
      console.error(`❌ ${file}: N'exporte pas une fonction`);
      return;
    }

    const model = modelDefiner(sequelize, DataTypes);

    // Vérifier que le modèle est valide
    if (!model || !model.name) {
      console.error(`❌ ${file}: Modèle invalide (pas de nom)`);
      return;
    }

    db[model.name] = model;
    console.log(`✅ Modèle ${model.name} chargé avec succès`);
  } catch (error) {
    console.error(`❌ Erreur lors du chargement de ${file}:`, error.message);
    console.error(`   Stack: ${error.stack.split('\n')[1]}`); // Première ligne du stack seulement
  }
});

// =============================================
// 3. CRÉATION DES ASSOCIATIONS ENTRE MODÈLES - AMÉLIORÉE
// =============================================
console.log("🔗 Création des associations entre modèles...");

const loadedModels = Object.keys(db).filter(key =>
  key !== "sequelize" &&
  key !== "Sequelize" &&
  typeof db[key] !== "function"
);

loadedModels.forEach((modelName) => {
  const model = db[modelName];

  if (model.associate && typeof model.associate === 'function') {
    console.log(`🔗 Création des associations pour: ${modelName}`);
    try {
      model.associate(db);
      console.log(`✅ Associations créées pour ${modelName}`);
    } catch (error) {
      console.error(`❌ Erreur lors de l'association de ${modelName}:`, error.message);
      console.error(`Stack trace: ${error.stack}`);
    }
  }
});

/**
 * Fonction utilitaire pour tester la connexion
 * @returns {Promise<boolean>} True si la connexion réussit
 */
db.testConnection = async () => {
  try {
    console.log("🔄 Test de connexion à MySQL...");
    await sequelize.authenticate();
    console.log("✅ Connexion MySQL établie avec succès.");

    // Afficher les informations de la base de données
    const [results] = await sequelize.query("SELECT VERSION() as version");
    console.log(`📊 Version MySQL: ${results[0].version}`);

    return true;
  } catch (error) {
    console.error("❌ Impossible de se connecter à MySQL:", error.message);
    console.error("🔍 Vérifiez que :");
    console.error("   - MySQL/MariaDB est démarré (via XAMPP ou service)");
    console.error("   - Le port est correct (3306 par défaut)");
    console.error("   - La base 'hydriav2_clean' existe");
    console.error("   - L'utilisateur 'root' a les permissions");
    return false;
  }
};

// 5. Fonction pour créer la base de données si elle n'existe pas - CORRIGÉE
db.createDatabaseIfNotExists = async () => {
  console.log("🔄 Vérification/Création de la base de données...");

  const tempSequelize = new Sequelize({
    dialect: "mysql",
    host: process.env.DB_HOST || "localhost",
    port: process.env.DB_PORT || 3306,  // Corrigé
    username: process.env.DB_USER || "root",
    password: process.env.DB_PASS || "",
    logging: false,
    dialectOptions: {
      charset: "utf8mb4"
    }
  });

  try {
    const dbName = "hydriav2_clean";  // Forcé

    // Créer la base de données
    await tempSequelize.query(
      `CREATE DATABASE IF NOT EXISTS \`${dbName}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`
    );
    console.log(`✅ Base de données '${dbName}' créée ou existe déjà.`);

    // Vérifier que la base existe
    const [databases] = await tempSequelize.query("SHOW DATABASES LIKE ?", {
      replacements: [dbName]
    });

    if (databases.length > 0) {
      console.log(`📊 Base de données '${dbName}' confirmée.`);
    }

    await tempSequelize.close();
    return true;
  } catch (error) {
    console.error("❌ Erreur lors de la création de la base de données:", error.message);
    try {
      await tempSequelize.close();
    } catch (closeError) {
      console.error("❌ Erreur lors de la fermeture de la connexion temporaire:", closeError.message);
    }
    return false;
  }
};

/**
 * Fonction pour synchroniser tous les modèles avec la base de données
 * @param {Object} options - Options de synchronisation
 * @returns {Promise<boolean>} True si la synchronisation réussit
 */
db.syncDatabase = async (options = {}) => {
  try {
    console.log("🔄 Synchronisation des modèles avec la base de données...");

    const syncOptions = {
      force: options.force || false,
      alter: options.alter || false,
      logging: (sql) => console.log(`🔍 SYNC: ${sql}`),
      ...options
    };

    if (syncOptions.force) {
      console.log("⚠️ ATTENTION: Mode FORCE activé - toutes les données seront perdues !");
    }

    await sequelize.sync(syncOptions);
    console.log("✅ Base de données synchronisée avec succès.");

    // Vérifier les tables créées
    const [tables] = await sequelize.query("SHOW TABLES");
    console.log(`📊 ${tables.length} tables créées: ${tables.map(t => Object.values(t)[0]).join(', ')}`);

    return true;
  } catch (error) {
    console.error("❌ Erreur lors de la synchronisation:", error.message);
    console.error("Stack:", error.stack);
    return false;
  }
};

/**
 * Fonction complète d'initialisation de la base de données
 * @param {Object} options - Options d'initialisation
 * @returns {Promise<boolean>} True si l'initialisation réussit
 */
db.initialize = async (options = {}) => {
  console.log("🚀 Initialisation complète de la base de données...");

  try {
    // 1. Créer la base si elle n'existe pas
    const dbCreated = await db.createDatabaseIfNotExists();
    if (!dbCreated) {
      throw new Error("Impossible de créer la base de données");
    }

    // 2. Tester la connexion
    const connectionOk = await db.testConnection();
    if (!connectionOk) {
      throw new Error("Impossible de se connecter à la base de données");
    }

    // 3. Synchroniser les modèles
    if (options.sync !== false) {
      await db.syncDatabase(options.syncOptions || { force: false, alter: true });
    }

    console.log("🎉 Initialisation de la base de données terminée avec succès !");
    return true;
  } catch (error) {
    console.error("❌ Échec de l'initialisation de la base de données:", error.message);
    return false;
  }
};

/**
 * Fonction pour fermer proprement la connexion à la base de données
 */
db.closeConnection = async () => {
  try {
    console.log("🔄 Fermeture de la connexion à la base de données...");
    await sequelize.close();
    console.log("✅ Connexion fermée avec succès.");
  } catch (error) {
    console.error("❌ Erreur lors de la fermeture de la connexion:", error.message);
  }
};

// =============================================
// 5. EXPORTATION DES OBJETS
// =============================================

// Exporter l'instance de connexion et les modèles
db.sequelize = sequelize;
db.Sequelize = Sequelize;

// Gestion des signaux pour fermeture propre
process.on("SIGINT", async () => {
  console.log("\n🛑 Signal SIGINT reçu. Fermeture propre...");
  await db.closeConnection();
  process.exit(0);
});

process.on("SIGTERM", async () => {
  console.log("\n🛑 Signal SIGTERM reçu. Fermeture propre...");
  await db.closeConnection();
  process.exit(0);
});

// Afficher les modèles chargés
const modelNames = Object.keys(db).filter(
  (key) => key !== "sequelize" && key !== "Sequelize" && typeof db[key] !== "function"
);

console.log(`📊 ${modelNames.length} modèles chargés:`, modelNames);
console.log("🔧 Fonctions utilitaires disponibles:");
console.log("   - db.testConnection()");
console.log("   - db.createDatabaseIfNotExists()");
console.log("   - db.executeSqlScript()");
console.log("   - db.syncDatabase(options)");
console.log("   - db.initialize(options)");
console.log("   - db.closeConnection()");

module.exports = db;