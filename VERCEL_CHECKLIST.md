# Vercel Deployment Checklist

## Phase 1: Local Verification ✅

- [x] `frontend/index.html` - React SPA with Supabase integration
- [x] `frontend/catalog-data.js` - Auto-generated catalog (2984 products)
- [x] `package.json` - Node.js metadata for Vercel
- [x] `vercel.json` - Vercel configuration (static site, env vars, caching)
- [x] `.vercelignore` - Ignore Python/backend files on Vercel
- [x] `DEPLOY.md` - Deployment guide with step-by-step instructions
- [x] GitHub Actions workflow (`.github/workflows/deploy-vercel.yml`)
- [x] `README.md` - Updated with deployment architecture

## Phase 2: Prepare for Vercel Deployment

### On GitHub
1. [ ] Push all changes to GitHub:
   ```bash
   git add .
   git commit -m "Setup Vercel deployment with systemd backend automation"
   git push origin main
   ```

### On Vercel
1. [ ] Create Vercel account: https://vercel.com
2. [ ] Click "Add New" → "Project"
3. [ ] Select LicorScan GitHub repository
4. [ ] Vercel auto-detects `vercel.json` (framework: Other, root: `.`)
5. [ ] Click "Deploy"
6. [ ] Wait for build to complete (~30s)

### Environment Variables in Vercel
1. [ ] Go to Project Settings → "Environment Variables"
2. [ ] Add for **Production** environment:
   - `SUPABASE_URL` = `https://bwxxifwqnkrfbegoycod.supabase.co`
   - `SUPABASE_ANON` = `sb_publishable_3g_CcUcp3WI890zg0IGPeg_zI9j1QCq` (public key)
3. [ ] Redeploy to apply env vars: "Deployments" tab → click latest → "Redeploy"

### GitHub Secrets for CI/CD
1. [ ] Go to GitHub: Settings → Secrets and variables → Actions
2. [ ] Create these secrets:
   - `VERCEL_TOKEN`: Get from https://vercel.com/account/tokens → Create Token
   - `VERCEL_ORG_ID`: View on Vercel dashboard (Account Settings → Team ID)
   - `VERCEL_PROJECT_ID`: Find in Vercel project → Settings → Project ID

### Test Frontend Deployment
1. [ ] Open your Vercel URL (e.g., `https://licorscan.vercel.app`)
2. [ ] Verify:
   - Page loads (React app visible)
   - Catalog data loads (products display)
   - Comparison drawer works
   - Minimize toggle works
3. [ ] Check browser console for errors (should be clean)

## Phase 3: Backend VM Setup (Optional but Recommended)

### VM Provisioning
1. [ ] Choose provider: AWS EC2 / DigitalOcean / GCP / Linode
2. [ ] Launch Ubuntu 22.04+ instance (t2.micro free tier OK)
3. [ ] SSH into VM
4. [ ] Follow [BACKEND_VM_SETUP.md](BACKEND_VM_SETUP.md):
   - [ ] Install Python 3.11+, Git, Playwright
   - [ ] Clone repo and setup venv
   - [ ] Create `.env` with credentials (Supabase, GitHub)
   - [ ] Copy `licorscan.service` and `licorscan.timer` to `/etc/systemd/system/`
   - [ ] Enable timer: `sudo systemctl enable licorscan.timer`
   - [ ] Test: `sudo systemctl start licorscan.service` and check logs

### First Automated Run
1. [ ] VM trigger manual test: `sudo systemctl start licorscan.service`
2. [ ] Monitor logs: `journalctl -u licorscan.service -f`
3. [ ] Wait ~5-10 minutes for completion
4. [ ] Verify:
   - [ ] Scraper ran (check logs)
   - [ ] Catalog built (check `frontend/catalog-data.js` timestamp)
   - [ ] Uploaded to Supabase (check product count in dashboard)
   - [ ] Auto-pushed to GitHub (check GitHub commit history)
   - [ ] Vercel redeployed (check deployment log)

### Daily Schedule Activation
1. [ ] Verify timer is active: `sudo systemctl status licorscan.timer`
2. [ ] Check schedule: `sudo systemctl list-timers licorscan.timer`
3. [ ] System will run at 02:00 GMT-5 daily (UTC 07:00)

## Phase 4: Monitor & Iterate

### Vercel Dashboard
- View deployments, logs, and analytics
- Custom domain setup (optional)
- Rollback if needed: "Deployments" tab

### Supabase Console
- Check `products` table for latest data
- Monitor row count and updated_at timestamps
- View query usage and API statistics

### VM Logs
- `tail -f /var/log/licorscan/scraper.log`
- Check for errors in Supabase upload or git push
- Monitor disk space and VM performance

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Frontend blank page | Check env vars in Vercel; check browser console for JS errors |
| Products not showing | Verify `SUPABASE_ANON` in env vars; check Supabase RLS policies (should allow public read) |
| VM job never runs | `sudo journalctl -u licorscan.timer -n 50`; check systemd timer syntax |
| Git push fails | Verify GitHub token in VM `.env`; check SSH key or use HTTPS token |
| Supabase upload timeout | Increase VM timeout or reduce batch size (200 products default) |

---

## Next Steps

1. **Immediate (today):**
   - Commit Vercel config files
   - Push to GitHub
   - Deploy to Vercel via GitHub integration
   - Test frontend URL

2. **Short-term (this week):**
   - Provision VM (AWS, DigitalOcean, etc.)
   - Deploy backend automation
   - Run first manual test
   - Verify daily schedule works

3. **Long-term (ongoing):**
   - Monitor Vercel + Supabase dashboards
   - Review daily logs for errors
   - Optimize scraper if needed
   - Plan for custom domain + SSL

---

For detailed instructions, see [DEPLOY.md](DEPLOY.md) and [BACKEND_VM_SETUP.md](BACKEND_VM_SETUP.md).
