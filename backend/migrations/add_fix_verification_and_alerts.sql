-- ================================================================
-- Migration: fix-verification-loop fields on clusters + proactive
-- alert webhook on profiles.
-- Run this once in Supabase SQL Editor (or psql)
-- ================================================================

-- 1. Cluster regression detection — richer than the original boolean flag.
ALTER TABLE clusters
  ADD COLUMN IF NOT EXISTS regression_confidence DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS regression_match_method TEXT,
  ADD COLUMN IF NOT EXISTS regression_resolved_at TIMESTAMPTZ;

-- 2. Proactive alerting — one webhook URL per user, format (Slack vs
--    Discord) auto-detected at send time from the URL itself.
ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS alert_webhook_url TEXT,
  ADD COLUMN IF NOT EXISTS alerts_enabled BOOLEAN NOT NULL DEFAULT true;

-- 3. Verify
SELECT id, regression_detected, regression_confidence, regression_match_method
FROM clusters WHERE regression_detected = true LIMIT 10;

SELECT id, email, alert_webhook_url, alerts_enabled FROM profiles LIMIT 10;
