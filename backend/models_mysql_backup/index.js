const { Sequelize, DataTypes } = require("sequelize");
const fs = require("fs");
const path = require("path");

// Configuration Sequelize pour MySQL
const sequelize = new Sequelize({
  dialect: "mysql",
  host: "localhost",
  port: 3307,
  database: "hydriav2_clean",
  username: "root",
  password: "",
  logging: (sql, timing) => console.log(`SQL: ${sql.replace(/Executed \(default\): /, '')}${timing ? ` (${timing}ms)` : ""}`),
  pool: {
    max: 10,
    min: 0,
    acquire: 30000,
    idle: 10000
  },
  dialectOptions: {
    charset: "utf8mb4"
  },
  define: {
    timestamps: true,
    underscored: false,
    freezeTableName: true,
    charset: "utf8mb4"
  }
});

const db = {};

console.log("Initialisation de la base de donnees MySQL...");

// Charger tous les modeles
const modelFiles = fs.readdirSync(__dirname)
  .filter(file =>
    file.indexOf(".") !== 0 &&
    !file.startsWith("index") &&  // Exclure tous les fichiers index-*
    file.slice(-3) === ".js"
  );

console.log(`${modelFiles.length} fichiers de modeles trouves: ${modelFiles.join(', ')}`);

// Charger chaque modele
modelFiles.forEach((file) => {
  console.log(`Chargement du modele: ${file}`);
  try {
    const modelDefiner = require(path.join(__dirname, file));

    if (typeof modelDefiner !== 'function') {
      console.error(`ERREUR ${file}: N'exporte pas une fonction`);
      return;
    }

    const model = modelDefiner(sequelize, DataTypes);

    if (!model || !model.name) {
      console.error(`ERREUR ${file}: Modele invalide`);
      return;
    }

    db[model.name] = model;
    console.log(`OK Modele ${model.name} charge avec succes`);
  } catch (error) {
    console.error(`ERREUR lors du chargement de ${file}:`, error.message);
  }
});

// Creer les associations
console.log("Creation des associations entre modeles...");

// NOUVEAU CODE
const loadedModels = Object.keys(db).filter(modelName =>
  db[modelName].prototype instanceof Sequelize.Model
);

console.log(`DEBUG: Models in db object: ${Object.keys(db)}`);

loadedModels.forEach((modelName) => {
  const model = db[modelName];

  if (model.associate && typeof model.associate === 'function') {
    console.log(`Creation des associations pour: ${modelName}`);
    try {
      model.associate(db);
      console.log(`OK Associations creees pour ${modelName}`);
    } catch (error) {
      console.error(`ERREUR lors de l'association de ${modelName}:`, error.message);
    }
  }
});

// Fonctions utilitaires
db.testConnection = async () => {
  try {
    console.log("Test de connexion a MySQL...");
    await sequelize.authenticate();
    console.log("OK Connexion MySQL etablie avec succes.");

    const [results] = await sequelize.query("SELECT VERSION() as version");
    console.log(`Version MySQL: ${results[0].version}`);

    return true;
  } catch (error) {
    console.error("ERREUR Impossible de se connecter a MySQL:", error.message);
    return false;
  }
};

db.createDatabaseIfNotExists = async () => {
  console.log("Verification/Creation de la base de donnees...");

  const tempSequelize = new Sequelize({
    dialect: "mysql",
    host: "localhost",
    port: 3307,
    username: "root",
    password: "",
    logging: false
  });

  try {
    const dbName = "hydriav2_clean";

    await tempSequelize.query(
      `CREATE DATABASE IF NOT EXISTS \`${dbName}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`
    );
    console.log(`OK Base de donnees '${dbName}' creee ou existe deja.`);

    const [databases] = await tempSequelize.query("SHOW DATABASES LIKE ?", {
      replacements: [dbName]
    });

    if (databases.length > 0) {
      console.log(`Base de donnees '${dbName}' confirmee.`);
    }

    await tempSequelize.close();
    return true;
  } catch (error) {
    console.error("ERREUR lors de la creation de la base de donnees:", error.message);
    try {
      await tempSequelize.close();
    } catch (closeError) {
      console.error("ERREUR lors de la fermeture:", closeError.message);
    }
    return false;
  }
};

db.syncDatabase = async (options = {}) => {
  try {
    console.log("Synchronisation des modeles avec la base de donnees...");

    const syncOptions = {
      force: options.force || false,
      alter: options.alter || false,
      logging: (sql) => console.log(`SYNC: ${sql}`),
      ...options
    };

    if (syncOptions.force) {
      console.log("ATTENTION: Mode FORCE active - toutes les donnees seront perdues !");
    }

    await sequelize.sync(syncOptions);
    console.log("OK Base de donnees synchronisee avec succes.");

    const [tables] = await sequelize.query("SHOW TABLES");
    console.log(`${tables.length} tables creees: ${tables.map(t => Object.values(t)[0]).join(', ')}`);

    return true;
  } catch (error) {
    console.error("ERREUR lors de la synchronisation:", error.message);
    return false;
  }
};

db.initialize = async (options = {}) => {
  console.log("Initialisation complete de la base de donnees...");

  try {
    const dbCreated = await db.createDatabaseIfNotExists();
    if (!dbCreated) {
      throw new Error("Impossible de creer la base de donnees");
    }

    const connectionOk = await db.testConnection();
    if (!connectionOk) {
      throw new Error("Impossible de se connecter a la base de donnees");
    }

    if (options.sync !== false) {
      await db.syncDatabase(options.syncOptions || { force: false, alter: true });
    }

    console.log("OK Initialisation de la base de donnees terminee avec succes !");
    return true;
  } catch (error) {
    console.error("ERREUR Echec de l'initialisation:", error.message);
    return false;
  }
};

db.closeConnection = async () => {
  try {
    console.log("Fermeture de la connexion...");
    await sequelize.close();
    console.log("OK Connexion fermee avec succes.");
  } catch (error) {
    console.error("ERREUR lors de la fermeture:", error.message);
  }
};

// Exporter les objets
db.sequelize = sequelize;
db.Sequelize = Sequelize;

// Afficher le resume
console.log(`${loadedModels.length} modeles charges:`, loadedModels);
console.log("Fonctions utilitaires disponibles:");
console.log("   - db.testConnection()");
console.log("   - db.createDatabaseIfNotExists()");
console.log("   - db.syncDatabase(options)");
console.log("   - db.initialize(options)");
console.log("   - db.closeConnection()");

module.exports = db;