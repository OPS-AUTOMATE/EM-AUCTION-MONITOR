# Implementation Plan: Auction Scraper Bot

## Phase 1: Environment & Foundational Setup (Week 1)

1. **Infrastructure Setup:**
   - Initialize a Next.js project for the Dashboard.
   - Set up a Supabase project (Auth + Database + Realtime).
   - Configure Database Schema:
     - `users`: User profiles.
     - `auctions`: Fields: `item_name`, `current_bid`, `time_remaining`, `bidders`, `status`, `user_id`, `url`, etc.
2. **Authentication:**
   - Implement Login/Signup flow in Next.js.
   - Set up Row Level Security (RLS) in Supabase to ensure users only see their own items.

## Phase 2: Core Scraping Engine (Week 1-2)

1. **Python Scraper Module:**
   - Create a modular scraper using `Playwright` with the `playwright-stealth` plugin.
   - Implement generic collectors for the 15+ target sites.
   - **Anti-Bot Strategy:** Integrate residential proxy rotation and randomized user-agent strings.
2. **Background Task Runner:**
   - Use a simple Python orchestrator to loop through the "Active Items" in the database.
   - Implement a priority queue (Items ending sooner get checked more frequently).

## Phase 3: Dashboard Development (Week 2)

1. **Real-time UI:**
   - Build the main dashboard using a "Live Grid" layout.
   - Use Supabase `.subscribe()` to update the UI the moment the scraper writes to the DB.
2. **Local Countdown Logic:**
   - Implement a Javascript-based countdown that calculates time remaining locally to avoid constant API calls for the timer.
3. **Item Management:**
   - "Add Item" modal with URL validation.
   - "Remove" button and total items tracked indicator.

## Phase 4: Lifecycle & Logic (Week 3)

1. **Expiration Logic:**
   - Background worker to mark items as "Expired" based on closing time.
   - Automated cleanup job to soft-delete items older than 48 hours post-expiry.
2. **Error Handling & Stability:**
   - Auto-retry for failed scrapes.
   - Monitoring dashboard (Internal) to see if any site changed its layout (scraping breakages).

## Phase 5: Deployment & Polish (Week 3-4)

1. **VPS Deployment:**
   - Deploy Next.js to Vercel or VPS.
   - Deploy Scraper as a Dockerized background service on a VPS.
2. **Premium Polish:**
   - Final CSS styling for "WOW" factor (Glassmorphism, Dark mode, Animation for bid changes).
   - Final testing with real auction links.

---

## Technical Challenges & Mitigations

- **Site Layout Changes:** Auction sites update their UI frequently. **Mitigation:** Modular scraper architecture where each site has its own isolated "Parser" file.
- **Heavy Anti-Bot (GSA/BidSpotter):** **Mitigation:** Use Playwright in "Headful" mode on the server (via Xvfb) and high-quality residential proxies.
- **Concurrent Load:** 150 items checked every minute. **Mitigation:** Use a lightweight worker pool in Python (asyncio) to run multiple scrapers in parallel.
