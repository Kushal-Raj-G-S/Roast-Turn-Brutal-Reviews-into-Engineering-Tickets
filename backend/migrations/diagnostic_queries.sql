-- ============================================================
-- DIAGNOSTIC QUERIES FOR SUPABASE
-- Run these one by one in Supabase SQL Editor to diagnose FK issue
-- ============================================================

-- Query 1: Check if user_monthly_usage table exists
-- Expected: Should return FALSE (table doesn't exist yet)
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'user_monthly_usage'
) as user_monthly_usage_exists;

-- Query 2: List all public tables
-- Expected: Should see profiles, uploads, clusters, reviews, etc.
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name;

-- Query 3: Check profiles table columns
-- Expected: Should see id (uuid), email, full_name, plan, etc.
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' 
AND table_name = 'profiles'
ORDER BY ordinal_position;

-- Query 4: Check all foreign keys that reference profiles table
-- Expected: Should see uploads.user_id and other columns
SELECT
    tc.table_name, 
    kcu.column_name,
    tc.constraint_name
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
  AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' 
AND ccu.table_name = 'profiles';

-- ============================================================
-- INTERPRETATION:
-- ============================================================
-- If Query 1 returns FALSE:
--   → user_monthly_usage table does NOT exist
--   → This is the root cause of your 500 error
--   → Solution: Run create_user_monthly_usage.sql
--
-- If Query 1 returns TRUE:
--   → Table exists but FK might be misconfigured
--   → Check the results of Query 4
--   → May need to drop and recreate the table
-- ============================================================
