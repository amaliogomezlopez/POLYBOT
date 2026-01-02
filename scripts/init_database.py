#!/usr/bin/env python3
"""
🗃️ DATABASE INITIALIZATION SCRIPT
===================================
Run this to:
1. Initialize PostgreSQL+TimescaleDB tables
2. Migrate existing JSON data
3. Verify database connection

Usage:
    python scripts/init_database.py --init      # Create tables
    python scripts/init_database.py --migrate   # Migrate JSON to DB
    python scripts/init_database.py --verify    # Check connection
    python scripts/init_database.py --stats     # Show portfolio stats
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    parser = argparse.ArgumentParser(description="Database Management")
    parser.add_argument("--init", action="store_true", help="Initialize database tables")
    parser.add_argument("--migrate", action="store_true", help="Migrate JSON data to DB")
    parser.add_argument("--verify", action="store_true", help="Verify database connection")
    parser.add_argument("--stats", action="store_true", help="Show portfolio statistics")
    
    args = parser.parse_args()
    
    try:
        from src.db.production_db import (
            init_database, 
            migrate_from_json, 
            get_portfolio_stats,
            engine
        )
        print("✅ Database module loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load database module: {e}")
        print("\nMake sure you have installed: pip install sqlalchemy psycopg2-binary")
        return
    
    if args.verify or not any([args.init, args.migrate, args.stats]):
        print("\n🔍 Verifying database connection...")
        try:
            with engine.connect() as conn:
                result = conn.execute("SELECT version()")
                version = result.fetchone()[0]
                print(f"✅ Connected to: {version[:60]}...")
                
                # Check TimescaleDB
                result = conn.execute("SELECT installed_version FROM pg_available_extensions WHERE name = 'timescaledb'")
                ts = result.fetchone()
                if ts:
                    print(f"✅ TimescaleDB available: {ts[0]}")
                else:
                    print("⚠️ TimescaleDB not installed (optional)")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            print("\nCheck your DATABASE_URL in .env or environment")
            return
    
    if args.init:
        print("\n🔧 Initializing database tables...")
        try:
            init_database()
            print("✅ Tables created successfully!")
        except Exception as e:
            print(f"❌ Init failed: {e}")
    
    if args.migrate:
        print("\n📥 Migrating JSON data to database...")
        bets_file = Path('data/tail_bot/bets.json')
        if not bets_file.exists():
            print(f"⚠️ No bets file found at {bets_file}")
        else:
            try:
                migrate_from_json(str(bets_file))
                print("✅ Migration complete!")
            except Exception as e:
                print(f"❌ Migration failed: {e}")
    
    if args.stats:
        print("\n📊 Portfolio Statistics:")
        try:
            stats = get_portfolio_stats()
            print(f"""
╔═══════════════════════════════════════╗
║          PORTFOLIO SUMMARY            ║
╠═══════════════════════════════════════╣
║  Total Positions:    {stats['total_positions']:>15}  ║
║  Pending:            {stats['pending_positions']:>15}  ║
║  Won:                {stats['won_positions']:>15}  ║
║  Lost:               {stats['lost_positions']:>15}  ║
╠═══════════════════════════════════════╣
║  Total Invested:  ${stats['total_invested']:>15.2f}  ║
║  Total P&L:       ${stats['total_profit']:>15.2f}  ║
║  Hit Rate:        {stats['hit_rate']:>14.1f}%  ║
╚═══════════════════════════════════════╝
""")
        except Exception as e:
            print(f"❌ Stats failed: {e}")

if __name__ == "__main__":
    main()
