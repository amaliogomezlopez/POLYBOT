"""
📊 POLYBOT DASHBOARD
=====================
Ultralight web dashboard for monitoring the multi-strategy bot.

Tech Stack:
- FastAPI (async, minimal footprint)
- Raw SQL queries (no heavy ORM)
- Tailwind CSS via CDN
- Auto-refresh every 5 seconds
- HTTP Basic Auth for security

Memory target: <50MB RAM

Usage:
    uvicorn src.dashboard.app:app --host 0.0.0.0 --port 8000
"""

import os
import asyncio
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import deque

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# Use psycopg2 directly for minimal memory footprint
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

app = FastAPI(
    title="Polybot Dashboard",
    description="Multi-Strategy Trading Bot Monitor",
    version="1.0.0"
)

# =============================================================================
# SECURITY - HTTP BASIC AUTH
# =============================================================================

security = HTTPBasic()

# Credentials from environment or defaults
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "polybot")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "Poly2026Dashboard!")

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Auth credentials."""
    correct_username = secrets.compare_digest(credentials.username, DASHBOARD_USER)
    correct_password = secrets.compare_digest(credentials.password, DASHBOARD_PASS)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Templates
TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_DIR.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# =============================================================================
# DATABASE CONFIG
# =============================================================================

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "polymarket"),
    "user": os.getenv("DB_USER", "polybot"),
    "password": os.getenv("DB_PASSWORD", "PolyBot2026Trading!"),
}

LOG_FILE = Path(os.getenv("LOG_FILE", "logs/multi_strategy.log"))
DAEMON_START_TIME = datetime.utcnow()  # Will be updated from logs

# Near miss cache (in-memory, limited size)
NEAR_MISS_CACHE: deque = deque(maxlen=100)

# =============================================================================
# DATABASE HELPERS
# =============================================================================

def get_db_connection():
    """Get a raw database connection."""
    if not DB_AVAILABLE:
        return None
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"DB connection error: {e}")
        return None


def execute_query(query: str, params: tuple = None) -> List[Dict]:
    """Execute a query and return results as dicts."""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"Query error: {e}")
        return []
    finally:
        conn.close()


# =============================================================================
# API ENDPOINTS (Protected with HTTP Basic Auth)
# =============================================================================

@app.get("/api/stats")
async def get_stats(user: str = Depends(verify_credentials)) -> Dict[str, Any]:
    """Get overall bot statistics."""
    
    # Get trade stats by strategy
    strategy_stats = execute_query("""
        SELECT 
            strategy_id,
            COUNT(*) as total_trades,
            SUM(CASE WHEN status = 'RESOLVED_WIN' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN status = 'RESOLVED_LOSS' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN status IN ('PENDING', 'FILLED') THEN 1 ELSE 0 END) as open,
            COALESCE(SUM(realized_pnl), 0) as total_pnl,
            COALESCE(SUM(stake), 0) as total_stake
        FROM trades
        WHERE paper_mode = true
        GROUP BY strategy_id
    """)
    
    # Get today's trades
    today_stats = execute_query("""
        SELECT 
            COUNT(*) as trades_today,
            COALESCE(SUM(stake), 0) as stake_today
        FROM trades
        WHERE paper_mode = true
        AND signal_at >= CURRENT_DATE
    """)
    
    # Calculate overall stats
    total_trades = sum(s.get('total_trades', 0) for s in strategy_stats)
    total_wins = sum(s.get('wins', 0) for s in strategy_stats)
    total_pnl = sum(float(s.get('total_pnl', 0)) for s in strategy_stats)
    
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
    
    # Get cycle count from logs
    cycles = get_cycle_count()
    
    # Calculate uptime
    uptime = get_uptime()
    
    return {
        "status": "online" if cycles > 0 else "unknown",
        "uptime": uptime,
        "cycles": cycles,
        "total_trades": total_trades,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "trades_today": today_stats[0].get('trades_today', 0) if today_stats else 0,
        "strategies": {
            s['strategy_id']: {
                "trades": s['total_trades'],
                "wins": s['wins'],
                "losses": s['losses'],
                "open": s['open'],
                "pnl": float(s['total_pnl']),
                "win_rate": round(s['wins'] / s['total_trades'] * 100, 1) if s['total_trades'] > 0 else 0
            }
            for s in strategy_stats
        },
        "best_strategy": max(strategy_stats, key=lambda x: float(x.get('total_pnl', 0)))['strategy_id'] if strategy_stats else "N/A",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/trades")
async def get_trades(limit: int = 50, user: str = Depends(verify_credentials)) -> List[Dict]:
    """Get recent trades."""
    trades = execute_query("""
        SELECT 
            trade_id,
            strategy_id,
            question,
            outcome,
            entry_price,
            stake,
            status,
            realized_pnl,
            signal_at,
            resolved_at
        FROM trades
        WHERE paper_mode = true
        ORDER BY signal_at DESC
        LIMIT %s
    """, (limit,))
    
    # Format for frontend
    for t in trades:
        t['created_at'] = t['signal_at'].isoformat() if t.get('signal_at') else None
        t['resolved_at'] = t['resolved_at'].isoformat() if t.get('resolved_at') else None
        t['entry_price'] = float(t['entry_price']) if t.get('entry_price') else 0
        t['stake'] = float(t['stake']) if t.get('stake') else 0
        t['realized_pnl'] = float(t['realized_pnl']) if t.get('realized_pnl') else 0
    
    return trades


@app.get("/api/logs")
async def get_logs(lines: int = 50, user: str = Depends(verify_credentials)) -> Dict[str, Any]:
    """Get recent log lines."""
    log_lines = []
    near_misses = []
    
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                # Read last N lines efficiently
                all_lines = f.readlines()
                log_lines = all_lines[-lines:]
                
                # Extract near misses
                for line in all_lines[-200:]:
                    if "Near miss" in line or "NEAR_MISS" in line:
                        near_misses.append(line.strip())
        except Exception as e:
            log_lines = [f"Error reading logs: {e}"]
    else:
        log_lines = ["Log file not found"]
    
    return {
        "logs": [l.strip() for l in log_lines if l.strip()],
        "near_misses": near_misses[-20:],  # Last 20 near misses
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/near-misses")
async def get_near_misses(user: str = Depends(verify_credentials)) -> List[Dict]:
    """Get near miss opportunities."""
    return list(NEAR_MISS_CACHE)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "db": DB_AVAILABLE,
        "timestamp": datetime.utcnow().isoformat()
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_cycle_count() -> int:
    """Extract cycle count from logs."""
    if not LOG_FILE.exists():
        return 0
    
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-100:]
            for line in reversed(lines):
                if "CYCLE" in line:
                    # Extract cycle number from "🔄 CYCLE 123 -"
                    parts = line.split("CYCLE")
                    if len(parts) > 1:
                        num_part = parts[1].strip().split()[0]
                        try:
                            return int(num_part)
                        except:
                            pass
    except:
        pass
    return 0


def get_uptime() -> str:
    """Get bot uptime from systemd or logs."""
    if not LOG_FILE.exists():
        return "Unknown"
    
    try:
        # Get modification time of log file as proxy for activity
        mtime = datetime.fromtimestamp(LOG_FILE.stat().st_mtime)
        
        # Find first "DAEMON STARTING" in recent logs
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            for line in lines:
                if "DAEMON STARTING" in line:
                    # Extract timestamp from log line
                    try:
                        ts_str = line.split("|")[0].strip()
                        start_time = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
                        delta = datetime.now() - start_time
                        
                        hours = int(delta.total_seconds() // 3600)
                        minutes = int((delta.total_seconds() % 3600) // 60)
                        
                        if hours > 0:
                            return f"{hours}h {minutes}m"
                        return f"{minutes}m"
                    except:
                        pass
    except:
        pass
    
    return "Unknown"


# =============================================================================
# FRONTEND ROUTE (Protected)
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: str = Depends(verify_credentials)):
    """Serve the main dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})


# =============================================================================
# STARTUP
# =============================================================================

@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    print("🚀 Dashboard starting...")
    print(f"   Database: {'✅' if DB_AVAILABLE else '❌'}")
    print(f"   Log file: {LOG_FILE}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
