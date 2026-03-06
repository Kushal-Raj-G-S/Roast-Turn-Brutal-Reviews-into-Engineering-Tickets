-- ================================================================
-- Migration: add plan column to profiles
-- Run this once in Supabase SQL Editor (or psql)
-- ================================================================

-- 1. Add the plan column (safe to run more than once via IF NOT EXISTS)
ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free'
    CHECK (plan IN ('free', 'starter', 'pro', 'business', 'enterprise'));

-- 2. Backfill any existing rows that somehow slipped through without a value
UPDATE profiles SET plan = 'free' WHERE plan IS NULL;

-- 3. Verify
SELECT id, email, plan FROM profiles LIMIT 10;
