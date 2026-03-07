-- ================================================================
-- Create user_monthly_usage table for proper plan enforcement
-- ================================================================

CREATE TABLE IF NOT EXISTS user_monthly_usage (
  id SERIAL PRIMARY KEY,
  user_id UUID NOT NULL,
  year_month TEXT NOT NULL, -- "2026-03" format
  uploads_used INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  -- Ensure one record per user per month
  UNIQUE(user_id, year_month),
  
  -- Foreign key to profiles (with proper schema reference)
  CONSTRAINT fk_user_monthly_usage_user_id 
    FOREIGN KEY (user_id) 
    REFERENCES public.profiles(id) 
    ON DELETE CASCADE
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_user_monthly_usage_user_month 
  ON user_monthly_usage(user_id, year_month);

-- Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_user_monthly_usage_updated_at ON user_monthly_usage;
CREATE TRIGGER update_user_monthly_usage_updated_at 
  BEFORE UPDATE ON user_monthly_usage 
  FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();