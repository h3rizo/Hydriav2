const { Sequelize, DataTypes } = require("sequelize");
const fs = require("fs");
const path = require("path");

let sequelize = null;
let isInitialized = false;
const db = {};

// Lazy initialization function - only connects when called
async function initializeDatabase() {
  if (isInitialized) {
    return db;
  }

  console.log("🔧 Lazy initialization of database...");

  try {
    // First create a connection without specifying database to create the database if needed
    const tempSequelize = new Sequelize({
      dialect: "mysql",
      host: "localhost",
      port: 3307,
      username: "root",
      password: "",
      logging: false
    });

    try {
      // Create the database if it doesn't exist
      await tempSequelize.query("CREATE DATABASE IF NOT EXISTS `hydriav2_clean` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;");
      console.log("✅ Database 'hydriav2_clean' created or already exists");
      await tempSequelize.close();
    } catch (dbCreateError) {
      console.error("❌ Failed to create database:", dbCreateError.message);
      await tempSequelize.close();
    }

    // Now create Sequelize instance with the specific database
    sequelize = new Sequelize({
      dialect: "mysql",
      host: "localhost",
      port: 3307,
      database: "hydriav2_clean", // Match the main configuration
      username: "root",
      password: "",
      logging: (sql) => console.log(`🔍 SQL Query: ${sql.replace(/Executed \(default\): /, '')}`), // Enable logging to debug
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

    // Test connection
    await sequelize.authenticate();
    console.log("✅ Database connection established");

    // Verify which database we're connected to
    const [results] = await sequelize.query("SELECT DATABASE() as current_database");
    const currentDb = results[0].current_database;
    console.log(`🔍 Currently connected to database: ${currentDb}`);

    if (currentDb !== 'hydriav2_clean') {
      throw new Error(`Connected to wrong database: ${currentDb}. Expected: hydriav2_clean`);
    }

    // Load models only after connection is established
    console.log("📚 Loading models...");

    const modelFiles = fs.readdirSync(__dirname)
      .filter(file =>
        file.indexOf(".") !== 0 &&
        !file.startsWith("index") &&
        file.slice(-3) === ".js"
      );

    console.log(`Found ${modelFiles.length} model files`);

    // Load each model
    modelFiles.forEach((file) => {
      try {
        const modelDefiner = require(path.join(__dirname, file));

        if (typeof modelDefiner !== 'function') {
          console.error(`ERROR ${file}: Does not export a function`);
          return;
        }

        const model = modelDefiner(sequelize, DataTypes);

        if (!model || !model.name) {
          console.error(`ERROR ${file}: Model is null or has no name`);
          return;
        }

        // Verify it's actually a Sequelize model
        if (typeof model.findOne !== 'function') {
          console.error(`ERROR ${file}: Not a valid Sequelize model`);
          return;
        }

        db[model.name] = model;
        console.log(`✅ Loaded model: ${model.name}`);
      } catch (error) {
        console.error(`ERROR loading ${file}:`, error.message);
      }
    });

    // Create associations
    const loadedModels = Object.keys(db).filter(modelName => {
      const model = db[modelName];
      // Check if it's a valid Sequelize model by checking for common Sequelize methods
      return model &&
        typeof model === 'function' &&
        typeof model.findOne === 'function' &&
        typeof model.create === 'function' &&
        model.name;
    });

    console.log(`Creating associations for ${loadedModels.length} models...`);

    loadedModels.forEach((modelName) => {
      const model = db[modelName];
      if (model && model.associate && typeof model.associate === 'function') {
        try {
          model.associate(db);
          console.log(`✅ Associations created for ${modelName}`);
        } catch (error) {
          console.error(`ERROR creating associations for ${modelName}:`, error.message);
        }
      }
    });

    // Add sequelize instances to db object
    db.sequelize = sequelize;
    db.Sequelize = Sequelize;

    // Add utility functions
    db.testConnection = async () => {
      try {
        await sequelize.authenticate();
        return true;
      } catch (error) {
        console.error("Connection test failed:", error.message);
        return false;
      }
    };

    isInitialized = true;
    console.log(`✅ Database initialized successfully with ${loadedModels.length} models`);

    return db;

  } catch (error) {
    console.error("❌ Database initialization failed:", error.message);
    throw error;
  }
}

// Export function to get initialized db
const getDatabase = async () => {
  if (!isInitialized) {
    await initializeDatabase();
  }
  return db;
};

// Export sync version for compatibility (but it will be empty until initialized)
db.sequelize = null; // Will be set after initialization
db.Sequelize = Sequelize;
db.getDatabase = getDatabase;
db.initializeDatabase = initializeDatabase;
db.isInitialized = () => isInitialized;

// For immediate access (returns empty db if not initialized)
Object.defineProperty(db, 'initialized', {
  get: () => isInitialized
});

console.log("📦 Models module loaded (lazy initialization)");

module.exports = db;