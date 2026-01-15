-- ROAST Application Database Schema
-- ===================================
-- This SQL script creates all necessary tables for the ROAST application

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================
-- PROFILES TABLE
-- =====================
-- Extends Supabase auth.users with additional user profile data
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT UNIQUE NOT NULL,
  full_name TEXT,
  avatar_url TEXT,
  provider TEXT, -- 'google', 'github', 'email'
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- RLS Policies for profiles
CREATE POLICY "Users can view their own profile" 
  ON public.profiles FOR SELECT 
  USING (auth.uid() = id);

CREATE POLICY "Users can update their own profile" 
  ON public.profiles FOR UPDATE 
  USING (auth.uid() = id);

-- =====================
-- ROAST RESULTS TABLE
-- =====================
-- Stores all roast analysis results
CREATE TABLE IF NOT EXISTS public.roast_results (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  
  -- Original Review Data
  review_text TEXT NOT NULL,
  original_rating NUMERIC(2,1) CHECK (original_rating >= 1.0 AND original_rating <= 5.0),
  reviewer_name TEXT,
  review_date TIMESTAMPTZ,
  
  -- Roast Analysis Results
  roast_summary TEXT,
  sentiment_score NUMERIC(3,2) CHECK (sentiment_score >= -1.0 AND sentiment_score <= 1.0),
  toxicity_level TEXT CHECK (toxicity_level IN ('low', 'medium', 'high', 'extreme')),
  key_issues JSONB, -- Array of detected issues
  
  -- AI Response
  ai_response TEXT,
  suggested_reply TEXT,
  improvement_suggestions JSONB,
  
  -- Status & Metadata
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  ticket_number TEXT UNIQUE,
  is_resolved BOOLEAN DEFAULT FALSE,
  resolved_at TIMESTAMPTZ,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE public.roast_results ENABLE ROW LEVEL SECURITY;

-- RLS Policies for roast_results
CREATE POLICY "Users can view their own roast results" 
  ON public.roast_results FOR SELECT 
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own roast results" 
  ON public.roast_results FOR INSERT 
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own roast results" 
  ON public.roast_results FOR UPDATE 
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own roast results" 
  ON public.roast_results FOR DELETE 
  USING (auth.uid() = user_id);

-- =====================
-- USER STATISTICS TABLE
-- =====================
-- Aggregated statistics for user dashboard
CREATE TABLE IF NOT EXISTS public.user_statistics (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
  
  total_reviews_analyzed INTEGER DEFAULT 0,
  total_issues_found INTEGER DEFAULT 0,
  total_issues_resolved INTEGER DEFAULT 0,
  average_sentiment_score NUMERIC(3,2),
  
  -- Rating Distribution
  rating_1_count INTEGER DEFAULT 0,
  rating_2_count INTEGER DEFAULT 0,
  rating_3_count INTEGER DEFAULT 0,
  rating_4_count INTEGER DEFAULT 0,
  rating_5_count INTEGER DEFAULT 0,
  
  -- Performance Metrics
  average_resolution_time_hours NUMERIC(10,2),
  satisfaction_improvement_percentage NUMERIC(5,2),
  
  last_analysis_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE public.user_statistics ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view their own statistics" 
  ON public.user_statistics FOR SELECT 
  USING (auth.uid() = user_id);

CREATE POLICY "Users can update their own statistics" 
  ON public.user_statistics FOR UPDATE 
  USING (auth.uid() = user_id);

-- =====================
-- INDEXES
-- =====================
CREATE INDEX IF NOT EXISTS idx_roast_results_user_id ON public.roast_results(user_id);
CREATE INDEX IF NOT EXISTS idx_roast_results_created_at ON public.roast_results(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_roast_results_status ON public.roast_results(status);
CREATE INDEX IF NOT EXISTS idx_roast_results_ticket_number ON public.roast_results(ticket_number);

-- =====================
-- FUNCTIONS & TRIGGERS
-- =====================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_profiles_updated_at 
  BEFORE UPDATE ON public.profiles 
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_roast_results_updated_at 
  BEFORE UPDATE ON public.roast_results 
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_statistics_updated_at 
  BEFORE UPDATE ON public.user_statistics 
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to create user profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, avatar_url, provider)
  VALUES (
    NEW.id,
    NEW.email,
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'avatar_url',
    NEW.raw_app_meta_data->>'provider'
  );
  
  -- Initialize user statistics
  INSERT INTO public.user_statistics (user_id)
  VALUES (NEW.id);
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to auto-create profile on user signup
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Function to update user statistics when roast result changes
CREATE OR REPLACE FUNCTION public.update_user_stats()
RETURNS TRIGGER AS $$
BEGIN
  -- Update statistics when a roast result is created or updated
  UPDATE public.user_statistics
  SET
    total_reviews_analyzed = (
      SELECT COUNT(*) FROM public.roast_results WHERE user_id = NEW.user_id
    ),
    total_issues_found = (
      SELECT SUM(jsonb_array_length(COALESCE(key_issues, '[]'::jsonb)))
      FROM public.roast_results WHERE user_id = NEW.user_id
    ),
    total_issues_resolved = (
      SELECT COUNT(*) FROM public.roast_results 
      WHERE user_id = NEW.user_id AND is_resolved = TRUE
    ),
    average_sentiment_score = (
      SELECT AVG(sentiment_score) FROM public.roast_results 
      WHERE user_id = NEW.user_id AND sentiment_score IS NOT NULL
    ),
    last_analysis_at = NOW()
  WHERE user_id = NEW.user_id;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update stats on roast result changes
CREATE TRIGGER update_stats_on_roast_change
  AFTER INSERT OR UPDATE ON public.roast_results
  FOR EACH ROW EXECUTE FUNCTION public.update_user_stats();
