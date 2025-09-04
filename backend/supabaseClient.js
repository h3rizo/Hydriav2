const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl || !supabaseKey) {
  throw new Error('Supabase URL and service key are required. Please check your .env file.');
}

// On utilise la clé de service côté serveur pour avoir tous les droits
const supabase = createClient(supabaseUrl, supabaseKey);

module.exports = { supabase };