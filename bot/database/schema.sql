-- Intelligent Auction Monitoring System (IAMS) - Schema
-- This schema defines the single source of truth for auction monitoring state.

CREATE TABLE IF NOT EXISTS auction_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    site_key TEXT,              -- e.g. 'bidspotter', 'gsa', 'centurion'
    url TEXT NOT NULL,

    -- Auction data (latest snapshot)
    item_name TEXT DEFAULT 'Syncing...',
    current_bid NUMERIC DEFAULT 0,
    premium_percentage NUMERIC DEFAULT 15,
    total_bidders INTEGER DEFAULT 0,
    closing_time TIMESTAMPTZ,   -- High frequency updates based on this
    time_remaining_str TEXT DEFAULT 'Starting Sync...',
    city TEXT,
    state TEXT,
    website_name TEXT,
    serial_number TEXT,
    
    -- State & Scheduling
    status TEXT DEFAULT 'active', -- active, paused, expired, error
    fetch_tier SMALLINT DEFAULT 0, -- 0=NORMAL, 1=CLOSING, 2=URGENT, 3=CRITICAL
    next_fetch_at TIMESTAMPTZ DEFAULT now(),
    last_scraped_at TIMESTAMPTZ,
    
    -- Concurrency & Identity
    locked_until TIMESTAMPTZ,
    session_id TEXT,            -- Sticky proxy session identity
    
    -- Error Reporting
    error_message TEXT,
    
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for Atomic Scheduling (FOR UPDATE SKIP LOCKED)
CREATE INDEX IF NOT EXISTS idx_auction_items_next_fetch ON auction_items (next_fetch_at);
CREATE INDEX IF NOT EXISTS idx_auction_items_locked_until ON auction_items (locked_until);
CREATE INDEX IF NOT EXISTS idx_auction_items_status_fetch ON auction_items (status, next_fetch_at);

-- Supabase RLS (Row Level Security) Implementation
-- To enable RLS for a specific user, uncomment the following:
-- ALTER TABLE auction_items ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Users can only see their own auction items" ON auction_items
-- FOR ALL USING (auth.uid() = user_id);
