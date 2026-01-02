#!/bin/bash
# ============================================
# POLYMARKET BOT - SYSTEMD SERVICE INSTALLER
# ============================================
# Run as root on VPS: bash install_service.sh
# ============================================

set -e

echo "=========================================="
echo "🚀 Installing Polymarket Bot as systemd service"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Please run as root${NC}"
    exit 1
fi

BOT_DIR="/opt/polymarket-bot"

# Verify bot directory exists
if [ ! -d "$BOT_DIR" ]; then
    echo -e "${RED}❌ Bot directory not found: $BOT_DIR${NC}"
    exit 1
fi

# Verify Python venv exists
if [ ! -f "$BOT_DIR/venv/bin/python" ]; then
    echo -e "${RED}❌ Python venv not found. Run setup first.${NC}"
    exit 1
fi

# Create logs directory if not exists
mkdir -p "$BOT_DIR/logs"

echo -e "${YELLOW}📝 Step 1: Installing systemd service...${NC}"

# Copy service file
cp "$BOT_DIR/scripts/systemd/polymarket-bot.service" /etc/systemd/system/
chmod 644 /etc/systemd/system/polymarket-bot.service

# Reload systemd daemon
systemctl daemon-reload

echo -e "${GREEN}✅ Service file installed${NC}"

echo -e "${YELLOW}📝 Step 2: Configuring logrotate...${NC}"

# Copy logrotate config
cp "$BOT_DIR/scripts/systemd/polymarket-bot.logrotate" /etc/logrotate.d/polymarket-bot
chmod 644 /etc/logrotate.d/polymarket-bot

# Test logrotate config
logrotate -d /etc/logrotate.d/polymarket-bot 2>/dev/null && echo -e "${GREEN}✅ Logrotate configured${NC}" || echo -e "${YELLOW}⚠️ Logrotate test had warnings (usually OK)${NC}"

echo -e "${YELLOW}📝 Step 3: Enabling and starting service...${NC}"

# Stop any existing nohup processes
pkill -f "production_monitor.py" 2>/dev/null || true
sleep 2

# Enable service to start on boot
systemctl enable polymarket-bot.service

# Start the service
systemctl start polymarket-bot.service

# Wait a moment for startup
sleep 3

# Check status
if systemctl is-active --quiet polymarket-bot.service; then
    echo -e "${GREEN}✅ Service is running!${NC}"
else
    echo -e "${RED}❌ Service failed to start. Check logs:${NC}"
    journalctl -u polymarket-bot.service -n 20 --no-pager
    exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}🎉 INSTALLATION COMPLETE!${NC}"
echo "=========================================="
echo ""
echo "📋 Useful commands:"
echo "   systemctl status polymarket-bot    # Check status"
echo "   systemctl stop polymarket-bot      # Stop bot"
echo "   systemctl start polymarket-bot     # Start bot"
echo "   systemctl restart polymarket-bot   # Restart bot"
echo "   journalctl -u polymarket-bot -f    # View live logs"
echo "   tail -f $BOT_DIR/logs/daemon.log   # View log file"
echo ""
echo "🔄 Auto-restart: Enabled (5s delay on failure)"
echo "📁 Logs rotated: Daily, kept 14 days, max 50MB each"
echo ""
