/**
 * Script de préparation au déploiement sur Render
 * Ce script vérifie que toutes les configurations nécessaires sont en place
 * pour un déploiement réussi sur Render
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

console.log('🚀 Préparation du déploiement sur Render...');

// Vérifier la présence des fichiers essentiels
const requiredFiles = [
  'package.json',
  'server.js',
  'render.yaml',
  '.env.example'
];

let allFilesPresent = true;

requiredFiles.forEach(file => {
  if (!fs.existsSync(file)) {
    console.error(`❌ Fichier manquant: ${file}`);
    allFilesPresent = false;
  } else {
    console.log(`✅ Fichier présent: ${file}`);
  }
});

// Vérifier la configuration de Git
try {
  const remoteUrl = execSync('git remote get-url origin').toString().trim();
  console.log(`✅ Dépôt Git configuré: ${remoteUrl}`);
  
  // Vérifier si le dépôt est sur GitHub
  if (remoteUrl.includes('github.com')) {
    console.log('✅ Dépôt hébergé sur GitHub (compatible avec Render)');
  } else {
    console.warn('⚠️ Le dépôt n\'est pas sur GitHub. Render fonctionne mieux avec GitHub.');
  }
} catch (error) {
  console.error('❌ Erreur lors de la vérification de la configuration Git:', error.message);
}

// Vérifier la présence des scripts dans package.json
try {
  const packageJson = JSON.parse(fs.readFileSync('package.json', 'utf8'));
  
  if (packageJson.scripts && packageJson.scripts.start) {
    console.log(`✅ Script de démarrage trouvé: ${packageJson.scripts.start}`);
  } else {
    console.error('❌ Script de démarrage manquant dans package.json');
    allFilesPresent = false;
  }
  
  // Vérifier les dépendances essentielles
  const essentialDeps = ['express', 'dotenv', '@supabase/supabase-js'];
  const missingDeps = [];
  
  essentialDeps.forEach(dep => {
    if (!packageJson.dependencies || !packageJson.dependencies[dep]) {
      missingDeps.push(dep);
    }
  });
  
  if (missingDeps.length > 0) {
    console.warn(`⚠️ Dépendances potentiellement manquantes: ${missingDeps.join(', ')}`);
  } else {
    console.log('✅ Toutes les dépendances essentielles sont présentes');
  }
  
} catch (error) {
  console.error('❌ Erreur lors de la lecture de package.json:', error.message);
}

// Vérifier la configuration des variables d'environnement
try {
  const envExample = fs.readFileSync('.env.example', 'utf8');
  const requiredEnvVars = ['SUPABASE_URL', 'SUPABASE_SERVICE_KEY'];
  const missingEnvVars = [];
  
  requiredEnvVars.forEach(envVar => {
    if (!envExample.includes(envVar)) {
      missingEnvVars.push(envVar);
    }
  });
  
  if (missingEnvVars.length > 0) {
    console.warn(`⚠️ Variables d'environnement manquantes dans .env.example: ${missingEnvVars.join(', ')}`);
  } else {
    console.log('✅ Toutes les variables d\'environnement requises sont définies dans .env.example');
  }
  
} catch (error) {
  console.error('❌ Erreur lors de la lecture de .env.example:', error.message);
}

// Vérifier la configuration de render.yaml
try {
  const renderConfig = fs.readFileSync('render.yaml', 'utf8');
  
  if (renderConfig.includes('services:') && renderConfig.includes('startCommand:')) {
    console.log('✅ Configuration Render valide détectée');
  } else {
    console.warn('⚠️ La configuration Render pourrait être incomplète');
  }
  
} catch (error) {
  console.error('❌ Erreur lors de la lecture de render.yaml:', error.message);
}

// Résumé
if (allFilesPresent) {
  console.log('\n✅ Le projet est prêt pour le déploiement sur Render!');
  console.log('\n📋 Prochaines étapes:');
  console.log('1. Assurez-vous que tous vos changements sont commités et poussés vers GitHub');
  console.log('2. Connectez-vous à Render et créez un nouveau service Web en pointant vers votre dépôt GitHub');
  console.log('3. Configurez les variables d\'environnement dans Render');
  console.log('4. Lancez le déploiement');
} else {
  console.error('\n❌ Certains éléments sont manquants pour le déploiement sur Render.');
  console.log('Veuillez corriger les problèmes signalés ci-dessus avant de déployer.');
}