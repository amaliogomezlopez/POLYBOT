# 🧹 CLEANUP: PredictBase → Internal ARB

**Fecha**: 2 Enero 2026  
**Motivo**: Análisis forense demostró que PredictBase tiene 0 liquidez (todas las opciones = $0.00)

---

## 📋 RESUMEN DE CAMBIOS

### 1. Nueva Estrategia: `ARB_INTERNAL_V1`

**Archivo**: `src/trading/strategies/internal_arb.py`

```
LÓGICA:
  Para cada mercado binario de Polymarket:
    1. Obtener best_ask(YES) y best_ask(NO)
    2. Calcular: Cost = YES + NO
    3. Si Cost < 0.99 (dejando 1% para fees):
       → SEÑAL: "Buy Both Sides" (Compra Sintética del Dólar)
       → ROI = (1.00 - Cost) / Cost

VENTAJAS:
  ✅ Sin riesgo (ambos outcomes cubiertos)
  ✅ No requiere predicción
  ✅ Ejecución rápida (sync, por mercado)
  ✅ Usa infraestructura existente del scanner
```

### 2. Daemon Actualizado

**Archivo**: `scripts/multi_strategy_daemon.py`

- ❌ Eliminado: Import de `PredictBaseClient`
- ❌ Eliminado: Variable `PB_AVAILABLE` (ahora siempre False)
- ❌ Eliminado: Inicialización del cliente PredictBase
- ❌ Eliminado: `_run_arb_batch_scan()` que usaba PredictBase
- ✅ Agregado: Import de `InternalArbStrategy`
- ✅ Agregado: Registro de `InternalArbStrategy` en strategies

### 3. Dashboard Actualizado

**Archivo**: `src/dashboard/templates/index.html`

- Tarjeta "ARB PREDICTBASE" → "INTERNAL ARB"
- Badge cambiado de "PREDICTBASE" a "RISK-FREE"
- JavaScript actualizado para mostrar datos de `ARB_INTERNAL_V1`

### 4. Module Exports

**Archivo**: `src/trading/strategies/__init__.py`

- `ArbitrageStrategy` marcado como DEPRECATED
- `InternalArbStrategy` agregado a exports

---

## 🗂️ ARCHIVOS MODIFICADOS

| Archivo | Cambio |
|---------|--------|
| `src/trading/strategies/internal_arb.py` | **NUEVO** - Estrategia Internal ARB |
| `src/trading/strategies/__init__.py` | Actualizado exports |
| `src/trading/strategies/base_strategy.py` | Agregado campo `liquidity` a MarketData |
| `scripts/multi_strategy_daemon.py` | Removido PredictBase, agregado Internal ARB |
| `src/dashboard/templates/index.html` | Actualizada tarjeta ARB |
| `scripts/cleanup_predictbase.sh` | **NUEVO** - Script de limpieza VPS |

---

## 🗑️ ARCHIVOS DEPRECADOS (No eliminados)

Estos archivos ya no se usan pero se mantienen por referencia:

- `src/exchanges/predictbase_client.py` - Cliente API PredictBase
- `src/scanner/arb_scanner.py` - Scanner cross-exchange

---

## 📦 DESPLIEGUE EN VPS

### Opción 1: Script Automático

```bash
# Desde máquina local:
scp scripts/cleanup_predictbase.sh root@94.143.138.8:/opt/polymarket-bot/
ssh root@94.143.138.8 "cd /opt/polymarket-bot && bash scripts/cleanup_predictbase.sh"
```

### Opción 2: Manual

```bash
# Conectar al VPS
ssh root@94.143.138.8

# Ir al directorio
cd /opt/polymarket-bot
source venv/bin/activate

# Parar daemon
pkill -f multi_strategy_daemon.py

# Actualizar código
git pull origin main

# Reiniciar daemon
nohup python scripts/multi_strategy_daemon.py --daemon --interval 60 > logs/daemon.log 2>&1 &

# Verificar
tail -f logs/multi_strategy.log
```

---

## ✅ VERIFICACIÓN

Después de desplegar, verificar:

1. **Logs muestran Internal ARB**:
   ```
   grep "ARB_INTERNAL_V1" logs/multi_strategy.log
   ```

2. **No hay errores de PredictBase**:
   ```
   grep -i "predictbase\|pb_client" logs/multi_strategy.log
   ```

3. **Dashboard muestra "INTERNAL ARB"**:
   - Ir a http://94.143.138.8:8000
   - Login: polybot / Poly2026Dashboard!
   - Verificar tarjeta dice "INTERNAL ARB" no "PREDICTBASE"

---

## 📊 MÉTRICAS ESPERADAS

| Métrica | Antes (PredictBase) | Después (Internal ARB) |
|---------|---------------------|------------------------|
| Oportunidades/día | 0 (sin liquidez) | 0-5 (raro en mercados eficientes) |
| ROI por trade | N/A | 1-10% |
| Riesgo | N/A | 0% (sin riesgo) |
| Latencia detección | ~5s batch | ~10ms per-market |

**Nota**: Los mercados eficientes raramente tienen sum(YES+NO) < 0.99. 
Esta estrategia es más útil como "safety net" que como generador de trades.

---

## 🔗 CREDENCIALES VPS

```
IP:       94.143.138.8
User:     root
Password: p4RCcQUr

Dashboard: http://94.143.138.8:8000
User:      polybot
Password:  Poly2026Dashboard!
```
