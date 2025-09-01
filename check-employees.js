const db = require('./models');

async function checkEmployees() {
  try {
    await db.sequelize.authenticate();
    console.log('✅ Database connected');

    const employes = await db.Employes.findAll({
      attributes: ['ID', 'Nom', 'Prenom', 'Surnom'],
      limit: 10
    });

    console.log('👥 Employees available:');
    employes.forEach(emp => {
      console.log(`ID: ${emp.ID}, Nom: ${emp.Nom}, Prenom: ${emp.Prenom}, Surnom: ${emp.Surnom}`);
    });

    console.log('\n🔍 Checking specific user Tsilavina...');
    const tsilavina = await db.Employes.findOne({
      where: { Surnom: 'Tsilavina' },
      attributes: ['ID', 'Nom', 'Prenom', 'Surnom']
    });

    if (tsilavina) {
      console.log('✅ Found Tsilavina:', tsilavina.toJSON());
    } else {
      console.log('❌ Tsilavina not found');
    }

  } catch (error) {
    console.error('❌ Error:', error.message);
  } finally {
    await db.sequelize.close();
    process.exit(0);
  }
}

checkEmployees();