# Backend VM Setup Guide

## Overview
LicorScan backend runs on a VM with automated scraping, catalog generation, and Supabase syncing. This guide covers setup for Linux (Ubuntu 22.04+) or any Unix-like system with systemd.

## Architecture

```
VM (cron/systemd timers)
  ├── Daily 02:00 GMT-5: Scraper (exito, carulla, olimpica)
  ├── After Scraper: build_front_catalog.py (generate catalog-data.js)
  ├── After Build: upload_to_supabase.py (sync to Supabase)
  ├── After Success: git commit + push (triggers Vercel redeploy)
  └── Logs: /var/log/licorscan/ (for monitoring/debugging)
```

## Prerequisites

- Ubuntu 22.04+ or similar Linux
- Python 3.11+
- Git
- Playwright (async browser automation)
- Systemd (most Linux systems)
- Root or sudo access

## Step 1: VM Initial Setup

### 1.1 SSH and System Basics
```bash
# SSH into your VM
ssh ubuntu@your-vm-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.11 python3-pip git curl wget
```

### 1.2 Clone Repository
```bash
cd /opt  # or /home/ubuntu/
sudo git clone https://github.com/Ricardoarangob26/LicorScan.git
sudo chown -R ubuntu:ubuntu /opt/LicorScan  # if running as ubuntu user
cd /opt/LicorScan
```

### 1.3 Python Virtual Environment
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium  # Download browser
```

### 1.4 Environment Secrets
Create `/opt/LicorScan/.env` with production credentials:

```bash
# Supabase (NEVER commit this file)
SUPABASE_URL=https://bwxxifwqnkrfbegoycod.supabase.co
SUPABASE_ANON=sb_publishable_...
SUPABASE_KEY=sb_secret_...

# GitHub (for auto-commit/push)
GITHUB_TOKEN=ghp_your_github_token_here
GITHUB_USER=your-github-username
GITHUB_REPO=LicorScan

# Optional: Email for notifications
NOTIFY_EMAIL=your-email@example.com
```

**Security note:** Restrict `.env` permissions:
```bash
chmod 600 /opt/LicorScan/.env
```

## Step 2: Create Systemd Service & Timer

### 2.1 Service Unit: `licorscan.service`

Create `/etc/systemd/system/licorscan.service`:

```ini
[Unit]
Description=LicorScan Scraper & Catalog Sync
After=network-online.target
Wants=network-online.target
Documentation=https://github.com/Ricardoarangob26/LicorScan

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/opt/LicorScan
Environment="PATH=/opt/LicorScan/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
ExecStart=/bin/bash -c ' \
  source venv/bin/activate && \
  echo "[$(date)] Starting scraper..." >> /var/log/licorscan/scraper.log && \
  py -3 -m scraper.main --store exito --verbose >> /var/log/licorscan/scraper.log 2>&1 && \
  py -3 -m scraper.main --store carulla --verbose >> /var/log/licorscan/scraper.log 2>&1 && \
  py -3 -m scraper.main --store olimpica --verbose >> /var/log/licorscan/scraper.log 2>&1 && \
  echo "[$(date)] Building catalog..." >> /var/log/licorscan/scraper.log && \
  py -3 build_front_catalog.py >> /var/log/licorscan/scraper.log 2>&1 && \
  echo "[$(date)] Uploading to Supabase..." >> /var/log/licorscan/scraper.log && \
  py -3 scripts/upload_to_supabase.py >> /var/log/licorscan/scraper.log 2>&1 && \
  echo "[$(date)] Pushing to GitHub..." >> /var/log/licorscan/scraper.log && \
  git add frontend/catalog-data.js && \
  git commit -m "Auto: Update catalog $(date +%Y-%m-%d)" || echo "No changes" && \
  git push origin main >> /var/log/licorscan/scraper.log 2>&1 && \
  echo "[$(date)] Job completed successfully" >> /var/log/licorscan/scraper.log \
'
StandardOutput=journal
StandardError=journal
Restart=on-failure
RestartSec=300

[Install]
WantedBy=multi-user.target
```

### 2.2 Timer Unit: `licorscan.timer`

Create `/etc/systemd/system/licorscan.timer`:

```ini
[Unit]
Description=LicorScan Daily Scraper Timer
Documentation=https://github.com/Ricardoarangob26/LicorScan

[Timer]
# Run daily at 02:00 GMT-5 (equivalent to UTC-5, so UTC 07:00)
OnCalendar=*-*-* 07:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Note:** To calculate your timezone:
- Colombia (GMT-5): Daily 02:00 → UTC 07:00
- For EST (GMT-5): Use `*-*-* 07:00:00`
- For other timezones, convert to UTC

