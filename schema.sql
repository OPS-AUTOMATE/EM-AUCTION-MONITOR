-- Database Schema for Auction Bot

-- Create a table for users (if not using Supabase Auth's default)
-- CREATE TABLE IF NOT EXISTS public.profiles (
--   id UUID REFERENCES auth.users ON DELETE CASCADE PRIMARY KEY,
--   email TEXT UNIQUE,
--   created_at TIMESTAMPTZ DEFAULT NOW()
-- );

-- Main Auctions Table
CREATE TABLE IF NOT EXISTS public.auctions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  url TEXT NOT NULL,
  
  -- Item Details
  item_name TEXT,
  current_bid NUMERIC(15, 2),
  currency TEXT DEFAULT 'USD',
  premium_percentage NUMERIC(5, 2),
  total_bidders INTEGER DEFAULT 0,
  auction_name TEXT,
  city TEXT,
  state TEXT,
  serial_number TEXT,
  website_name TEXT,
  
  -- Timing
  closing_time TIMESTAMPTZ,
  time_remaining_str TEXT, -- Original string from site
  last_scraped_at TIMESTAMPTZ DEFAULT NOW(),
  last_closing_check_at TIMESTAMPTZ DEFAULT NOW(),
  
  -- Lifecycle Status
  status TEXT DEFAULT 'pending' CHECK (status IN ('active', 'paused', 'pending', 'error', 'expired')),
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  is_deleted BOOLEAN DEFAULT FALSE -- Soft delete for safety
);

-- Enable Realtime for the auctions table
ALTER PUBLICATION supabase_realtime ADD TABLE auctions;

-- Row Level Security (RLS)
ALTER TABLE public.auctions ENABLE ROW LEVEL SECURITY;

-- Policies: Users can only see/edit their own data
CREATE POLICY "Users can view their own auctions" ON public.auctions
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own auctions" ON public.auctions
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own auctions" ON public.auctions
  FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own auctions" ON public.auctions
  FOR DELETE USING (auth.uid() = user_id);
