# Polymarket API Integration Guide

## 📋 Overview

Este documento detalla cómo configurar e integrar el bot con la API de Polymarket para trading automatizado.

## 🔐 1. Requisitos Previos

### 1.1 Crear Cuenta en Polymarket

1. **Visita**: https://polymarket.com
2. **Registro**: Puedes registrarte con:
   - **Email (Magic Link)** - Recomendado para bots
   - **Wallet externa** (MetaMask, etc.)
   - **Social login** (Google, Discord, etc.)

3. **Verificación KYC**: 
   - Polymarket requiere verificación de identidad para trading
   - Proceso toma 1-3 días hábiles
   - Necesitas: ID válido + selfie

### 1.2 Depositar Fondos

```
Polymarket opera en Polygon (MATIC) con USDC como moneda base.

1. Deposita USDC directamente desde:
   - Coinbase
   - Bridge desde Ethereum
   - Compra con tarjeta (en la app)

2. Mínimo recomendado para testing: $50-100 USDC
3. Para producción: Según tu estrategia de capital
```

## 🔑 2. Obtener Credenciales API

### 2.1 Tipo de Wallet y Signature Type

Polymarket usa diferentes métodos de firma según cómo creaste tu cuenta:

| Método de Registro | Signature Type | Descripción |
|-------------------|----------------|-------------|
| Wallet Externa (MetaMask) | `0` (EOA) | Firma directa con private key. El funder es la dirección EOA y necesitas POL para pagar gas |
| Email (Magic Link/Google) | `1` (POLY_PROXY) | Proxy wallet personalizado. Requiere exportar PK desde Polymarket.com |
| Gnosis Safe (Browser) | `2` (GNOSIS_SAFE) | Proxy wallet multisig (**MÁS COMÚN**). Usar para usuarios nuevos que no son EOA ni Magic |

> ⚠️ **IMPORTANTE**: La dirección que ves en Polymarket.com es tu **proxy wallet** (funder). 
> Estas wallets se despliegan automáticamente en tu primer login.

### 2.2 Niveles de Autenticación (L1 y L2)

Polymarket usa **dos niveles de autenticación**:

#### L1 Authentication (Private Key)
- Usa la **private key** de tu wallet para firmar mensajes EIP-712
- Sirve para: Crear/derivar credenciales API (L2)
- **Es como tu "master key"**

#### L2 Authentication (API Credentials)
- Usa credenciales API (`apiKey`, `secret`, `passphrase`)
- Sirve para: Trading, cancelar órdenes, ver posiciones
- Se genera a partir de L1

```python
# El py-clob-client maneja esto automáticamente:
from py_clob_client.client import ClobClient

# 1. Crear cliente con L1 (private key)
client = ClobClient(
    host="https://clob.polymarket.com",
    key=PRIVATE_KEY,  # L1 auth
    chain_id=137,
)

# 2. Derivar credenciales L2 automáticamente
api_creds = client.create_or_derive_api_creds()
# Returns: {"apiKey": "...", "secret": "...", "passphrase": "..."}

# 3. Configurar L2 para trading
client.set_api_creds(api_creds)
```

### 2.3 Obtener Private Key

#### Opción A: Wallet Externa (EOA - MetaMask)

```bash
# Si usas MetaMask o wallet externa:
# 1. Exporta tu private key desde la wallet
# 2. NUNCA compartas esta key
# 3. Usa variables de entorno, no hardcodees
# 4. Necesitarás POL (MATIC) para gas
```

#### Opción B: Cuenta con Email/Google (POLY_PROXY o GNOSIS_SAFE)

#### Opción B: Cuenta con Email/Google (POLY_PROXY o GNOSIS_SAFE)

Si creaste cuenta con email/Google, necesitas extraer las credenciales desde el navegador:

