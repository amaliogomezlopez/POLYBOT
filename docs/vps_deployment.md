# 🚀 VPS Deployment Guide

## Server Information

| Field | Value |
|-------|-------|
| **IP Address** | 94.143.138.8 |
| **OS** | Ubuntu |
| **User** | root |
| **Bot Directory** | /opt/polymarket-bot |
| **Python Venv** | /opt/polymarket-bot/venv |

---

## 📁 Directory Structure on Server

```
/opt/polymarket-bot/
├── venv/                    # Python virtual environment
├── data/
│   └── tail_bot/
│       ├── bets.json        # Paper bets (100+)
│       ├── resolved.json    # Resolved bets
│       └── training_data.json
├── logs/
│   └── scheduled_monitor.log
├── scripts/
│   ├── scheduled_monitor.py # Main daemon
│   └── setup_server.sh
├── tools/
│   ├── terminal_ui.py       # Dashboard
│   ├── tail_dashboard.py
│   ├── place_tail_bets.py
│   └── scan_tails.py
└── .env                     # Credentials (DO NOT COMMIT)
```

---

## 🔧 Initial Setup (Done January 2, 2026)

### 1. SSH Connection
```bash
ssh root@94.143.138.8
```

### 2. System Dependencies
```bash
apt-get update
apt-get install -y python3 python3-pip python3-venv git screen
```

### 3. Create Bot Directory
```bash
mkdir -p /opt/polymarket-bot
cd /opt/polymarket-bot
```

### 4. Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install httpx rich
```

### 5. Clone Repository (Git Method)
```bash
cd /opt/polymarket-bot
git clone https://github.com/amaliogomezlopez/POLYBOT.git .
# Or if already exists:
git pull origin main
```

### 6. Create .env File
```bash
nano /opt/polymarket-bot/.env
```
```env
PAPER_TRADING=true
POLYMARKET_PRIVATE_KEY=0x...
API_KEY=...
SECRET=...
PASSPHRASE=...
```

---

## 🔄 Updating the Bot

### From Local Machine (Push changes)
```bash
git add -A
git commit -m "Update: description"
git push origin main
```

### On Server (Pull changes)
```bash
cd /opt/polymarket-bot
git pull origin main
```

---

## 🚀 Running the Bot

### Option 1: Background with nohup (Recommended)
```bash
cd /opt/polymarket-bot
source venv/bin/activate
nohup python scripts/scheduled_monitor.py --daemon --interval 30 > logs/nohup.log 2>&1 &
```

### Option 2: Screen Session
```bash
screen -S polybot
cd /opt/polymarket-bot
source venv/bin/activate
python scripts/scheduled_monitor.py --daemon --interval 30
# Ctrl+A, D to detach
# screen -r polybot to reattach
```

### Option 3: Systemd Service
```bash
# Create service file
sudo nano /etc/systemd/system/polymarket-bot.service
```
```ini
[Unit]
Description=Polymarket Tail Betting Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/polymarket-bot
ExecStart=/opt/polymarket-bot/venv/bin/python scripts/scheduled_monitor.py --daemon --interval 30
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable polymarket-bot
sudo systemctl start polymarket-bot
sudo systemctl status polymarket-bot
```

---

## 📊 Monitoring

### Check if Bot is Running
```bash
ps aux | grep scheduled_monitor
```

### View Logs
```bash
tail -f /opt/polymarket-bot/logs/scheduled_monitor.log
```

### View Dashboard (interactive)
```bash
cd /opt/polymarket-bot
source venv/bin/activate
python tools/terminal_ui.py
```

---

## 🗄️ Database Setup (PostgreSQL)

### Install PostgreSQL
```bash
apt-get install -y postgresql postgresql-contrib
systemctl start postgresql
systemctl enable postgresql
```

### Create Database
```bash
sudo -u postgres psql
```
```sql
CREATE DATABASE polymarket_bot;
CREATE USER polybot WITH ENCRYPTED PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE polymarket_bot TO polybot;
\q
```

### Update .env
```env
DATABASE_URL=postgresql://polybot:your_secure_password@localhost:5432/polymarket_bot
```

---

## 🔒 Security Notes

1. **Never commit .env file** - Contains private keys
2. **Use strong passwords** for database
3. **Firewall**: Only allow SSH (22) and necessary ports
4. **Regular updates**: `apt-get update && apt-get upgrade`

---

## 📝 Common Commands

| Action | Command |
|--------|---------|
| SSH to server | `ssh root@94.143.138.8` |
| Pull updates | `cd /opt/polymarket-bot && git pull` |
| Start bot | `nohup python scripts/scheduled_monitor.py --daemon &` |
| Stop bot | `pkill -f scheduled_monitor` |
| View logs | `tail -f logs/scheduled_monitor.log` |
| Check status | `ps aux \| grep python` |

---

## 📅 Deployment History

| Date | Action | Notes |
|------|--------|-------|
| 2026-01-02 | Initial deployment | 100 paper bets, daemon running |

---

*Last updated: January 2, 2026*
