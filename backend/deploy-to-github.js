/**
 * Script pour faciliter le déploiement vers GitHub
 * Ce script commit et push les modifications vers GitHub
 * pour déclencher le déploiement automatique sur Render
 */

const { execSync } = require('child_process');
const readline = require('readline');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

console.log('🚀 Préparation du déploiement vers GitHub...');

// Vérifier l'état de Git
try {
  const status = execSync('git status --porcelain').toString();
  
  if (!status) {
    console.log('✅ Aucune modification à commiter. Le dépôt est à jour.');
    process.exit(0);
  }
  
  console.log('\n📝 Modifications détectées:');
  console.log(execSync('git status').toString());
  
  rl.question('\n✏️ Entrez un message de commit: ', (commitMessage) => {
    if (!commitMessage) {
      console.error('❌ Le message de commit ne peut pas être vide.');
      rl.close();
      process.exit(1);
    }
    
    try {
      // Ajouter tous les fichiers modifiés
      console.log('\n📦 Ajout des fichiers modifiés...');
      execSync('git add .');
      
      // Créer le commit
      console.log(`\n📌 Création du commit: "${commitMessage}"...`);
      execSync(`git commit -m "${commitMessage}"`);
      
      // Demander confirmation avant de pousser
      rl.question('\n🚀 Voulez-vous pousser les modifications vers GitHub? (o/n): ', (answer) => {
        if (answer.toLowerCase() === 'o' || answer.toLowerCase() === 'oui') {
          try {
            console.log('\n📤 Envoi des modifications vers GitHub...');
            execSync('git push origin main');
            console.log('\n✅ Les modifications ont été envoyées avec succès!');
            console.log('\n📋 Prochaines étapes:');
            console.log('1. Connectez-vous à Render (https://render.com)');
            console.log('2. Vérifiez que le déploiement automatique a été déclenché');
            console.log('3. Si nécessaire, configurez les variables d\'environnement dans Render');
          } catch (pushError) {
            console.error('\n❌ Erreur lors de l\'envoi vers GitHub:', pushError.message);
          }
        } else {
          console.log('\n⏸️ Les modifications ont été commitées mais pas envoyées.');
          console.log('Pour envoyer manuellement plus tard, utilisez: git push origin main');
        }
        rl.close();
      });
    } catch (commitError) {
      console.error('\n❌ Erreur lors du commit:', commitError.message);
      rl.close();
    }
  });
} catch (error) {
  console.error('\n❌ Erreur lors de la vérification de l\'état Git:', error.message);
  rl.close();
}