```javascript
// En la consola del navegador (F12) mientras estás logueado en polymarket.com:

// 1. Obtener la API Key y Secret (si ya existen)
const creds = JSON.parse(localStorage.getItem('polymarket_api_creds'));
if (creds) {
    console.log('API Key:', creds.apiKey);
    console.log('API Secret:', creds.secret);
    console.log('Passphrase:', creds.passphrase);
}

// 2. Obtener la dirección del funder (tu proxy wallet)
const auth = JSON.parse(localStorage.getItem('polymarket_auth'));
console.log('Funder Address (proxy wallet):', auth.user.proxyWallet || auth.user.address);

// 3. Para obtener la private key, ve a:
// Polymarket.com → Settings → Export Wallet
```

> 💡 **TIP**: La forma más fácil de obtener tus credenciales es ir a:
> **polymarket.com/settings?tab=builder** → Builder Keys → Create New

### 2.4 Obtener Funder Address

La `funder_address` es la dirección que tiene los fondos en Polymarket (tu **proxy wallet**):

```javascript
// En consola del navegador en polymarket.com:
const auth = JSON.parse(localStorage.getItem('polymarket_auth'));
console.log('Your Funder Address:', auth.user.proxyWallet);
```

> ⚠️ **NOTA**: La dirección del funder es la que aparece en tu perfil de Polymarket, 
> NO es necesariamente tu EOA wallet. Es una proxy wallet que se despliega al hacer login.

## ⚙️ 3. Configuración del Bot

### 3.1 Crear archivo .env

```bash
# Copiar el template
cp .env.example .env
```

### 3.2 Configurar Variables de Entorno

```env
# ============================================
# POLYMARKET CREDENTIALS (REQUIRED)
# ============================================

# Tu private key (SIN el prefijo 0x)
# ⚠️ NUNCA commitees este archivo a git
POLYMARKET_PRIVATE_KEY=abc123...your_private_key_here

# Tu dirección de funder (con prefijo 0x)
POLYMARKET_FUNDER_ADDRESS=0x1234567890abcdef...

# Tipo de firma (ver tabla arriba)
# 0 = EOA (MetaMask, wallet externa - necesitas POL para gas)
# 1 = POLY_PROXY (Magic/Email - más común para cuentas email)
# 2 = GNOSIS_SAFE (Browser proxy - más común para nuevos usuarios)
SIGNATURE_TYPE=2

# ============================================
# TRADING PARAMETERS
# ============================================

# Tamaño máximo por posición (USDC)
MAX_POSITION_SIZE_USDC=100

# Profit mínimo para entrar (0.04 = 4 centavos)
MIN_PROFIT_THRESHOLD=0.04

# Pérdida máxima diaria antes de parar
MAX_DAILY_LOSS_USDC=50

# Exposición total máxima
MAX_TOTAL_EXPOSURE_USDC=500

# ============================================
# OPERATION MODE
# ============================================

# true = simulación, false = dinero real
PAPER_TRADING=true

# development o production
ENVIRONMENT=development

# DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# ============================================
# TELEGRAM ALERTS (OPTIONAL)
# ============================================

# Crear bot en @BotFather
TELEGRAM_BOT_TOKEN=

# Tu chat ID (usar @userinfobot)
TELEGRAM_CHAT_ID=

# ============================================
# DATABASE
# ============================================

# SQLite por defecto (local)
DATABASE_URL=sqlite+aiosqlite:///./polymarket_bot.db
```

### 3.3 Seguridad de Credenciales

```bash
# Asegurar que .env está en .gitignore
echo ".env" >> .gitignore
echo "*.db" >> .gitignore

# Verificar que no está trackeado
git status
```

## 🔌 4. Arquitectura de la API

### 4.1 Endpoints Principales

Polymarket tiene dos APIs principales:

