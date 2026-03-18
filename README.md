# Auction Monitor Bot

A high-performance, automated auction monitoring system designed for **Eighteen Medical**. This project synchronizes auction data from multiple platforms, calculates premiums, and provides a premium real-time dashboard for administrators and users.

## 🚀 Key Features

- **Multi-Platform Syncing**: Support for over 15 auction platforms including:
    - GSA Auctions, BidSpotter, Centurion, GovPlanet, Purple Wave, Mazree, DotMed, BMA, AllSurplus, EquipNet, and more.
- **Real-Time Dashboard**: 
    - Master View for admins to monitor all items across all users.
    - User-level filtering for granular oversight.
    - Live updates via Supabase Realtime.
- **Robust Scrapers**: 
    - Tiered scanning (REST/HTML vs Playwright) for maximum reliability.
    - Session persistence for login-protected sites (Mazree).
- **Smart URL Validation**: Intelligent detection and validation of supported auction domains.
- **Premium Aesthetics**: Sleek dark-mode interface with glassmorphism and modern UI components.

## 🛠 Tech Stack

- **Dashboard**: 
    - Next.js 15+ (App Router)
    - TypeScript
    - Tailwind CSS (Vanilla CSS for custom glass effects)
    - Supabase (Auth, Database, Realtime)
    - Framer Motion (Animations)
    - Lucide React (Icons)
- **Bot/Engine**:
    - Python 3.10+
    - Playwright (Headless Browser Automation)
    - Supabase-py (Database client)
    - Request-based scrapers (Speed-optimized)

## 📁 Project Structure

```text
├── bot/                # Python-based auction monitoring engine
│   ├── adapters/       # Platform-specific scraping logic
│   ├── engine/         # Core worker and synchronization logic
│   ├── database/       # Database connection and queries
│   └── .sessions/      # Persistent login sessions (ignored by git)
├── dashboard/          # Next.js web application
│   ├── app/            # Frontend routes and logic
│   ├── utils/          # Constants, database browser client, helpers
│   └── public/         # Static assets
└── archive/            # Log and script backups (ignored by git)
```

## 🚗 Getting Started

### 1. Prerequisites
- Node.js 18+
- Python 3.10+
- Supabase Account

### 2. Setup Assistant (Bot)
```bash
cd bot
pip install -r requirements.txt
playwright install chromium
```
Configure environment variables in a `.env` file (see `bot/.env.example`).

### 3. Setup Dashboard
```bash
cd dashboard
npm install
npm run dev
```

## 🛡 Security & Maintenance

- Refer to [SECURITY.md](SECURITY.md) for vulnerability disclosure and safety standards.
- All scrapers follow a "Polite Crawling" policy to minimize server load on host auction sites.

## 📄 License
Privately developed for Eighteen Medical.
