# Integración de Agentes IA con Polymarket

## Índice
1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Polymarket Agents Framework](#polymarket-agents-framework)
3. [MCP (Model Context Protocol)](#mcp-model-context-protocol)
4. [Comparativa de Soluciones](#comparativa-de-soluciones)
5. [Arquitectura Propuesta](#arquitectura-propuesta)
6. [Implementación Práctica](#implementación-práctica)
7. [Recomendación Final](#recomendación-final)

---

## Resumen Ejecutivo

Existen dos aproximaciones principales para conectar IA con Polymarket:

| Método | Descripción | Complejidad | Trading |
|--------|-------------|-------------|---------|
| **Polymarket Agents** | Framework oficial de Polymarket | Media | ✅ Sí |
| **MCP Server** | Protocolo estándar para conectar IA | Baja | ❌ Solo lectura |

### Recomendación
- **Para trading automatizado**: Polymarket Agents
- **Para análisis con IA**: MCP Server (más simple)
- **Híbrido**: Usar MCP para análisis + nuestro código para ejecución

---

## Polymarket Agents Framework

### 📋 Información General

| Aspecto | Detalle |
|---------|---------|
| **Repositorio** | [github.com/Polymarket/agents](https://github.com/Polymarket/agents) |
| **Stars** | 1,100+ |
| **Licencia** | MIT (open source) |
| **Lenguaje** | Python 3.9 |
| **Estado** | Último commit: hace 1 año |
| **Contacto** | liam@polymarket.com |

### 🎯 Features Principales

1. **Integración con API de Polymarket**
   - Gamma API para metadata de mercados
   - CLOB API para trading
   - Ejecución de órdenes automatizada

2. **Sistema RAG (Retrieval-Augmented Generation)**
   - ChromaDB para vectorización
   - Búsqueda semántica de mercados
   - Contexto dinámico para LLM

3. **Fuentes de Datos**
   - NewsAPI para noticias en tiempo real
   - Tavily para búsqueda web
   - APIs de mercados de predicción

4. **LLM Tools**
   - Prompts especializados para trading
   - Análisis de sentimiento
   - Superforecasting prompts

### 🏗️ Arquitectura del Framework

```
Polymarket Agents
├── agents/
│   ├── application/
│   │   ├── trade.py          # Trader autónomo principal
│   │   ├── executor.py       # Ejecutor de decisiones LLM
│   │   ├── creator.py        # Creador de mercados
│   │   ├── prompts.py        # Prompts especializados
│   │   └── cron.py           # Scheduler para ejecución periódica
│   │
│   ├── connectors/
│   │   ├── chroma.py         # Vector DB (RAG)
│   │   ├── news.py           # NewsAPI integration
│   │   └── search.py         # Tavily web search
│   │
│   ├── polymarket/
│   │   ├── polymarket.py     # Core API (trading)
│   │   └── gamma.py          # Gamma API (markets)
│   │
│   └── utils/
│       └── objects.py        # Modelos Pydantic
│
├── scripts/
│   └── python/
│       └── cli.py            # CLI principal
│
└── requirements.txt
```

### 🔄 Flujo de Trading Autónomo

```
┌─────────────────────────────────────────────────────────────────┐
│                    ONE BEST TRADE STRATEGY                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. GET EVENTS                                                   │
│     └─► polymarket.get_all_tradeable_events()                   │
│                                                                  │
│  2. FILTER WITH RAG                                              │
│     └─► agent.filter_events_with_rag(events)                    │
│         └─► ChromaDB similarity search                          │
│                                                                  │
│  3. MAP TO MARKETS                                               │
│     └─► agent.map_filtered_events_to_markets()                  │
│                                                                  │
│  4. FILTER MARKETS                                               │
│     └─► agent.filter_markets(markets)                           │
│         └─► LLM evalúa cada mercado                             │
│                                                                  │
│  5. SOURCE BEST TRADE                                            │
│     └─► agent.source_best_trade(market)                         │
│         └─► LLM: superforecaster prompt                         │
│         └─► LLM: one_best_trade prompt                          │
│                                                                  │
│  6. EXECUTE                                                      │
│     └─► polymarket.execute_market_order(market, amount)         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 📝 Prompts Clave del Sistema

#### Superforecaster Prompt
```python
def superforecaster(self, question: str, description: str, outcome: str) -> str:
    """
    Evalúa un mercado usando técnicas de superforecasting
    - Analiza la pregunta del mercado
    - Considera la descripción y contexto
    - Genera probabilidades calibradas
    """
```

#### Market Analyst Prompt
```python
def market_analyst(self) -> str:
    """
    You are a market analyst that takes a description of an event 
    and produces a market forecast. Assign a probability estimate 
    to the event occurring described by the user.
    """
```

#### One Best Trade Prompt
```python
def one_best_trade(self, prediction: str, outcomes: List[str], 
                   outcome_prices: str) -> str:
    """
    Dado: predicción del LLM + precios actuales
    Decide: BUY/SELL, tamaño de posición, outcome
    """
```

### ⚙️ Instalación de Polymarket Agents

```bash
# 1. Clonar repositorio
git clone https://github.com/Polymarket/agents.git
cd agents

# 2. Crear entorno virtual (Python 3.9 requerido)
virtualenv --python=python3.9 .venv
.venv\Scripts\activate  # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar .env
POLYGON_WALLET_PRIVATE_KEY="tu_private_key"
OPENAI_API_KEY="tu_openai_key"
NEWSAPI_API_KEY="opcional"
TAVILY_API_KEY="opcional"

# 5. Exportar PYTHONPATH
set PYTHONPATH=.  # Windows

# 6. Ejecutar
python agents/application/trade.py
```

### 📊 CLI Commands Disponibles

```bash
# Listar mercados
python scripts/python/cli.py get-all-markets --limit 10

# Obtener eventos
python scripts/python/cli.py get-all-events --limit 5

# Preguntar al LLM
python scripts/python/cli.py ask-llm "What markets are trending?"

# LLM + Datos de Polymarket
python scripts/python/cli.py ask-polymarket-llm "Best crypto markets?"

# Ejecutar trader autónomo
python scripts/python/cli.py run-autonomous-trader

# Crear mercado (formato)
python scripts/python/cli.py create-market
```

---

## MCP (Model Context Protocol)

### 📋 ¿Qué es MCP?

El **Model Context Protocol (MCP)** es un estándar abierto creado por Anthropic que actúa como "USB-C para IA" - permite conectar modelos de IA con fuentes de datos externas de manera estandarizada.

### 🔌 MCP Servers para Polymarket

| Server | Lenguaje | Trading | Features | Ideal Para |
|--------|----------|---------|----------|------------|
| **berlinbra/polymarket-mcp** | Python | ❌ No | Simple, 4 tools | Principiantes |
| **0x79de/polymarket-mcp** | Rust | ❌ No | High-perf, caching | Producción HFT |
| **pab1it0/polymarket-mcp** | Python | ❌ No | Docker, orderbook | Análisis profundo |
| **bnorphism/manifold-mcp** | TypeScript | ✅ Sí | Full interaction | Trading agents |

### 🛠️ Core Tools del MCP Server (berlinbra)

| Tool | Propósito | Parámetros | Ejemplo |
|------|-----------|------------|---------|
| `list-markets` | Descubrir mercados | status, limit, offset | "Show 5 open markets" |
| `get-market-info` | Metadata de mercado | market_id | "Details on election" |
| `get-market-prices` | Precios Yes/No | market_id | "Current election odds" |
| `get-market-history` | Datos históricos | market_id, timeframe | "30-day price history" |

### ⚙️ Instalación MCP Server

```bash
# 1. Clonar
git clone https://github.com/berlinbra/polymarket-mcp.git
cd polymarket-mcp

# 2. Instalar con uv
uv pip install -e .

# 3. Crear .env
Key=your_api_key
Funder=your_wallet

# 4. Configurar Claude Desktop (Windows)
# Archivo: %APPDATA%\Claude\claude_desktop_config.json
{
  "mcpServers": {
    "polymarket": {
      "command": "uv",
      "args": ["--directory", "C:\\path\\to\\polymarket-mcp", "run", "polymarket-mcp"],
      "env": {
        "Key": "your_api_key",
        "Funder": "your_wallet"
      }
    }
  }
}

# 5. Reiniciar Claude Desktop
```

### 🎯 Casos de Uso MCP

| Caso de Uso | Descripción | Tools Usados |
|-------------|-------------|--------------|
| Daily Briefing | Resumen de mercados activos | list-markets, get-market-info |
| Trend Analysis | Análisis de movimientos históricos | get-market-history |
| Real-time Odds | Probabilidades instantáneas | get-market-prices |
| RAG Enrichment | Enriquecer RAG con datos | list-markets, get-market-prices |
| Cross-Platform | Comparar con otras plataformas | Multiple MCP servers |

### ⚠️ Limitaciones MCP

- **Solo lectura** - No puede ejecutar trades
- **Rate limiting** - Limitaciones de API
- **Dependencia** - Requiere Claude Desktop o Cursor
- **Sin orderbook** - La versión básica no tiene depth

---

## Comparativa de Soluciones

### Matriz de Decisión

| Criterio | Polymarket Agents | MCP Server | Nuestro Bot |
|----------|-------------------|------------|-------------|
| **Trading** | ✅ Completo | ❌ No | ✅ Completo |
| **LLM Integration** | ✅ OpenAI | ✅ Claude | 🔄 Por añadir |
| **RAG** | ✅ ChromaDB | ❌ No | 🔄 Por añadir |
| **Complejidad** | Alta | Baja | Media |
| **Mantenimiento** | ⚠️ 1 año sin updates | ✅ Activo | ✅ Nosotros |
| **Personalización** | Media | Baja | Alta |
| **Flash Markets** | ❌ No específico | ❌ No | ✅ Optimizado |

### Escenarios de Uso

#### Escenario 1: Solo Análisis (Sin Trading)
**Recomendación**: MCP Server
```
Usuario → Claude Desktop + MCP → Polymarket API → Análisis
```

#### Escenario 2: Trading Autónomo Básico
**Recomendación**: Polymarket Agents
```
Cron → Agents Framework → LLM Decision → Execute Trade
```

#### Escenario 3: HFT en Flash Markets (Como @Account88888)
**Recomendación**: Nuestro Bot + LLM híbrido
```
Flash Market Scanner → Decision Engine → Execute Trade
                           ↑
                    LLM (opcional)
```

---

## Arquitectura Propuesta

### Arquitectura Híbrida Recomendada

```
┌─────────────────────────────────────────────────────────────────┐
│                    POLYMARKET AI BOT v2.0                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │   MCP       │    │  LLM        │    │  News       │          │
│  │   Server    │    │  (OpenAI/   │    │  Connector  │          │
│  │   (Read)    │    │   Claude)   │    │  (NewsAPI)  │          │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘          │
│         │                  │                  │                  │
│         └──────────────────┼──────────────────┘                  │
│                            │                                     │
│                    ┌───────▼───────┐                             │
│                    │   Decision    │                             │
│                    │    Engine     │                             │
│                    │  (RAG + LLM)  │                             │
│                    └───────┬───────┘                             │
│                            │                                     │
│         ┌──────────────────┼──────────────────┐                  │
│         │                  │                  │                  │
│  ┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐          │
│  │  Strategy   │    │    Risk     │    │   Flash     │          │
│  │  Selector   │    │   Manager   │    │   Market    │          │
│  │             │    │             │    │   Scanner   │          │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘          │
│         │                  │                  │                  │
│         └──────────────────┼──────────────────┘                  │
│                            │                                     │
│                    ┌───────▼───────┐                             │
│                    │    Order      │                             │
│                    │   Executor    │                             │
│                    │  (py-clob)    │                             │
│                    └───────────────┘                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Componentes Nuevos a Integrar

#### 1. LLM Decision Engine
```python
# src/ai/decision_engine.py
class LLMDecisionEngine:
    def __init__(self, model="gpt-4"):
        self.llm = ChatOpenAI(model=model)
        
    def should_trade(self, market_data: dict, news: list) -> dict:
        """
        Analiza mercado + noticias y decide si operar
        Returns: {action: BUY/SELL/HOLD, confidence: 0-1, reasoning: str}
        """
        
    def analyze_flash_market(self, btc_price_trend: list) -> dict:
        """
        Análisis específico para flash markets
        """
```

#### 2. RAG Market Analyzer
```python
# src/ai/rag_analyzer.py
class MarketRAG:
    def __init__(self):
        self.vectordb = Chroma(persist_directory="./market_db")
        
    def find_similar_markets(self, query: str) -> list:
        """Busca mercados similares para contexto"""
        
    def enrich_context(self, market_id: str) -> str:
        """Enriquece contexto con datos históricos"""
```

#### 3. MCP Integration Layer
```python
# src/ai/mcp_client.py
class MCPClient:
    """Cliente para comunicarse con MCP servers"""
    
    def list_markets(self, status="open", limit=10):
        """Usa MCP para listar mercados"""
        
    def get_prices(self, market_id: str):
        """Obtiene precios via MCP"""
```

---

## Implementación Práctica

### Paso 1: Añadir OpenAI al Proyecto

```bash
# Instalar dependencias
pip install openai langchain langchain-openai chromadb

# Añadir a .env
OPENAI_API_KEY=sk-...
```

### Paso 2: Crear Decision Engine Básico

```python
# src/ai/decision_engine.py
import os
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

class TradingDecisionEngine:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4",
            temperature=0.1
        )
        
    def analyze_flash_market(self, 
                             market: str,
                             current_prices: dict,
                             btc_trend: str) -> dict:
        """
        Analiza un flash market y decide si operar
        """
        system_prompt = """
        You are a professional crypto trader specializing in 15-minute flash markets.
        Analyze the given market data and provide a trading decision.
        
        Consider:
        1. Current BTC price trend (last 15 min)
        2. Current Yes/No prices
        3. Historical patterns
        
        Respond in JSON format:
        {
            "action": "BUY_YES" | "BUY_NO" | "HOLD",
            "confidence": 0.0-1.0,
            "size_percent": 0-100,
            "reasoning": "brief explanation"
        }
        """
        
        user_prompt = f"""
        Market: {market}
        Current Prices: Yes=${current_prices['yes']}, No=${current_prices['no']}
        BTC Trend (15min): {btc_trend}
        
        What's your trading decision?
        """
        
        response = self.llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        
        return self._parse_response(response.content)
```

### Paso 3: Integrar con Scanner Existente

```python
# Modificar src/scanner/market_scanner.py
from src.ai.decision_engine import TradingDecisionEngine

class MarketScannerWithAI(MarketScanner):
    def __init__(self):
        super().__init__()
        self.ai_engine = TradingDecisionEngine()
        
    async def scan_with_ai_decision(self):
        """Escanea mercados y usa IA para decidir"""
        flash_markets = await self.scan_flash_markets()
        
        for market in flash_markets:
            # Obtener datos
            prices = await self.get_current_prices(market)
            btc_trend = await self.get_btc_trend()
            
            # Decisión IA
            decision = self.ai_engine.analyze_flash_market(
                market=market.question,
                current_prices=prices,
                btc_trend=btc_trend
            )
            
            if decision['action'] != 'HOLD' and decision['confidence'] > 0.7:
                yield {
                    'market': market,
                    'decision': decision
                }
```

---

## Recomendación Final

### Para Tu Caso Específico ($56.86)

#### Opción A: Híbrido Simple (Recomendado)
1. **Usa tu código actual** para flash markets
2. **Añade OpenAI** para decisiones de dirección (Up/Down)
3. **Sin MCP** - overhead innecesario para tu caso

```
Costo adicional: ~$5-10/mes en API OpenAI
Beneficio: Decisiones más informadas
```

#### Opción B: Full Polymarket Agents
1. Clonar y adaptar Polymarket Agents
2. Requiere refactorizar mucho código
3. Más complejo pero más features

```
Costo: Solo API keys
Riesgo: Framework sin mantenimiento
```

#### Opción C: MCP + Manual Trading
1. Instalar MCP en Claude Desktop
2. Usar Claude para análisis
3. Ejecutar trades manualmente

```
Costo: $0 (Claude ya lo tienes)
Beneficio: Análisis profundo sin código
```

### Próximos Pasos Sugeridos

1. **Inmediato**: Añadir OpenAI al proyecto actual
2. **Corto plazo**: Implementar Decision Engine básico
3. **Medio plazo**: Añadir RAG con ChromaDB
4. **Largo plazo**: Considerar MCP para análisis avanzado

---

## Referencias

### Repositorios
- [Polymarket Agents](https://github.com/Polymarket/agents) - Framework oficial
- [py-clob-client](https://github.com/Polymarket/py-clob-client) - Cliente Python CLOB
- [berlinbra/polymarket-mcp](https://github.com/berlinbra/polymarket-mcp) - MCP Server básico

### Lectura Recomendada
- [Prediction Markets: Bottlenecks and Unlocks](https://mirror.xyz/1kx.eth/jnQhA56Kx9p3RODKiGzqzHGGEODpbskivUUNdd7hwh0)
- [Crypto + AI Applications (Vitalik)](https://vitalik.eth.limo/general/2024/01/30/cryptoai.html)
- [Superforecasting (HBR)](https://hbr.org/2016/05/superforecasting-how-to-upgrade-your-companys-judgment)

### APIs
- Gamma API: `https://gamma-api.polymarket.com`
- CLOB API: `https://clob.polymarket.com`
- Data API: `https://data-api.polymarket.com` (descubierto en nuestro scraping)