```
┌─────────────────────────────────────────────────────────────┐
│                    POLYMARKET APIs                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────┐    ┌─────────────────────┐        │
│  │   GAMMA API         │    │   CLOB API          │        │
│  │   (Market Data)     │    │   (Trading)         │        │
│  ├─────────────────────┤    ├─────────────────────┤        │
│  │ • List markets      │    │ • Place orders      │        │
│  │ • Market details    │    │ • Cancel orders     │        │
│  │ • Historical data   │    │ • Get positions     │        │
│  │ • No auth needed    │    │ • Requires auth     │        │
│  └─────────────────────┘    └─────────────────────┘        │
│           │                          │                      │
│           ▼                          ▼                      │
│  gamma-api.polymarket.com    clob.polymarket.com           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Flujo de Autenticación

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Bot        │     │  py-clob     │     │  Polymarket  │
│              │     │  client      │     │  CLOB        │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │ 1. Initialize      │                    │
       │ (private_key,      │                    │
       │  funder_address)   │                    │
       │───────────────────>│                    │
       │                    │                    │
       │                    │ 2. Derive API      │
       │                    │    credentials     │
       │                    │───────────────────>│
       │                    │                    │
       │                    │ 3. Return API      │
       │                    │    key/secret      │
       │                    │<───────────────────│
       │                    │                    │
       │ 4. Ready to trade  │                    │
       │<───────────────────│                    │
       │                    │                    │
       │ 5. Place order     │                    │
       │───────────────────>│ 6. Sign & submit   │
       │                    │───────────────────>│
       │                    │                    │
       │                    │ 7. Order response  │
       │                    │<───────────────────│
       │ 8. Result          │                    │
       │<───────────────────│                    │
```

### 4.3 Código de Inicialización

```python
# src/trading/order_executor.py - Inicialización

from py_clob_client.client import ClobClient

async def initialize(self) -> None:
    """Initialize the CLOB client."""
    
    self._client = ClobClient(
        host="https://clob.polymarket.com",
        key=self.private_key.get_secret_value(),  # Tu private key
        chain_id=137,  # Polygon mainnet
        signature_type=self.signature_type,  # 0, 1, o 2
        funder=self.funder_address,  # Tu wallet address
    )
    
    # Derivar credenciales API automáticamente
    self._client.set_api_creds(
        self._client.create_or_derive_api_creds()
    )
```

## 📊 5. Flujo de Trading

### 5.1 Ciclo de Vida de una Operación

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRADING WORKFLOW                              │
└─────────────────────────────────────────────────────────────────┘

1. SCAN           2. DETECT           3. VALIDATE         4. EXECUTE
┌─────────┐      ┌─────────┐         ┌─────────┐        ┌─────────┐
│ Market  │─────>│ Spread  │────────>│  Risk   │───────>│  Order  │
│ Scanner │      │Analyzer │         │ Manager │        │Executor │
└─────────┘      └─────────┘         └─────────┘        └─────────┘
     │                │                   │                  │
     ▼                ▼                   ▼                  ▼
  Gamma API      Calculate           Check limits       Place orders
  WebSocket      UP + DOWN           Max exposure       Both sides
                 < $1.00?            Daily loss         simultaneously
```

### 5.2 Ejemplo de Ejecución

```python
# Cuando se detecta oportunidad:

# 1. Detectar spread < $1.00
up_price = 0.48   # Precio de UP token
down_price = 0.49  # Precio de DOWN token
total = 0.97       # Costo total
profit = 0.03      # Profit garantizado ($0.03 por contrato)

# 2. Validar con Risk Manager
if risk_manager.can_open_position(opportunity, size=100):
    
    # 3. Ejecutar ambas órdenes
    up_order = await executor.place_market_order(
        token_id=market.up_token_id,
        side=Side.BUY,
        amount=50,  # $50 USDC
    )
    
    down_order = await executor.place_market_order(
        token_id=market.down_token_id,
        side=Side.BUY,
        amount=50,  # $50 USDC
    )
    
    # 4. Registrar posición
    position_manager.record_position(up_order, down_order)
```

## 🚀 6. Proceso de Puesta en Marcha

### 6.1 Checklist Pre-Producción

```bash
# 1. Verificar configuración
poetry run polybot status

# 2. Testear conexión API
poetry run polybot test-connection

# 3. Escanear mercados (sin trading)
poetry run polybot scan

# 4. Ejecutar dry-run (48 horas mínimo)
poetry run polybot dry-run --duration 2880 --size 10

# 5. Generar reporte de validación
poetry run polybot validate --hours 48

