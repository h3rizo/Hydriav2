// diagnostic-models.js - Créez ce fichier dans votre dossier racine
const { Sequelize, DataTypes } = require("sequelize");
const fs = require("fs");
const path = require("path");

console.log("🔍 DIAGNOSTIC DES MODÈLES\n");

// Configuration Sequelize minimale pour test
const sequelize = new Sequelize('hydriav2_clean', 'root', '', {
  host: 'localhost',
  port: 3307,
  dialect: 'mysql',
  logging: false
});

const modelsDir = path.join(__dirname, 'models');
const modelFiles = fs.readdirSync(modelsDir)
  .filter(file => file.endsWith('.js') && file !== 'index.js')
  .sort();

console.log(`📁 ${modelFiles.length} fichiers trouvés:`);
modelFiles.forEach(file => console.log(`   - ${file}`));

console.log('\n🧪 TEST DE CHARGEMENT INDIVIDUEL:\n');

const loadedModels = {};
const failedModels = [];

// Tester chaque modèle individuellement
for (const file of modelFiles) {
  const filePath = path.join(modelsDir, file);
  const modelName = path.basename(file, '.js');

  try {
    // Supprimer le cache du module
    delete require.cache[require.resolve(filePath)];

    // Essayer de charger le module
    const modelDefiner = require(filePath);

    if (typeof modelDefiner !== 'function') {
      console.log(`❌ ${file}: N'exporte pas une fonction`);
      failedModels.push({ file, error: 'Not a function' });
      continue;
    }

    // Essayer de créer le modèle
    const model = modelDefiner(sequelize, DataTypes);

    if (!model || !model.name) {
      console.log(`❌ ${file}: Modèle invalide (pas de nom)`);
      failedModels.push({ file, error: 'Invalid model' });
      continue;
    }

    loadedModels[model.name] = model;
    console.log(`✅ ${file}: ${model.name} OK`);

  } catch (error) {
    console.log(`❌ ${file}: ${error.message}`);
    failedModels.push({ file, error: error.message });
  }
}

console.log('\n📊 RÉSUMÉ:');
console.log(`✅ Modèles chargés: ${Object.keys(loadedModels).length}`);
console.log(`❌ Modèles échoués: ${failedModels.length}`);

if (failedModels.length > 0) {
  console.log('\n❌ DÉTAILS DES ERREURS:');
  failedModels.forEach(({ file, error }) => {
    console.log(`\n📄 ${file}:`);
    console.log(`   Erreur: ${error}`);

    // Afficher les premières lignes du fichier pour debug
    try {
      const content = fs.readFileSync(path.join(modelsDir, file), 'utf8');
      const lines = content.split('\n').slice(0, 10);
      console.log('   Premières lignes:');
      lines.forEach((line, i) => {
        if (line.trim()) console.log(`   ${i + 1}: ${line.trim()}`);
      });
    } catch (e) {
      console.log('   Impossible de lire le fichier');
    }
  });
}

console.log('\n🔍 FICHIERS À CORRIGER EN PRIORITÉ:');
failedModels.forEach(({ file, error }) => {
  if (error.includes('allownull') || error.includes('allowNull')) {
    console.log(`🔧 ${file}: Remplacer 'allownull' par 'allowNull'`);
  } else if (error.includes('not defined') || error.includes('ReferenceError')) {
    console.log(`🔧 ${file}: Variable non définie dans le code`);
  } else {
    console.log(`🔧 ${file}: ${error}`);
  }
});

process.exit(0);