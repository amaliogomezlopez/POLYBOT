#!/bin/bash
# =============================================================================
# POLYMARKET BOT - SERVER SETUP SCRIPT
# =============================================================================
# Run this on your Ubuntu VPS after connecting via SSH
#
# Usage:
#   chmod +x setup_server.sh
#   ./setup_server.sh
# =============================================================================

set -e

echo "========================================"
echo "🎯 POLYMARKET BOT - SERVER SETUP"
echo "========================================"

# Configuration
BOT_DIR="/opt/polymarket-bot"
VENV_DIR="$BOT_DIR/venv"

# 1. Create directory structure
echo ""
echo "📁 Creating directory structure..."
mkdir -p $BOT_DIR
mkdir -p $BOT_DIR/data/tail_bot
mkdir -p $BOT_DIR/logs
mkdir -p $BOT_DIR/scripts
mkdir -p $BOT_DIR/tools

# 2. Install system dependencies
echo ""
echo "📦 Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv git screen

# 3. Create virtual environment
echo ""
echo "🐍 Creating Python virtual environment..."
python3 -m venv $VENV_DIR
source $VENV_DIR/bin/activate

# 4. Install Python packages
echo ""
echo "📚 Installing Python packages..."
pip install --upgrade pip
pip install httpx rich

# 5. Copy this script's location for reference
echo ""
echo "========================================"
echo "✅ SETUP COMPLETE!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Copy bot files from local machine:"
echo "   scp -r scripts tools data root@94.143.138.8:$BOT_DIR/"
echo ""
echo "2. Create .env file:"
echo "   nano $BOT_DIR/.env"
echo ""
echo "3. Start the bot:"
echo "   cd $BOT_DIR"
echo "   source venv/bin/activate"
echo "   python scripts/scheduled_monitor.py --daemon"
echo ""
echo "4. Or run in screen:"
echo "   screen -S polybot"
echo "   python scripts/scheduled_monitor.py --daemon"
echo "   # Ctrl+A, D to detach"
echo ""
echo "5. View dashboard:"
echo "   python tools/terminal_ui.py --live"
echo ""
