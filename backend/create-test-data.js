const mysql = require('mysql2/promise');

async function createTestData() {
  try {
    const connection = await mysql.createConnection({
      host: 'localhost',
      port: 3307,
      user: 'root',
      password: '',
      database: 'hydriav2_clean'
    });

    console.log('🔍 Connected to database');

    // Check current data
    const [employees] = await connection.execute('SELECT ID, Nom, Prenom FROM Employes LIMIT 3');
    const [activities] = await connection.execute('SELECT ID, Nom FROM Activites LIMIT 3');
    const [plannings] = await connection.execute('SELECT COUNT(*) as count FROM Plannings');

    console.log('👥 Employees:', employees.map(e => `${e.Prenom} ${e.Nom}`));
    console.log('🔧 Activities:', activities.map(a => a.Nom));
    console.log('📋 Current plannings:', plannings[0].count);

    if (plannings[0].count === 0 && employees.length > 0 && activities.length > 0) {
      console.log('💡 Creating test planning data...');

      // Insert test planning records
      for (let i = 0; i < 5; i++) {
        const employeeIndex = i % employees.length;
        const activityIndex = i % activities.length;

        await connection.execute(`
          INSERT INTO Plannings (Date, EmployeID, ActiviteID, Remarque, EstValide, createdAt, updatedAt)
          VALUES (?, ?, ?, ?, ?, NOW(), NOW())
        `, [
          new Date(Date.now() + i * 24 * 60 * 60 * 1000), // Add i days from today
          employees[employeeIndex].ID,
          activities[activityIndex].ID,
          `Test planning entry ${i + 1}`,
          i % 2 === 0 // Alternate between validated and pending
        ]);
      }

      console.log('✅ Created 5 test planning records');
    } else {
      console.log('ℹ️ Test data already exists or missing reference data');
    }

    // Verify results
    const [newPlannings] = await connection.execute(`
      SELECT p.ID, p.Date, p.Remarque, p.EstValide, 
             e.Prenom, e.Nom, a.Nom as ActivityName
      FROM Plannings p
      LEFT JOIN Employes e ON p.EmployeID = e.ID
      LEFT JOIN Activites a ON p.ActiviteID = a.ID
      ORDER BY p.Date DESC LIMIT 10
    `);

    console.log('📋 Current planning data:');
    newPlannings.forEach((p, i) => {
      console.log(`  ${i + 1}. ${p.Date.toISOString().split('T')[0]} - ${p.Prenom} ${p.Nom} - ${p.ActivityName} - ${p.EstValide ? 'Validé' : 'En attente'}`);
    });

    await connection.end();
    console.log('✅ Done!');

  } catch (error) {
    console.error('❌ Error:', error.message);
  }
}

createTestData();