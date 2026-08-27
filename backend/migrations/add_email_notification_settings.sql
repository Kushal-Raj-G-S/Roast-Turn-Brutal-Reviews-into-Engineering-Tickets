-- ================================================================
-- Migration: email notification toggle + weekly digest opt-in on
-- profiles, independent of the existing webhook/push alerts_enabled
-- flag (a user can want email off while keeping Discord/push on, or
-- vice versa).
-- Run this once in Supabase SQL Editor (or psql)
-- ================================================================

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS email_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS weekly_digest_enabled BOOLEAN NOT NULL DEFAULT true;

-- Verify
SELECT id, email, email_alerts_enabled, weekly_digest_enabled FROM profiles LIMIT 10;
