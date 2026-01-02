#!/bin/bash
# =============================================================================
# POLYMARKET BOT - COMPLETE VPS SETUP WITH TIMESCALEDB
# =============================================================================
# This script sets up the entire environment on the VPS
# Run with: bash vps_full_setup.sh
# =============================================================================

set -e

echo "========================================"
echo "🚀 POLYMARKET BOT - FULL VPS SETUP"
echo "========================================"
echo "Database: PostgreSQL + TimescaleDB (optimized for trading)"
echo ""

BOT_DIR="/opt/polymarket-bot"
DB_NAME="polymarket"
DB_USER="polybot"
DB_PASS="PolyBot2026Trading!"

# =============================================================================
# 1. CLEAN EXISTING INSTALLATION
# =============================================================================
echo "🧹 Cleaning existing installation..."
rm -rf $BOT_DIR
mkdir -p $BOT_DIR
mkdir -p $BOT_DIR/logs
mkdir -p $BOT_DIR/data/tail_bot

# Kill any existing bot processes
pkill -f scheduled_monitor.py 2>/dev/null || true
pkill -f terminal_ui.py 2>/dev/null || true

# =============================================================================
# 2. SYSTEM DEPENDENCIES
# =============================================================================
echo ""
echo "📦 Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git screen curl gnupg2 lsb-release

# =============================================================================
# 3. INSTALL POSTGRESQL + TIMESCALEDB
# =============================================================================
echo ""
echo "🗄️ Installing PostgreSQL + TimescaleDB..."

# Add TimescaleDB repository
echo "deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main" | tee /etc/apt/sources.list.d/timescaledb.list
curl -s https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/trusted.gpg.d/timescaledb.gpg

# Install PostgreSQL and TimescaleDB
apt-get update -qq
apt-get install -y -qq postgresql postgresql-contrib

# Check if timescaledb is available, otherwise use regular postgres
if apt-cache show timescaledb-2-postgresql-14 &>/dev/null; then
    apt-get install -y -qq timescaledb-2-postgresql-14
    TIMESCALE_AVAILABLE=true
else
    echo "⚠️ TimescaleDB package not found, using standard PostgreSQL"
    TIMESCALE_AVAILABLE=false
fi

# Start PostgreSQL
systemctl start postgresql
systemctl enable postgresql

# =============================================================================
# 4. CONFIGURE DATABASE
# =============================================================================
echo ""
echo "📊 Configuring database..."

# Drop existing database/user if exists and recreate
sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null || true
sudo -u postgres psql -c "DROP USER IF EXISTS $DB_USER;" 2>/dev/null || true

# Create user and database
sudo -u postgres psql << EOF
CREATE USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASS';
CREATE DATABASE $DB_NAME OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOF

# Enable TimescaleDB extension if available
if [ "$TIMESCALE_AVAILABLE" = true ]; then
    sudo -u postgres psql -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"
    echo "✅ TimescaleDB extension enabled"
fi

# =============================================================================
# 5. CLONE REPOSITORY
# =============================================================================
echo ""
echo "📥 Cloning repository..."
cd $BOT_DIR
git clone https://github.com/amaliogomezlopez/POLYBOT.git . || git pull origin main

# =============================================================================
# 6. PYTHON ENVIRONMENT
# =============================================================================
echo ""
echo "🐍 Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install httpx rich sqlalchemy psycopg2-binary asyncpg -q

# =============================================================================
# 7. CREATE .ENV FILE
# =============================================================================
echo ""
echo "📝 Creating .env file..."
cat > $BOT_DIR/.env << 'ENVFILE'
# ============================================
# POLYMARKET BOT - PRODUCTION CONFIG
# ============================================
PAPER_TRADING=true
ENVIRONMENT=production
LOG_LEVEL=INFO

# Database (PostgreSQL + TimescaleDB)
DATABASE_URL=postgresql://polybot:PolyBot2026Trading!@localhost:5432/polymarket

# API Credentials
API_KEY=dabb7991-b4bb-807e-988c-91a95a6e2b55
SECRET=r3d0xoBRYt8oMNMCJWad3rjb6NnS7KnemE2y5tkQ2LM=
PASSPHRASE=ffd72f563c2ee6f9efd1f92c337e0d1c2992870d32b24ada31d66ad06e425a1a
POLYMARKET_PRIVATE_KEY=0x88fecc80561590dfb16aafc3f3d8c8e9275ad1e9119d9b92b3edfb5bd1065f98
POLYMARKET_FUNDER_ADDRESS=0x20179f2cFA9051b0c7ea9B2bc6b23f5c8Fb31c31
SIGNATURE_TYPE=1

# Trading Parameters
MAX_POSITION_SIZE_USDC=5
MIN_PROFIT_THRESHOLD=0.02
MAX_DAILY_LOSS_USDC=10
MAX_TOTAL_EXPOSURE_USDC=20
ENVFILE

echo "✅ .env file created"

# =============================================================================
# 8. SUMMARY
# =============================================================================
echo ""
echo "========================================"
echo "✅ VPS SETUP COMPLETE!"
echo "========================================"
echo ""
echo "Database: PostgreSQL"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo ""
echo "Bot Directory: $BOT_DIR"
echo ""
echo "Next steps (run manually):"
echo "  cd $BOT_DIR"
echo "  source venv/bin/activate"
echo "  python src/db/db_models.py --init"
echo "  python src/db/db_models.py --migrate"
echo "  nohup python scripts/scheduled_monitor.py --daemon &"
echo ""
