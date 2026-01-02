#!/bin/bash
# =============================================================================
# POSTGRESQL SETUP SCRIPT FOR POLYMARKET BOT
# =============================================================================
# Run on Ubuntu VPS to set up PostgreSQL database
#
# Usage:
#   chmod +x setup_postgresql.sh
#   ./setup_postgresql.sh
# =============================================================================

set -e

echo "========================================"
echo "🗄️ POSTGRESQL SETUP FOR POLYMARKET BOT"
echo "========================================"

# Configuration
DB_NAME="polymarket_bot"
DB_USER="polybot"
DB_PASS="PolyBot2026Secure!"  # Change this!

# 1. Install PostgreSQL
echo ""
echo "📦 Installing PostgreSQL..."
apt-get update
apt-get install -y postgresql postgresql-contrib

# 2. Start and enable service
echo ""
echo "🔧 Starting PostgreSQL service..."
systemctl start postgresql
systemctl enable postgresql

# 3. Create database and user
echo ""
echo "📊 Creating database and user..."
sudo -u postgres psql << EOF
-- Drop if exists (for clean setup)
DROP DATABASE IF EXISTS $DB_NAME;
DROP USER IF EXISTS $DB_USER;

-- Create user with password
CREATE USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASS';

-- Create database
CREATE DATABASE $DB_NAME OWNER $DB_USER;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

-- Connect to database and set up schema permissions
\c $DB_NAME
GRANT ALL ON SCHEMA public TO $DB_USER;

\q
EOF

# 4. Configure pg_hba.conf for local connections
echo ""
echo "🔐 Configuring authentication..."
PG_HBA=$(sudo -u postgres psql -t -P format=unaligned -c "SHOW hba_file")
echo "local   $DB_NAME    $DB_USER                                md5" >> $PG_HBA

# Restart PostgreSQL to apply changes
systemctl restart postgresql

# 5. Test connection
echo ""
echo "🧪 Testing connection..."
PGPASSWORD=$DB_PASS psql -h localhost -U $DB_USER -d $DB_NAME -c "SELECT version();" && echo "✅ Connection successful!"

# 6. Output configuration
echo ""
echo "========================================"
echo "✅ POSTGRESQL SETUP COMPLETE!"
echo "========================================"
echo ""
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo "Password: $DB_PASS"
echo ""
echo "Connection string for .env:"
echo "DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"
echo ""
echo "Next steps:"
echo "1. Update /opt/polymarket-bot/.env with DATABASE_URL"
echo "2. Run: python src/db/db_models.py --init"
echo "3. Run: python src/db/db_models.py --migrate"
echo ""