### 2.3 Deploy Service

```bash
# Copy service files
sudo cp /etc/systemd/system/licorscan.service /etc/systemd/system/licorscan.service
sudo cp /etc/systemd/system/licorscan.timer /etc/systemd/system/licorscan.timer

# Reload systemd daemon
sudo systemctl daemon-reload

# Enable and start timer
sudo systemctl enable licorscan.timer
sudo systemctl start licorscan.timer

# Verify
sudo systemctl status licorscan.timer
sudo systemctl list-timers licorscan.timer
```

## Step 3: Log Management

### 3.1 Create Log Directory
```bash
sudo mkdir -p /var/log/licorscan
sudo chown ubuntu:ubuntu /var/log/licorscan
chmod 755 /var/log/licorscan
```

### 3.2 Logrotate Configuration

Create `/etc/logrotate.d/licorscan`:

```
/var/log/licorscan/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 ubuntu ubuntu
    sharedscripts
}
```

Test logrotate:
```bash
sudo logrotate -f /etc/logrotate.d/licorscan
```

## Step 4: Monitoring & Debugging

### View Service Logs
```bash
# Recent 50 lines
sudo journalctl -u licorscan.service -n 50

# Follow in real-time
sudo journalctl -u licorscan.service -f

# Custom log file
tail -f /var/log/licorscan/scraper.log
```

### Manual Test Run
```bash
cd /opt/LicorScan
source venv/bin/activate
sudo systemctl start licorscan.service
# Wait ~5 mins
journalctl -u licorscan.service -n 100
```

### Check Timer Status
```bash
sudo systemctl status licorscan.timer
sudo systemctl list-timers licorscan.timer --all
```

### Disable/Enable Timer
```bash
# Temporarily stop
sudo systemctl stop licorscan.timer

# Restart
sudo systemctl start licorscan.timer

# Permanently disable
sudo systemctl disable licorscan.timer
```

## Step 5: Git Credentials Setup (For Auto-Push)

To avoid entering GitHub credentials repeatedly:

### Option A: Git Token (Recommended)
```bash
cd /opt/LicorScan
git config user.name "LicorScan Bot"
git config user.email "bot@licorscan.local"

# Create GitHub Personal Access Token:
# https://github.com/settings/tokens (select 'repo' scope)
# Then use it as password when git prompts, or:

git config credential.helper store
# On next push, enter token when prompted; it will be saved
```

### Option B: SSH Key
```bash
# Generate SSH key (no passphrase for automation)
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa_licorscan -N ""

# Add to GitHub:
# https://github.com/settings/keys → Add SSH key → paste content of ~/.ssh/id_rsa_licorscan.pub

# Configure Git to use this key
git config core.sshCommand "ssh -i ~/.ssh/id_rsa_licorscan"

# Update remote URL to use SSH
git remote set-url origin git@github.com:Ricardoarangob26/LicorScan.git
```

## Step 6: Monitoring & Alerts (Optional)

### Use Uptime Monitoring
- **UptimeRobot**: Monitor your VM via HTTP endpoint or cron job completion
- **Healthchecks.io**: Ping endpoint after successful job

Example: Add to end of systemd service ExecStart:
```bash
&& curl -X POST https://hc-ping.com/your-job-uuid
```

### Email Alerts (Optional)
Install `mailutils` for error notifications:
```bash
sudo apt install -y mailutils
```

Add to service script:
```bash
if [ $? -ne 0 ]; then
  echo "LicorScan job failed at $(date)" | mail -s "LicorScan Error" $NOTIFY_EMAIL
fi
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Timer not running | `sudo systemctl status licorscan.timer` → Check systemd logs |
| Service fails silently | Check `/var/log/licorscan/scraper.log` and `journalctl -u licorscan.service` |
| Git push fails | Verify `.env` has correct GITHUB_TOKEN; check SSH key permissions |
| Playwright timeout | Increase VM RAM or add `--timeout=60000` to scraper command |
| Supabase upload fails | Verify SUPABASE_KEY in `.env`; check Supabase quota/limits |

---

## Next Steps

1. ✅ Deploy service files (`licorscan.service`, `licorscan.timer`)
2. ✅ Enable timer: `sudo systemctl enable --now licorscan.timer`
3. ✅ Monitor first run: `journalctl -u licorscan.service -f`
4. ✅ Verify Supabase data updated
5. ✅ Check GitHub for auto-commit
6. ✅ Verify Vercel redeploy triggered

---

**Support:** For issues, check logs at `/var/log/licorscan/` or consult GitHub repo issues.
