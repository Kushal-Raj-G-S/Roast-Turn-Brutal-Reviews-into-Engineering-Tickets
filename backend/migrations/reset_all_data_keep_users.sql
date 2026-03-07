-- ================================================================
-- RESET ALL DATA (Keep Users Only)
-- ================================================================
-- This script clears all upload/analysis data while preserving user profiles.
-- Run this in Supabase SQL Editor to start fresh for testing.
--
-- ⚠️ WARNING: This will DELETE ALL your upload data permanently!
-- ================================================================

-- Show counts before deletion (for confirmation)
SELECT 'Before deletion:' as status;
SELECT 'user_monthly_usage' as table_name, COUNT(*) as count FROM user_monthly_usage WHERE 1=1
UNION ALL
SELECT 'uploads', COUNT(*) FROM uploads WHERE 1=1
UNION ALL
SELECT 'clusters', COUNT(*) FROM clusters WHERE 1=1
UNION ALL
SELECT 'reviews', COUNT(*) FROM reviews WHERE 1=1
UNION ALL
SELECT 'user_statistics', COUNT(*) FROM user_statistics WHERE 1=1
UNION ALL
SELECT 'profiles (PRESERVED)', COUNT(*) FROM profiles WHERE 1=1;

-- ================================================================
-- DELETE ALL DATA (cascades will handle related records)
-- ================================================================

-- 1. Clear usage tracking (plan enforcement data)
DELETE FROM user_monthly_usage;

-- 2. Clear uploads (this will CASCADE to clusters and reviews due to FK constraints)
DELETE FROM uploads;

-- 3. Clear user_statistics (if any exist)
DELETE FROM user_statistics;

-- ================================================================
-- Verify deletion
-- ================================================================

SELECT 'After deletion:' as status;
SELECT 'user_monthly_usage' as table_name, COUNT(*) as count FROM user_monthly_usage WHERE 1=1
UNION ALL
SELECT 'uploads', COUNT(*) FROM uploads WHERE 1=1
UNION ALL
SELECT 'clusters', COUNT(*) FROM clusters WHERE 1=1
UNION ALL
SELECT 'reviews', COUNT(*) FROM reviews WHERE 1=1
UNION ALL
SELECT 'user_statistics', COUNT(*) FROM user_statistics WHERE 1=1
UNION ALL
SELECT 'profiles (PRESERVED)', COUNT(*) FROM profiles WHERE 1=1;

-- ================================================================
-- Reset sequences (optional - starts IDs from 1 again)
-- ================================================================

-- Uncomment these if you want upload IDs to start from 1 again:
-- ALTER SEQUENCE uploads_id_seq RESTART WITH 1;
-- ALTER SEQUENCE clusters_id_seq RESTART WITH 1;
-- ALTER SEQUENCE user_monthly_usage_id_seq RESTART WITH 1;

SELECT '✅ All data cleared! Users preserved. Ready for testing.' as result;
