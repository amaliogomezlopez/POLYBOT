# 🎯 Trading Strategies

El bot ejecuta un **sistema multi-estrategia** que evalúa cada mercado con 3 estrategias independientes en paralelo. Cada estrategia tiene sus propios triggers, parámetros y métricas de rendimiento.

---

## 📊 Resumen de Estrategias

| ID | Nombre | Tipo | Trigger | Stake | ROI Esperado |
|----|--------|------|---------|-------|--------------|
| `ARB_PREDICTBASE_V1` | Cross-Exchange Arbitrage | Arbitrage | ROI > 2.5% (synthetic) | $50 | 2.5-25% |
| `SNIPER_MICRO_V1` | Microstructure Sniper | Dual Mode | Crash Detection + Stink Bids | $5-10 | 50-500% |
| `TAIL_BETTING_V1` | Tail Betting | Tail | YES < $0.04, ML Score > 55% | $2 | 25-1000x |

---

## 🔀 Estrategia A: Cross-Exchange Arbitrage (v2 - ARBScanner)

**ID**: `ARB_PREDICTBASE_V1`  
**Archivos**: 
- `src/scanner/arb_scanner.py` (batch scanner)
- `src/trading/strategies/arbitrage_strategy.py` (strategy wrapper)

### Concepto
Detecta oportunidades de **arbitraje sintético** cuando:
- `Poly_YES + PB_NO < $0.975` (2.5% profit margin)
- `Poly_NO + PB_YES < $0.975`

**Nota Importante**: PredictBase es un mercado de predicciones SEPARADO en Base chain, 
NO un agregador de Polymarket. Las oportunidades de arbitraje solo existen cuando 
mercados similares están listados en AMBAS plataformas.

### Tipos de Arbitraje

#### 1. Arbitraje Sintético (Principal)
```
Total Cost = Poly_YES + PB_NO
ROI = (1.0 - Total Cost) / Total Cost * 100

Ejemplo:
  Poly YES = $0.45
  PB NO    = $0.52
  Cost     = $0.97
  Profit   = $0.03 (3.1% ROI)
```

#### 2. Arbitraje Directo (Informativo)
```
Price Diff = |Poly_YES - PB_YES|
Edge = Price Diff / min(Poly, PB) * 100

Requiere capacidad de venta/short en una plataforma.
```

### Parámetros v2
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `min_roi_pct` | 2.5% | ROI mínimo (cubre fees de bridging) |
| `max_roi_pct` | 25% | ROI máximo (evita datos erróneos) |
| `fuzzy_threshold` | 85 | Score mínimo de matching (token_sort_ratio) |
| `stake_size` | $50 | Tamaño de posición (más alto por bajo riesgo) |
| `scan_interval` | 60s | Intervalo entre scans |

### Flujo de Ejecución (v2 - Batch)
1. **Batch Fetch**: Obtiene ~200 mercados de PredictBase
2. **Batch Match**: Fuzzy matching usando `thefuzz.token_sort_ratio`
3. **Ambiguity Check**: Detecta indicadores opuestos ("NOT", "under", etc.)
4. **ROI Calculation**: Calcula ambas direcciones (YES+NO, NO+YES)
5. **Signal Generation**: Genera `TradeSignal` si ROI > 2.5%

### Limitaciones Actuales (Enero 2025)
- **PredictBase**: Principalmente deportes (NHL, NBA, Premier League)
- **Polymarket**: Principalmente política/macro (elecciones, películas)
- **Overlap**: Muy bajo - pocas oportunidades reales de arbitraje
- **Acción**: El scanner está implementado y funcionando, pero las señales
  serán raras hasta que haya más mercados superpuestos.

---

## 🎯 Estrategia B: Microstructure Sniper (DUAL MODE)

**ID**: `SNIPER_MICRO_V1`  
**Archivo**: `src/trading/strategies/sniper_strategy.py`

Esta estrategia opera en **dos modos simultáneos**:

