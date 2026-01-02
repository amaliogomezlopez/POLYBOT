# Polybot Documentation

Sistema **multi-estrategia** para validación de oportunidades de trading en Polymarket y exchanges relacionados. Actualmente operando en **Paper Trading Mode** para validar 3 estrategias simultáneamente.

## 🎯 Sistema Actual

| Estrategia | ID | Estado | Descripción |
|------------|-----|--------|-------------|
| Cross-Exchange Arbitrage | `ARB_PREDICTBASE_V1` | 🟡 Paper | Polymarket vs PredictBase |
| Microstructure Sniper | `SNIPER_MICRO_V1` | 🟡 Paper | Dual Mode: Crash Detector + Stink Bids |
| Tail Betting | `TAIL_BETTING_V1` | 🟡 Paper | ML-scored long shots (<$0.04) |

## 📚 Documentación

1.  **[Trading Strategy](strategy.md)** ⭐ **ACTUALIZADO**
    *   Las 3 estrategias en detalle: Arbitrage, Sniper, Tail
    *   Parámetros, triggers y flujos de ejecución
2.  **[Architecture](architecture.md)**
    *   Sistema multi-estrategia con Strategy Pattern
    *   Database models y daemon orchestrator
3.  **[Setup Guide](setup.md)**
    *   Instalación local y deployment a VPS
4.  **[API Reference](api_reference.md)**
    *   Módulos: scanner, detector, trading, risk, monitoring
5.  **[Current Status](current_status.md)**
    *   Fases completadas y métricas actuales
6.  **[Production Workflow](production_workflow.md)**
    *   Paper Trading → Live Trading transition

## 🔧 Componentes Clave

```
scripts/
  └── multi_strategy_daemon.py    # Orchestrador principal
src/trading/strategies/
  ├── base_strategy.py            # BaseStrategy ABC
  ├── arbitrage_strategy.py       # Cross-exchange arb
  ├── sniper_strategy.py          # Dual mode sniper
  └── tail_strategy.py            # ML tail betting
src/db/
  └── multi_strategy_models.py    # SQLAlchemy models
src/exchanges/
  └── predictbase_client.py       # PredictBase API client
```

## 🚀 Quick Start

```bash
# Ejecutar daemon (paper mode)
python scripts/multi_strategy_daemon.py --init-db

# Verificar status
systemctl status multi-strategy-bot  # En VPS
```

## 📊 VPS Deployment

```
Server: 94.143.138.8
Service: multi-strategy-bot.service
Interval: 60 segundos
Database: PostgreSQL (polymarket)
```

## Quick Links
- [README.md](../README.md)
- [Strategy Deep Dive](strategy.md)
- [Task Tracker](../task.md)

