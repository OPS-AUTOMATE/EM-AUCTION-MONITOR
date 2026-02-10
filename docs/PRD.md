# Product Requirement Document (PRD): Real-Time Auction Scraper Bot

## 1. Project Overview

A multi-user, real-time auction scraping dashboard designed for medical equipment procurement. The system allows users to track specific auction items across multiple platforms (GSA, BidSpotter, DotMed, etc.) with live updates on bids, bidders, and time remaining.

## 2. Target Audience

- Internal team members (3-5 users max).
- Each user tracks 20-30 items concurrently.

## 3. Core Features

### 3.1 User Management & Isolation

- **Authentication:** Secure login (Email/Password) to identify users.
- **Data Isolation:** Users can only see and manage their own list of tracked auction items.
- **Dashboard:** A personalized view of active and recently expired auctions.

### 3.2 Real-Time Scraping Engine

- **Multi-Site Support:** Support for 15+ auction websites (GSA, Centurion, British Medical, etc.).
- **Data Fields to Extract:**
  - Item Name
  - Ending (Sorted by nearest expiration)
  - Current Bid (USD/Local Currency)
  - Premium % (Buyer's premium)
  - Direct Link to Item
  - Total Bidders
  - Auction Name
  - City & State
  - Closing Time
  - Time Remaining (Local countdown)
  - Serial Number
  - Website Name
- **Smart Refresh:**
  - Real-time updates for bid costs and bidder counts.and a frequent refresh for  time remaining or closing time. in case anyone get updated. Maybe check very 6 hours.
  - Local browser-side countdown timer for "Time Remaining" to minimize server requests.

### 3.3 Auction Lifecycle Management

- **Add Item:** Users paste a URL into the list to start tracking.
- **Auto-Removal:** Items are automatically hidden 48 hours after the auction expires.
- **Manual Control:** A "Remove" button to clear items from the dashboard manually. for each item and for bulk remove too.

User can stop/resume/delete/start each item scrapping indivuidally. make sure its process is handled along with it properly. no memory leakage. no server over whelming.

### 3.4 Concurrency & Scaling

- **Concurrent Scraping:** Support for tracking ~150 items simultaneously across the team. (Use a proper logic for not creating race conditions or memory leakage issue. or any kind of locks. Handle the processes logically and implementically correct. prperly sync to enable robust and performance optimized implementation.)
- **Anti-Bot Protection:** Implementation of stealth browser techniques and proxy rotation to prevent IP bans from government and commercial auction sites. Handle the captcha, cloudlfare turnstile and things like this automatically. but try to handle this with minimum latency. as we need realtime results as much as possible but with the atleast bearable minimum latency which is requried for the system to work.

---

## 4. Technical Stack Proposal

| Component      | Technology                 | Rationale                                                                   |
| :------------- | :------------------------- | :-------------------------------------------------------------------------- |
| **Frontend**   | **Next.js (React)**        | Fast, SEO-friendly, and allows for premium, responsive UI.                  |
| **Backend/DB** | **Supabase**               | Provides Auth, Real-time DB (PostgreSQL), and easy data isolation rules.    |
| **Scraper**    | **Python + Playwright**    | Best-in-class for handling JS-heavy auction sites and anti-bot stealth.     |
| **Styling**    | **Vanilla CSS / Radix UI** | For a high-end, custom professional dashboard look.                         |
| **Real-time**  | **Supabase Realtime**      | Instantly syncs scraper updates to the user's dashboard without refreshing. |

---

## 5. Deployment Recommendation

### **Centralized Cloud Server (VPS)**

- **Why:** Reliability. The bot needs to run 24/7 to catch last-minute bid changes. A laptop-based app would stop if the laptop is closed or disconnected.
- **Platform:** DigitalOcean (Basic $12-20 droplet) or AWS Lightsail.

---

## 6. Success Metrics

- **Latency:** Bid updates reflected in the UI within 10-30 seconds of the source change.
- **Reliability:** 99% uptime of scraping tasks without getting blocked by target sites.
- **UI/UX:** Zero manual refresh required for active auction monitoring.

What are your thoughts about using .NET framework. is this suitable? reliable? performance optimized?
have you think about applying your suggested approach and will it work issue lessly with the server. Maybe i use digital ocean droplet.