### MODE 1: CRASH DETECTOR (Reactivo) 🚨

Detecta y captura rebotes después de ventas de pánico.

#### Trigger
```
SI Precio_Actual < (Precio_Medio_5min * 0.85)  // Caída del 15%
Y  Volumen_2min > (Volumen_Promedio * 2)       // Spike de volumen
→  COMPRAR con Limit Order 1% sobre Best Bid
```

#### Parámetros Mode 1
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `price_drop_threshold` | 15% | Caída mínima para trigger |
| `volume_spike_multiplier` | 2x | Múltiplo de volumen requerido |
| `lookback_minutes` | 5 | Ventana de análisis |
| `bid_offset_pct` | 1% | Offset sobre best bid |

#### Flujo Mode 1
1. Mantiene `PriceBuffer` rolling de 5 minutos por mercado
2. Calcula `price_change_pct` en cada update
3. Si detecta caída > 15%:
   - Verifica spike de volumen (panic selling)
   - Genera señal con target = precio medio (rebound)

---

### MODE 2: STINK BID (Proactivo) 🪤

Coloca órdenes "trampa" a precios ridículamente bajos esperando flash crashes.

#### Concepto
Un "Stink Bid" es una orden límite a precio muy bajo ($0.02-$0.05) que espera pasivamente a que el mercado caiga hasta ese nivel durante un flash crash.

#### Criterios para Colocar Stink Bid
```
SI Volumen_24h > $50,000
Y  Expiry < 24 horas
Y  Precio_YES > $0.05 (no es ya muy barato)
Y  No hay stink bid activo en este mercado
Y  Active_Stink_Bids < MAX_CONCURRENT (10)
→  COLOCAR STINK BID
```

#### Parámetros Mode 2
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `stink_bid_min_price` | $0.02 | Precio mínimo del bid |
| `stink_bid_max_price` | $0.05 | Precio máximo del bid |
| `stink_bid_min_volume` | $50,000 | Volumen mínimo requerido |
| `stink_bid_ttl_minutes` | 30 | Tiempo antes de rotar bid |
| `max_active_stink_bids` | 10 | Máximo de bids concurrentes |
| `stink_bid_stake` | $10 | Stake por stink bid |

#### Flujo Mode 2

**Fase 1: Colocación**
```python
# Calcular precio del bid basado en liquidez
liquidity_factor = min(1.0, volume_24h / 200000)
bid_price = min_price + (max_price - min_price) * liquidity_factor

# Crear StinkBid
stink_bid = StinkBid(
    bid_price=bid_price,
    target_exit=current_price * 0.9,
    stake=10,
    expires_at=now + 30min
)
```

**Fase 2: Monitoreo de Fill**
```python
# En cada market update, verificar si el precio tocó nuestro bid
if best_ask <= stink_bid.bid_price:
    # ¡FILLED! 
    fill_price = best_ask
    exit_price = current_price  # Rebound price
    profit = (exit_price / fill_price - 1) * stake
    # ROI típico: 100-500%
```

**Fase 3: Rotación**
```python
# Cada 30 minutos, expirar bids no llenados
if stink_bid.is_expired:
    del active_stink_bids[bid_id]
    # El mercado puede ser reconsiderado
```

#### Ejemplo de Fill

```
Mercado: "Will BTC hit $100k today?"
Precio actual: $0.45
Stink Bid colocado: $0.03

[Flash Crash ocurre - whale vende en pánico]
Best Ask cae a: $0.025

✅ STINK BID FILLED @ $0.025
→ Exit inmediato @ $0.35 (rebound)
→ ROI: 1300%
→ Profit: $10 → $140
```

---

## 🎰 Estrategia C: Tail Betting

**ID**: `TAIL_BETTING_V1`  
**Archivo**: `src/trading/strategies/tail_strategy.py`

### Concepto
Apuestas de bajo costo ($2) en eventos con baja probabilidad pero alto multiplicador (25-1000x). Basado en el enfoque de @Spon.

