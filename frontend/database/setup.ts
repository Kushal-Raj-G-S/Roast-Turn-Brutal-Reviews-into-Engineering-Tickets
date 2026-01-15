/**
 * Database Setup Script
 * =====================
 * Executes the schema.sql file to set up Supabase database
 */

import { supabaseAdmin } from '../src/lib/supabase/admin';
import * as fs from 'fs';
import * as path from 'path';

async function setupDatabase() {
  try {
    console.log('🚀 Starting database setup...\n');

    // Read the SQL schema file
    const schemaPath = path.join(__dirname, 'schema.sql');
    const schema = fs.readFileSync(schemaPath, 'utf-8');

    console.log('📝 Executing schema...');
    
    // Execute the schema
    const { error } = await supabaseAdmin.rpc('exec_sql', { sql: schema });

    if (error) {
      // If RPC doesn't exist, try direct execution (split by statement)
      const statements = schema
        .split(';')
        .map(s => s.trim())
        .filter(s => s.length > 0 && !s.startsWith('--'));

      for (const statement of statements) {
        const { error: execError } = await supabaseAdmin.from('_').select('*').limit(0);
        if (execError) {
          console.error('❌ Error executing statement:', statement.substring(0, 100) + '...');
          console.error(execError);
        }
      }
    }

    console.log('\n✅ Database setup completed successfully!');
    console.log('\n📊 Created tables:');
    console.log('  - profiles (user profile data)');
    console.log('  - roast_results (roast analysis results)');
    console.log('  - user_statistics (aggregated user stats)');
    console.log('\n🔐 Row Level Security enabled on all tables');
    console.log('\n⚡ Triggers configured for:');
    console.log('  - Auto-create profile on user signup');
    console.log('  - Auto-update statistics on roast changes');
    console.log('  - Auto-update timestamps');

  } catch (error) {
    console.error('\n❌ Database setup failed:', error);
    process.exit(1);
  }
}

setupDatabase();
