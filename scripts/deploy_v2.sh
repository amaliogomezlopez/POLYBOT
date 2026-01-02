#!/bin/bash
# ==============================================================================
# 🚀 HYDRA V2 DEPLOYMENT SCRIPT
# ==============================================================================
# Deploys the new V2 strategies (Flash Sniper, Contrarian NO) to production.
#
# Usage:
#   chmod +x scripts/deploy_v2.sh
#   ./scripts/deploy_v2.sh
#
# Prerequisites:
#   - SSH access to VPS configured in ~/.ssh/config as "polybot"
#   - Git repository is clean (no uncommitted changes)
# ==============================================================================

set -e  # Exit on any error

# Configuration
VPS_HOST="${VPS_HOST:-polybot}"
VPS_PATH="/home/polybot/polymarket-bot"
BRANCH="main"

echo "============================================================"
echo "🚀 HYDRA V2 DEPLOYMENT"
echo "============================================================"
echo ""

# 1. Pre-flight checks
echo "📋 Pre-flight checks..."
git status --porcelain | grep -q . && {
    echo "❌ ERROR: Uncommitted changes detected. Please commit first."
    exit 1
}
echo "   ✅ Git status clean"

# 2. Push latest changes
echo ""
echo "📤 Pushing to origin/$BRANCH..."
git push origin $BRANCH

# 3. Deploy to VPS
echo ""
echo "🖥️  Deploying to VPS ($VPS_HOST)..."

ssh $VPS_HOST << 'EOF'
    cd /home/polybot/polymarket-bot
    
    echo "   📥 Pulling latest..."
    git pull origin main
    
    echo "   📦 Installing dependencies..."
    pip install -q -r requirements.txt
    
    # Check if research dependencies are needed
    if [ -f "research/whale_hunting/requirements.txt" ]; then
        pip install -q -r research/whale_hunting/requirements.txt
    fi
    
    echo "   🔄 Restarting daemon..."
    # Stop existing daemon gracefully
    pkill -f "multi_strategy_daemon.py" || true
    sleep 2
    
    # Start new daemon in background
    nohup python scripts/multi_strategy_daemon.py --daemon --interval 60 > logs/daemon.log 2>&1 &
    
    echo "   ✅ Daemon restarted (PID: $!)"
    
    # Verify it's running
    sleep 3
    if pgrep -f "multi_strategy_daemon.py" > /dev/null; then
        echo "   ✅ Daemon is running"
    else
        echo "   ❌ Daemon failed to start. Check logs/daemon.log"
        exit 1
    fi
EOF

echo ""
echo "============================================================"
echo "✅ DEPLOYMENT COMPLETE"
echo "============================================================"
echo ""
echo "V2 Strategies now active:"
echo "  - Flash Sniper (HFT, 10s cycle)"
echo "  - Contrarian NO (Swing, 60s cycle)"
echo ""
echo "Monitor logs:"
echo "  ssh $VPS_HOST 'tail -f $VPS_PATH/logs/daemon.log'"
echo ""
