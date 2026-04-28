# Vercel Deployment Guide

## Overview
LicorScan frontend is deployed on Vercel as a static site with dynamic catalog data. The frontend reads product data from Supabase directly or from a cached `catalog-data.js` file.

## Prerequisites
- Vercel account (free or paid): https://vercel.com
- GitHub repository linked to Vercel
- Supabase project credentials

## Step 1: Set Up Vercel Environment Variables

In your Vercel project dashboard (`vercel.com/dashboard`):

1. Go to **Settings → Environment Variables**
2. Add these variables:

| Variable | Value | Environment |
|----------|-------|------------|
| `SUPABASE_URL` | `https://bwxxifwqnkrfbegoycod.supabase.co` | Production |
| `SUPABASE_ANON` | `sb_publishable_...` (public key) | Production |
| `SUPABASE_KEY` | `sb_secret_...` (optional, for backend jobs) | Production |

**Note:** The anon key is safe to expose in frontend code since Supabase RLS policies protect data.

## Step 2: Deploy to Vercel

### Option A: GitHub Integration (Recommended)
1. Push your code to GitHub: `git push origin main`
2. Log in to Vercel at https://vercel.com
3. Click **Add New → Project**
4. Select your LicorScan GitHub repository
5. Vercel auto-detects `vercel.json` and deploys
6. Once deployed, your site is live at `https://licorscan.vercel.app` (or custom domain)

### Option B: Vercel CLI
```bash
# Install Vercel CLI (global or local)
npm install -g vercel

# Link your project
vercel link

# Deploy
vercel --prod
```

## Step 3: Configure Frontend to Use Supabase

The frontend currently reads from `catalog-data.js`. To enable real-time data from Supabase:

Edit `frontend/index.html` to add Supabase client (example):

```javascript
// Add this after React imports:
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>

// In your React component:
const supabaseUrl = window.__SUPABASE_URL__ || process.env.REACT_APP_SUPABASE_URL;
const supabaseAnonKey = window.__SUPABASE_ANON__ || process.env.REACT_APP_SUPABASE_ANON;

const supabase = window.supabase.createClient(supabaseUrl, supabaseAnonKey);

// Fetch products from Supabase instead of static file:
const { data: products } = await supabase
  .from('products')
  .select('*')
  .limit(1000);
```

Or keep the static approach and update `catalog-data.js` on a schedule (backend cron job).

## Step 4: Enable CI/CD for Catalog Updates

### Option 1: GitHub Actions (Auto-deploy on new catalog)
Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Vercel on Catalog Update

on:
  push:
    branches: [main]
    paths:
      - 'frontend/catalog-data.js'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: vercel/action@main
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
```

### Option 2: Manual Backend Cron
- Backend VM runs scraper → `build_front_catalog.py` → `git commit` + push
- Vercel redeploys automatically (GitHub webhook triggers)

## Step 5: Monitor & Logs

- **Vercel Dashboard:** View deployment history, logs, and performance
- **Supabase Console:** Check products table for real-time data
- **Frontend:** Open browser DevTools → Console to verify Supabase connection

## Rollback
If deployment has issues:
```bash
# View deployment history
vercel list

# Promote a previous deployment to production
vercel rollback
```

## Custom Domain (Optional)

1. In Vercel dashboard: **Settings → Domains**
2. Add your domain (e.g., `licorscan.com`)
3. Update DNS records as instructed

---

## Summary

| Component | Location | Update Frequency |
|-----------|----------|-----------------|
| Frontend (HTML + React) | Vercel CDN | On git push |
| Catalog Data | `frontend/catalog-data.js` | Daily (backend cron) |
| Products DB | Supabase `products` table | Daily (backend scraper) |

**Next Steps:**
1. Push repo to GitHub
2. Link Vercel to GitHub repo
3. Add environment variables to Vercel
4. Deploy
5. Set up backend VM for automated catalog updates
