-- ================================================================
-- Create user_monthly_usage table for proper plan enforcement
-- ================================================================

CREATE TABLE IF NOT EXISTS user_monthly_usage (
  id SERIAL PRIMARY KEY,
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  year_month TEXT NOT NULL, -- "2026-03" format
  uploads_used INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  -- Ensure one record per user per month
  UNIQUE(user_id, year_month)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_user_monthly_usage_user_month 
  ON user_monthly_usage(user_id, year_month);

-- Auto-update timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_user_monthly_usage_updated_at 
  BEFORE UPDATE ON user_monthly_usage 
  FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();