### Trigger
```
SI $0.001 < Precio_YES < $0.04
Y  ML_Score > 55%
→  APOSTAR $2
```

### ML Scoring
El score se calcula basándose en:

| Factor | Peso | Descripción |
|--------|------|-------------|
| Crypto keywords | +12% | bitcoin, ethereum, crypto |
| Stock keywords | +8% | nvidia, tesla, apple |
| AI keywords | +8% | ai, openai, gpt |
| Sports keywords | -5% | nba, nfl, sports |
| High multiplier (>500x) | +5% | Bonus por alto multiplicador |
| High volume (>$100k) | +3% | Mercados más líquidos |

### Parámetros
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `max_price` | $0.04 | Precio máximo de entrada |
| `min_price` | $0.001 | Precio mínimo de entrada |
| `min_multiplier` | 25x | Multiplicador mínimo |
| `min_ml_score` | 55% | Score ML mínimo |
| `stake_size` | $2 | Stake fijo por apuesta |

### Matemáticas del Tail Betting
```
100 apuestas × $2 = $200 invertido
Multiplicador promedio: 50x
Para break-even: necesitas 1 win (0.5% hit rate)
Con 2% hit rate: 2 wins × $100 = $200 profit → +100% ROI
```

---

## 🔧 Implementación Técnica

### Base Strategy Pattern

Todas las estrategias heredan de `BaseStrategy`:

```python
class BaseStrategy(ABC):
    @abstractmethod
    async def process_market(self, market: MarketData) -> Optional[TradeSignal]:
        """Evalúa mercado y retorna señal si aplica."""
        pass
    
    @abstractmethod
    def get_config(self) -> Dict:
        """Retorna configuración de la estrategia."""
        pass
```

### TradeSignal Structure

```python
@dataclass
class TradeSignal:
    strategy_id: str          # "SNIPER_MICRO_V1"
    signal_type: SignalType   # BUY, SELL, HOLD
    condition_id: str         # Polymarket condition ID
    outcome: str              # "YES" or "NO"
    entry_price: float        # Precio de entrada
    stake: float              # USD a invertir
    confidence: float         # 0-1
    expected_value: float     # EV calculado
    trigger_reason: str       # "crash_drop_15%_vol_2.5x"
    signal_data: Dict         # Metadata específica
    snapshot_data: Dict       # Estado del mercado (para ML)
```

### Strategy Registry

```python
# Registro y ejecución paralela
strategy_registry.register(ArbitrageStrategy())
strategy_registry.register(SniperStrategy())
strategy_registry.register(TailStrategy())

# Procesar mercado con todas las estrategias
signals = await strategy_registry.process_all(market_data)
```

---

## 📈 Métricas por Estrategia

El sistema trackea métricas independientes por estrategia:

```sql
SELECT 
    strategy_id,
    COUNT(*) as total_signals,
    SUM(CASE WHEN status = 'RESOLVED_WIN' THEN 1 ELSE 0 END) as wins,
    SUM(realized_pnl) as total_pnl
FROM trades
WHERE paper_mode = true
GROUP BY strategy_id;
```

---

## ⚠️ Riesgos por Estrategia

| Estrategia | Riesgo Principal | Mitigación |
|------------|------------------|------------|
| Arbitrage | Datos desactualizados de PredictBase | Max spread 15%, verificación de timestamps |
| Sniper (Crash) | False positives en caídas normales | Requiere volume spike confirmación |
| Sniper (Stink) | Capital bloqueado sin fills | TTL de 30 min, rotación automática |
| Tail | Alta tasa de pérdida (>95%) | Stake bajo ($2), diversificación |

---

## 🔄 Próximos Pasos

1. **Backtesting**: Simular estrategias con datos históricos
2. **XGBoost Training**: Entrenar modelo con `training_data` acumulada
3. **Live Trading**: Activar con capital real después de validar paper results
4. **WebSocket Integration**: Cambiar de polling a WebSocket para Sniper
