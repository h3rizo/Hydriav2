const mysql = require('mysql2/promise');

async function addPlanningsDetailsColumns() {
  console.log('🔧 Migration: Ajout des colonnes Bilan et SuiteADonner à la table planningsdetails...');

  try {
    const connection = await mysql.createConnection({
      host: 'localhost',
      port: 3307,
      user: 'root',
      password: '',
      database: 'hydriav2_clean'
    });

    console.log('✅ Connexion à la base de données réussie');

    // Vérifier si la table planningsdetails existe
    const [tables] = await connection.execute(`
      SELECT TABLE_NAME 
      FROM INFORMATION_SCHEMA.TABLES 
      WHERE TABLE_SCHEMA = 'hydriav2_clean' 
      AND TABLE_NAME = 'planningsdetails'
    `);

    if (tables.length === 0) {
      console.log('❌ La table planningsdetails n\'existe pas');
      console.log('💡 Création de la table planningsdetails...');

      // Créer la table planningsdetails si elle n'existe pas
      await connection.execute(`
        CREATE TABLE \`planningsdetails\` (
          \`ID\` INT AUTO_INCREMENT PRIMARY KEY,
          \`PlanningID\` INT NOT NULL,
          \`OuvrageConstitutif\` VARCHAR(255),
          \`DesignationID\` INT NOT NULL,
          \`Quantite\` FLOAT,
          \`PrixUnitaire\` FLOAT,
          \`Montant\` FLOAT,
          \`AcheteurID\` INT,
          \`MagasinID\` INT,
          \`CompteID\` INT,
          \`EstLivre\` BOOLEAN DEFAULT FALSE,
          \`EstRetourne\` BOOLEAN DEFAULT FALSE,
          \`NumeroDiameX\` VARCHAR(255),
          \`BaseDiameX\` VARCHAR(255),
          \`Bilan\` LONGTEXT,
          \`SuiteADonner\` LONGTEXT,
          \`createdAt\` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          \`updatedAt\` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          FOREIGN KEY (\`PlanningID\`) REFERENCES \`Plannings\`(\`ID\`) ON DELETE CASCADE ON UPDATE CASCADE,
          FOREIGN KEY (\`DesignationID\`) REFERENCES \`Designations\`(\`ID\`) ON DELETE CASCADE ON UPDATE CASCADE,
          FOREIGN KEY (\`AcheteurID\`) REFERENCES \`Employes\`(\`ID\`) ON DELETE SET NULL ON UPDATE CASCADE,
          FOREIGN KEY (\`MagasinID\`) REFERENCES \`Magasins\`(\`ID\`) ON DELETE SET NULL ON UPDATE CASCADE,
          FOREIGN KEY (\`CompteID\`) REFERENCES \`Comptes\`(\`ID\`) ON DELETE SET NULL ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
      `);

      console.log('✅ Table planningsdetails créée avec les nouvelles colonnes');
    } else {
      console.log('✅ Table planningsdetails trouvée');

      // Vérifier si les colonnes existent déjà
      const [columns] = await connection.execute(`
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = 'hydriav2_clean' 
        AND TABLE_NAME = 'planningsdetails' 
        AND COLUMN_NAME IN ('Bilan', 'SuiteADonner')
      `);

      const existingColumns = columns.map(col => col.COLUMN_NAME);
      const columnsToAdd = [];

      if (!existingColumns.includes('Bilan')) {
        columnsToAdd.push('Bilan');
      }

      if (!existingColumns.includes('SuiteADonner')) {
        columnsToAdd.push('SuiteADonner');
      }

      if (columnsToAdd.length > 0) {
        console.log(`📝 Ajout des colonnes: ${columnsToAdd.join(', ')}`);

        for (const columnName of columnsToAdd) {
          await connection.execute(`
            ALTER TABLE \`planningsdetails\` 
            ADD COLUMN \`${columnName}\` LONGTEXT
          `);
          console.log(`✅ Colonne ${columnName} ajoutée`);
        }
      } else {
        console.log('ℹ️ Les colonnes Bilan et SuiteADonner existent déjà');
      }
    }

    // Vérifier le résultat final
    const [finalColumns] = await connection.execute(`
      SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE 
      FROM INFORMATION_SCHEMA.COLUMNS 
      WHERE TABLE_SCHEMA = 'hydriav2_clean' 
      AND TABLE_NAME = 'planningsdetails' 
      ORDER BY ORDINAL_POSITION
    `);

    console.log('\n📋 Structure finale de la table planningsdetails:');
    finalColumns.forEach(col => {
      console.log(`  - ${col.COLUMN_NAME} (${col.DATA_TYPE}) - ${col.IS_NULLABLE === 'YES' ? 'NULL' : 'NOT NULL'}`);
    });

    await connection.end();
    console.log('\n✅ Migration terminée avec succès');

  } catch (error) {
    console.error('❌ Erreur lors de la migration:', error.message);
    console.error('💡 Détails:', error);
    process.exit(1);
  }
}

// Exécuter la migration si ce fichier est appelé directement
if (require.main === module) {
  addPlanningsDetailsColumns();
}

module.exports = addPlanningsDetailsColumns;