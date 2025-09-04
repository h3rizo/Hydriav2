const { supabase } = require('./supabaseClient');

async function checkEmployees() {
  try {
    // Test Supabase connection
    const { error: connectionError } = await supabase.from('employes').select('count').limit(1);
    if (connectionError) throw connectionError;
    console.log('✅ Supabase connected');

    const { data: employes, error } = await supabase
      .from('employes')
      .select('id, nom, prenom, surnom')
      .limit(10);

    if (error) throw error;

    console.log('👥 Employees available:');
    (employes || []).forEach(emp => {
      console.log(`ID: ${emp.id}, Nom: ${emp.nom}, Prenom: ${emp.prenom}, Surnom: ${emp.surnom}`);
    });

    console.log('\n🔍 Checking specific user Tsilavina...');
    const { data: tsilavina, error: tsilError } = await supabase
      .from('employes')
      .select('id, nom, prenom, surnom')
      .eq('surnom', 'Tsilavina')
      .single();

    if (tsilError && tsilError.code !== 'PGRST116') {
      throw tsilError;
    }

    if (tsilavina) {
      console.log('✅ Found Tsilavina:', tsilavina);
    } else {
      console.log('❌ Tsilavina not found');
    }

  } catch (error) {
    console.error('❌ Error:', error.message);
  } finally {
    process.exit(0);
  }
}

checkEmployees();