# 6. Revisar checklist
poetry run polybot checklist
```

### 6.2 Pasos para Go-Live

```
FASE 1: Paper Trading (1-2 semanas)
├── Ejecutar con PAPER_TRADING=true
├── Validar lógica de detección
├── Verificar no hay crashes
└── Analizar reportes de simulación

FASE 2: Small Stakes (1 semana)
├── PAPER_TRADING=false
├── MAX_POSITION_SIZE_USDC=1
├── Monitorear cada trade manualmente
└── Verificar slippage real vs simulado

FASE 3: Escalar Gradualmente
├── Incrementar posición a $10, $50, $100
├── Ajustar thresholds según performance
├── Configurar alertas Telegram
└── Revisar reportes diarios

FASE 4: Producción Completa
├── Desplegar en VPS (us-east-1)
├── Configurar monitoring 24/7
├── Establecer dead-man switch
└── Backup diario de DB
```

## 🛡️ 7. Seguridad

### 7.1 Mejores Prácticas

```bash
# NUNCA hacer esto:
POLYMARKET_PRIVATE_KEY=abc123  # En código fuente
git add .env                    # Commitear .env

# SIEMPRE hacer esto:
- Usar variables de entorno
- Mantener .env en .gitignore
- Usar secrets manager en producción
- Rotar API keys periódicamente
- Limitar permisos de la wallet
```

### 7.2 Wallet Dedicada

```
Recomendación: Crear wallet SOLO para el bot

1. Crear nueva wallet en MetaMask
2. Transferir solo capital de trading
3. No usar para otras actividades
4. Mantener backup seguro de seed phrase
```

## 📡 8. WebSocket Real-Time

### 8.1 Conexión a Order Book

```python
# src/scanner/websocket_feed.py

WEBSOCKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

async def subscribe(self, token_id: str):
    """Subscribe to real-time orderbook updates."""
    
    message = {
        "type": "subscribe",
        "channel": "market",
        "assets_ids": [token_id],
    }
    
    await self.ws.send(json.dumps(message))
```

### 8.2 Estructura de Mensajes

```json
// Orderbook Update
{
    "event_type": "book",
    "asset_id": "0x123...",
    "market": "0xabc...",
    "bids": [
        {"price": "0.48", "size": "1000"},
        {"price": "0.47", "size": "500"}
    ],
    "asks": [
        {"price": "0.52", "size": "800"},
        {"price": "0.53", "size": "400"}
    ],
    "timestamp": 1704067200000
}
```

## 🔧 9. Troubleshooting

### 9.1 Errores Comunes

| Error | Causa | Solución |
|-------|-------|----------|
| `Invalid signature` | Signature type incorrecto | Verificar SIGNATURE_TYPE en .env |
| `INVALID_SIGNATURE` | Private key o funder incorrectos | Verificar credenciales |
| `L2_AUTH_NOT_AVAILABLE` | Faltan API credentials | Llamar `create_or_derive_api_creds()` primero |
| `Insufficient balance` | No hay fondos | Depositar USDC en Polymarket |
| `Insufficient allowance` | Falta aprobar tokens | Aprobar USDC y Conditional Tokens |
| `Order rejected` | Precio fuera de mercado | Ajustar precio o usar market order |
| `Rate limited` | Demasiadas requests | Implementar rate limiting |
| `NONCE_ALREADY_USED` | Nonce repetido | Usar nonce diferente o reset |

### 9.2 Rate Limits de la API

| Endpoint | Límite | Tipo |
|----------|--------|------|
| General CLOB | 9000 req/10s | Throttle |
| POST /order | 500/s burst, 60/s sustained | Trading |
| DELETE /order | 300/s burst, 50/s sustained | Trading |
| GET /book | 1500 req/10s | Market Data |
| GAMMA /markets | 300 req/10s | Market Data |

### 9.3 Logs de Debug

```bash
# Activar logs detallados
LOG_LEVEL=DEBUG poetry run polybot run --paper --verbose

