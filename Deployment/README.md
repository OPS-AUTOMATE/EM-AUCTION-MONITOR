# Deployment Guide: Auction Bot

This guide explains how to deploy the Scraper and Dashboard on a VPS (e.g., DigitalOcean, AWS, Linode).

## 1. Prerequisites

- A Linux VPS with **Docker** and **Docker Compose** installed.
- A **Supabase** project (URL and API Keys).
- A domain or subdomain (e.g., `auction.yourdomain.com`).

## 2. Server Setup

### Clone the Repository

```bash
git clone https://github.com/OPS-AUTOMATE/EM-AUCTION-MONITOR.git
cd auction-bot
```

### Configure Environment Variables

1. **Scraper**:
   Create `Scraper/.env`:

   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
   ```

2. **Dashboard**:
   Create `Dashboard/.env.local`:

   ```env
   NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
   ```

## 3. Deploy with Docker Compose

Run the following command in the root directory:

```bash
docker-compose up -d --build
```

This will:

- Build the Next.js Dashboard.
- Build the Python Scraper.
- Launch Chromium inside the container.
- Start monitoring the database.

## 4. Nginx Reverse Proxy

Copy the content of `Deployment/nginx.conf` to your Nginx sites-available:

```bash
sudo cp Deployment/nginx.conf /etc/nginx/sites-available/auction-bot
sudo ln -s /etc/nginx/sites-available/auction-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 5. SSL (Recommended)

Use Certbot to get a free SSL certificate:

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d auction.yourdomain.com
```

## 6. Verification

- Visit `auction.yourdomain.com` and log in.
- Add a GSA link.
- Check the Scraper logs: `docker-compose logs -f scraper`.

---

### Managing the Bot

- **Update code**: `git pull` then `docker-compose up -d --build`.
- **Stop everything**: `docker-compose down`.
- **Check health**: `docker ps`.
