#!/bin/bash
# ============================================================================
# 🧹 VPS CLEANUP & DEPLOY SCRIPT
# ============================================================================
# Removes deprecated PredictBase code and deploys Internal ARB strategy
# 
# Usage (from local machine):
#   1. Upload this script to VPS: scp scripts/cleanup_predictbase.sh root@94.143.138.8:/opt/polymarket-bot/
#   2. Run: ssh root@94.143.138.8 "cd /opt/polymarket-bot && bash scripts/cleanup_predictbase.sh"
#
# Or manually run commands below on VPS
# ============================================================================

set -e  # Exit on error

echo "============================================"
echo "🧹 POLYMARKET BOT - CLEANUP & UPGRADE"
echo "============================================"
echo "Removing: PredictBase (0 liquidity)"
echo "Adding:   Internal ARB (risk-free yield)"
echo "============================================"
echo ""

# Change to project directory
cd /opt/polymarket-bot || { echo "❌ Project not found at /opt/polymarket-bot"; exit 1; }

# Activate virtual environment
source venv/bin/activate || { echo "❌ Failed to activate venv"; exit 1; }

# ============================================================================
# STEP 1: Stop the daemon
# ============================================================================
echo "📌 Step 1: Stopping daemon..."

# Try systemd first
if systemctl is-active --quiet polymarket-bot 2>/dev/null; then
    sudo systemctl stop polymarket-bot
    echo "   ✅ Stopped via systemd"
elif pgrep -f "multi_strategy_daemon.py" > /dev/null; then
    pkill -f "multi_strategy_daemon.py"
    sleep 2
    echo "   ✅ Stopped via pkill"
else
    echo "   ⚠️  Daemon not running"
fi

# ============================================================================
# STEP 2: Pull latest code
# ============================================================================
echo ""
echo "📌 Step 2: Pulling latest code from git..."

git stash 2>/dev/null || true
git pull origin main
echo "   ✅ Code updated"

# ============================================================================
# STEP 3: Archive deprecated files (don't delete, just move)
# ============================================================================
echo ""
echo "📌 Step 3: Archiving deprecated PredictBase files..."

ARCHIVE_DIR="archive/deprecated_$(date +%Y%m%d)"
mkdir -p "$ARCHIVE_DIR"

# Files to archive (if they exist)
FILES_TO_ARCHIVE=(
    "src/exchanges/predictbase_client.py"
    "src/scanner/arb_scanner.py"
)

for file in "${FILES_TO_ARCHIVE[@]}"; do
    if [ -f "$file" ]; then
        mv "$file" "$ARCHIVE_DIR/" 2>/dev/null || true
        echo "   📦 Archived: $file"
    fi
done

echo "   ✅ Deprecated files moved to $ARCHIVE_DIR"

# ============================================================================
# STEP 4: Verify new files exist
# ============================================================================
echo ""
echo "📌 Step 4: Verifying new Internal ARB files..."

NEW_FILES=(
    "src/trading/strategies/internal_arb.py"
)

for file in "${NEW_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✅ Found: $file"
    else
        echo "   ❌ Missing: $file"
        echo "   Run 'git pull' to get latest code"
        exit 1
    fi
done

# ============================================================================
# STEP 5: Install/update dependencies
# ============================================================================
echo ""
echo "📌 Step 5: Installing dependencies..."

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "   ✅ Dependencies updated"

# ============================================================================
# STEP 6: Test import
# ============================================================================
echo ""
echo "📌 Step 6: Testing Python imports..."

python -c "
from src.trading.strategies import InternalArbStrategy, InternalArbDetector
print('   ✅ InternalArbStrategy imported successfully')
print('   ✅ InternalArbDetector imported successfully')
strategy = InternalArbStrategy()
print(f'   ✅ Strategy config: {strategy.get_config()}')
"

# ============================================================================
# STEP 7: Restart daemon
# ============================================================================
echo ""
echo "📌 Step 7: Starting daemon..."

# Check if using systemd
if [ -f /etc/systemd/system/polymarket-bot.service ]; then
    sudo systemctl start polymarket-bot
    sleep 3
    if systemctl is-active --quiet polymarket-bot; then
        echo "   ✅ Daemon started via systemd"
    else
        echo "   ❌ Failed to start via systemd"
        echo "   Check: journalctl -u polymarket-bot -n 50"
        exit 1
    fi
else
    # Use nohup
    mkdir -p logs
    nohup python scripts/multi_strategy_daemon.py --daemon --interval 60 > logs/daemon.log 2>&1 &
    sleep 3
    if pgrep -f "multi_strategy_daemon.py" > /dev/null; then
        echo "   ✅ Daemon started via nohup"
        echo "   Logs: tail -f logs/daemon.log"
    else
        echo "   ❌ Failed to start daemon"
        echo "   Check: cat logs/daemon.log"
        exit 1
    fi
fi

# ============================================================================
# STEP 8: Verify daemon is running
# ============================================================================
echo ""
echo "📌 Step 8: Verifying daemon..."
sleep 5

# Check recent logs
if [ -f logs/multi_strategy.log ]; then
    echo ""
    echo "Last 15 log lines:"
    echo "-------------------"
    tail -15 logs/multi_strategy.log
fi

# ============================================================================
# DONE
# ============================================================================
echo ""
echo "============================================"
echo "✅ UPGRADE COMPLETE!"
echo "============================================"
echo ""
echo "Changes made:"
echo "  ✅ PredictBase client: ARCHIVED (no longer used)"
echo "  ✅ ARB Scanner: ARCHIVED (no longer used)"  
echo "  ✅ Internal ARB: ACTIVE (risk-free orderbook arb)"
echo ""
echo "Monitor commands:"
echo "  tail -f logs/multi_strategy.log        # Live logs"
echo "  grep 'INTERNAL ARB' logs/*.log         # Find arb signals"
echo "  http://94.143.138.8:8000               # Dashboard"
echo ""
echo "Dashboard credentials:"
echo "  User: polybot"
echo "  Pass: Poly2026Dashboard!"
echo "============================================"