# Ver logs en tiempo real
tail -f logs/polybot.log
```

## 💶 10. Guía de Test con €50

### 10.1 Preparación (€50 ≈ $55 USDC)

```
PRESUPUESTO DE TEST RECOMENDADO:
├── Capital de trading: $40 USDC
├── Reserva para fees: $10 USDC  
├── Gas (si EOA): ~$5 en POL/MATIC
└── Total depositado: ~$55 USDC
```

### 10.2 Pasos para Iniciar Test Real

```bash
# PASO 1: Obtener credenciales
# -----------------------------------------
# Ir a polymarket.com/settings?tab=builder
# - Click "Builder Keys" → "+ Create New"
# - Guardar: apiKey, secret, passphrase

# PASO 2: Configurar .env
# -----------------------------------------
# Editar tu archivo .env:

POLYMARKET_PRIVATE_KEY=tu_private_key_aqui
POLYMARKET_FUNDER_ADDRESS=0x_tu_proxy_wallet_aqui
SIGNATURE_TYPE=2  # GNOSIS_SAFE para la mayoría

# Parámetros conservadores para test:
MAX_POSITION_SIZE_USDC=10   # Solo $10 por posición
MIN_PROFIT_THRESHOLD=0.03   # 3 centavos mínimo
MAX_DAILY_LOSS_USDC=15      # Stop si pierdes $15
MAX_TOTAL_EXPOSURE_USDC=40  # Máximo $40 en riesgo

PAPER_TRADING=false  # IMPORTANTE: false para real
```

### 10.3 Comandos de Verificación

```bash
# PASO 3: Verificar conexión a la API
poetry run polybot test-connection

# PASO 4: Ver mercados disponibles
poetry run polybot scan

# PASO 5: Ejecutar dry-run de 30 minutos
poetry run polybot dry-run --duration 30 --size 5

# PASO 6: Ver reporte de validación
poetry run polybot validate

# PASO 7: Si todo OK, ejecutar en modo real
poetry run polybot run
```

### 10.4 Monitoreo Durante Test

```bash
# Terminal 1: Bot corriendo
poetry run polybot run --verbose

# Terminal 2: Dashboard
poetry run polybot dashboard

# Terminal 3: Ver P&L en tiempo real
poetry run polybot pnl --live
```

### 10.5 Qué Esperar con €50

```
CON $55 USDC Y ESTRATEGIA CONSERVADORA:

📊 Operaciones esperadas: 5-15 por día (mercados flash)
💰 Profit por trade: $0.02-0.05 (si spread < $1.00)
📈 ROI esperado: 0.5%-2% diario (si hay oportunidades)
⚠️  Riesgo: Bajo (delta-neutral, pero no zero-risk)

ESCENARIOS:
├── Mejor caso: +$1-3/día con buenas oportunidades
├── Caso normal: +$0.10-0.50/día 
├── Peor caso: -$0.50-1/día (spreads adversos)
└── Black swan: Pérdida total si bug o API down
```

## 📚 11. Referencias

- **Polymarket Docs**: https://docs.polymarket.com
- **CLOB Authentication**: https://docs.polymarket.com/developers/CLOB/authentication
- **CLOB Quickstart**: https://docs.polymarket.com/developers/CLOB/quickstart
- **Builder Profile**: https://polymarket.com/settings?tab=builder
- **py-clob-client**: https://github.com/Polymarket/py-clob-client
- **Gamma API Markets**: https://docs.polymarket.com/developers/gamma-markets-api/get-markets

---

## ⚡ Quick Start (Test con €50)

```bash
# 1. Instalar dependencias
poetry install

# 2. Obtener credenciales de Polymarket
# Ir a: polymarket.com/settings?tab=builder
# Click: Builder Keys → + Create New

# 3. Configurar credenciales
cp .env.example .env
# Editar .env con tus credenciales

# 4. Verificar conexión
poetry run polybot test-connection

# 5. Ejecutar validación (30 min dry-run)
poetry run polybot dry-run --duration 30 --size 5

# 6. Ver reporte
poetry run polybot validate

# 7. Si todo OK, iniciar en modo real (¡CON CUIDADO!)
poetry run polybot run
```

---

*Documento creado: 2024-12-30*
*Última actualización: 2025-01-XX*
