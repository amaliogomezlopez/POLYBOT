#!/bin/bash
# =============================================================================
# VPS FIX COMMANDS - Run these on VPS after SSH
# =============================================================================
# 
# SSH: ssh root@94.143.138.8
# Password: p4RCcQUr
#
# Then run these commands:
# =============================================================================

# 1. Stop daemon
pkill -f multi_strategy_daemon.py

# 2. Go to project dir
cd /opt/polymarket-bot
source venv/bin/activate

# 3. Pull latest fix
git pull origin main

# 4. Test imports
python -c "
from src.trading.strategies import InternalArbStrategy, strategy_registry
print('✅ InternalArbStrategy imported')
from src.trading.strategies.base_strategy import MarketData
print('✅ MarketData imported')
print('✅ ALL IMPORTS OK')
"

# 5. Start daemon
nohup python scripts/multi_strategy_daemon.py --daemon --interval 60 > logs/daemon.log 2>&1 &

# 6. Wait and check logs
sleep 3
echo "=== DAEMON LOGS ==="
tail -20 logs/multi_strategy.log

# 7. Verify daemon running
echo ""
echo "=== DAEMON STATUS ==="
pgrep -f multi_strategy_daemon.py && echo "✅ Daemon is running" || echo "❌ Daemon not running"
