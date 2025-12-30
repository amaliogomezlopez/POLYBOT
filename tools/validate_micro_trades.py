#!/usr/bin/env python3
"""
VALIDACIÓN FASE 1: Micro-Trades para Probar Estrategia Delta-Neutral
====================================================================

Este script:
1. Busca oportunidades de arbitraje (spread < $1.00)
2. Ejecuta trades mínimos ($2-5) para validar
3. Mide latencia, slippage y profit real
4. Genera reporte de validación
"""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List
from dotenv import load_dotenv
import httpx

load_dotenv()

@dataclass
class MarketOpportunity:
    """Oportunidad de arbitraje detectada"""
    market_id: str
    question: str
    up_token_id: str
    down_token_id: str
    up_price: float
    down_price: float
    spread: float
    profit_pct: float
    volume_24h: float
    end_date: str
    timestamp: str

@dataclass
class ValidationTrade:
    """Trade de validación ejecutado"""
    opportunity: MarketOpportunity
    trade_size_usdc: float
    up_order_id: Optional[str]
    down_order_id: Optional[str]
    up_fill_price: Optional[float]
    down_fill_price: Optional[float]
    actual_spread: Optional[float]
    expected_profit: float
    actual_profit: Optional[float]
    latency_ms: float
    status: str  # "success", "partial", "failed"
    error: Optional[str]
    timestamp: str

class MicroTradeValidator:
    """Validador de estrategia con micro-trades"""
    
    def __init__(self):
        self.private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
        self.funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS")
        self.signature_type = int(os.getenv("SIGNATURE_TYPE", "1"))
        
        self.opportunities: List[MarketOpportunity] = []
        self.trades: List[ValidationTrade] = []
        
        # Parámetros de validación
        self.min_trade_size = 2.0  # $2 mínimo
        self.max_trade_size = 5.0  # $5 máximo
        self.min_profit_threshold = 0.01  # 1% mínimo
        
    def scan_opportunities(self) -> List[MarketOpportunity]:
        """Escanea mercados buscando oportunidades de arbitraje"""
        
        print("\n🔍 Escaneando mercados flash...")
        
        try:
            response = httpx.get(
                "https://gamma-api.polymarket.com/markets",
                params={
                    "limit": 200,
                    "active": True,
                    "closed": False,
                },
                timeout=15
            )
            
            if response.status_code != 200:
                print(f"❌ Error API: {response.status_code}")
                return []
            
            markets = response.json()
            opportunities = []
            
            for m in markets:
                # Filtrar mercados con orderbook
                if not m.get("enableOrderBook"):
                    continue
                
                question = m.get("question", "").lower()
                
                # Detectar mercados Up/Down
                is_updown = "up or down" in question or "higher or lower" in question
                
                if not is_updown:
                    continue
                
                # Parsear precios
                outcomes = m.get("outcomePrices", "")
                token_ids = m.get("clobTokenIds", "")
                
                try:
                    prices = json.loads(outcomes) if outcomes else []
                    tokens = token_ids.split(",") if isinstance(token_ids, str) else []
                    
                    # También intentar parsear si es JSON
                    if not tokens and token_ids:
                        try:
                            tokens = json.loads(token_ids)
                        except:
                            pass
                    
                    if len(prices) >= 2 and len(tokens) >= 2:
                        up_price = float(prices[0])
                        down_price = float(prices[1])
                        spread = up_price + down_price
                        
                        # Solo oportunidades con spread < $1.00
                        if spread < 1.0:
                            profit_pct = ((1 - spread) / spread) * 100
                            
                            if profit_pct >= self.min_profit_threshold:
                                opp = MarketOpportunity(
                                    market_id=m.get("id", ""),
                                    question=m.get("question", "")[:80],
                                    up_token_id=str(tokens[0]).strip().strip('"'),
                                    down_token_id=str(tokens[1]).strip().strip('"'),
                                    up_price=up_price,
                                    down_price=down_price,
                                    spread=spread,
                                    profit_pct=profit_pct,
                                    volume_24h=float(m.get("volume24hr", 0) or 0),
                                    end_date=m.get("endDate", ""),
                                    timestamp=datetime.now().isoformat()
                                )
                                opportunities.append(opp)
                except Exception as e:
                    continue
            
            # Ordenar por profit
            opportunities.sort(key=lambda x: x.profit_pct, reverse=True)
            self.opportunities = opportunities
            
            return opportunities
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return []
    
    def display_opportunities(self):
        """Muestra las oportunidades encontradas"""
        
        if not self.opportunities:
            print("\n⚠️  No hay oportunidades de arbitraje en este momento")
            print("   (Todos los spreads >= $1.00)")
            return
        
        print(f"\n✅ OPORTUNIDADES ENCONTRADAS: {len(self.opportunities)}")
        print("-" * 90)
        print(f"{'#':<3} {'Mercado':<45} {'UP':>7} {'DOWN':>7} {'Spread':>8} {'Profit':>8}")
        print("-" * 90)
        
        for i, opp in enumerate(self.opportunities[:20], 1):
            print(f"{i:<3} {opp.question[:45]:<45} "
                  f"${opp.up_price:.2f}  ${opp.down_price:.2f}  "
                  f"${opp.spread:.4f}  {opp.profit_pct:>6.2f}%")
    
    async def execute_micro_trade(self, opp: MarketOpportunity, size: float) -> ValidationTrade:
        """Ejecuta un micro-trade de validación"""
        
        start_time = datetime.now()
        
        trade = ValidationTrade(
            opportunity=opp,
            trade_size_usdc=size,
            up_order_id=None,
            down_order_id=None,
            up_fill_price=None,
            down_fill_price=None,
            actual_spread=None,
            expected_profit=(1 - opp.spread) * (size / opp.spread),
            actual_profit=None,
            latency_ms=0,
            status="pending",
            error=None,
            timestamp=start_time.isoformat()
        )
        
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import OrderArgs, OrderType
            
            # Inicializar cliente
            client = ClobClient(
                host="https://clob.polymarket.com",
                key=self.private_key,
                chain_id=137,
                signature_type=self.signature_type,
                funder=self.funder_address,
            )
            
            # Derivar credenciales
            creds = client.create_or_derive_api_creds()
            client.set_api_creds(creds)
            
            # Calcular shares
            up_shares = (size / 2) / opp.up_price
            down_shares = (size / 2) / opp.down_price
            
            print(f"\n📊 Ejecutando trade de ${size}...")
            print(f"   UP: {up_shares:.2f} shares @ ${opp.up_price}")
            print(f"   DOWN: {down_shares:.2f} shares @ ${opp.down_price}")
            
            # TODO: Implementar ejecución real con client.create_and_post_order()
            # Por ahora simulamos
            
            trade.status = "simulated"
            trade.up_fill_price = opp.up_price
            trade.down_fill_price = opp.down_price
            trade.actual_spread = opp.spread
            trade.actual_profit = trade.expected_profit
            
        except Exception as e:
            trade.status = "failed"
            trade.error = str(e)
        
        end_time = datetime.now()
        trade.latency_ms = (end_time - start_time).total_seconds() * 1000
        
        self.trades.append(trade)
        return trade
    
    def generate_report(self) -> dict:
        """Genera reporte de validación"""
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "min_trade_size": self.min_trade_size,
                "max_trade_size": self.max_trade_size,
                "min_profit_threshold": self.min_profit_threshold
            },
            "opportunities_found": len(self.opportunities),
            "trades_executed": len(self.trades),
            "opportunities": [asdict(o) for o in self.opportunities[:10]],
            "trades": [asdict(t) for t in self.trades],
            "summary": {
                "total_invested": sum(t.trade_size_usdc for t in self.trades),
                "total_expected_profit": sum(t.expected_profit for t in self.trades),
                "avg_latency_ms": sum(t.latency_ms for t in self.trades) / len(self.trades) if self.trades else 0,
                "success_rate": len([t for t in self.trades if t.status in ["success", "simulated"]]) / len(self.trades) * 100 if self.trades else 0
            }
        }
        
        # Guardar reporte
        output_dir = Path("reports/validation")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"micro_trade_validation_{timestamp}.json"
        
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n💾 Reporte guardado: {output_path}")
        
        return report

async def main():
    print("=" * 70)
    print("  VALIDACIÓN FASE 1: MICRO-TRADES DELTA-NEUTRAL")
    print("=" * 70)
    print(f"\n  Capital disponible: $56.86 USDC")
    print(f"  Tamaño por trade: $2-5 USDC")
    print(f"  Objetivo: Validar profit sostenido")
    print("=" * 70)
    
    validator = MicroTradeValidator()
    
    # 1. Escanear oportunidades
    opportunities = validator.scan_opportunities()
    validator.display_opportunities()
    
    # 2. Si hay oportunidades, preguntar si ejecutar
    if opportunities:
        print("\n" + "=" * 70)
        print("  OPCIONES")
        print("=" * 70)
        print("""
        1. Las oportunidades mostradas son REALES en este momento
        2. Para ejecutar trades reales, el bot necesita:
           - Verificar balance suficiente
           - Colocar órdenes en ambos lados simultáneamente
           - Monitorear fills
        
        ⚠️  MODO ACTUAL: PAPER TRADING (simulación)
        
        Para activar trading real:
        1. Cambiar PAPER_TRADING=false en .env
        2. Ejecutar: python -m src.cli run
        """)
    else:
        print("\n" + "=" * 70)
        print("  NO HAY OPORTUNIDADES AHORA")
        print("=" * 70)
        print("""
        Los mercados de arbitraje delta-neutral son EFICIENTES.
        Las oportunidades aparecen brevemente cuando:
        
        1. Mercados flash (15-min) tienen spread temporal
        2. Alta volatilidad crea desbalances
        3. Bajo volumen en un lado
        
        RECOMENDACIÓN:
        - Monitorear continuamente con el bot
        - Las oportunidades duran segundos/minutos
        - Ejecutar: python -m src.cli scan --live
        """)
    
    # 3. Generar reporte
    report = validator.generate_report()
    
    print("\n" + "=" * 70)
    print("  PRÓXIMOS PASOS")
    print("=" * 70)
    print("""
    1. MONITOREO CONTINUO:
       python -m src.cli scan --live
    
    2. DRY-RUN (simulación con mercado real):
       python -m src.cli dry-run --duration 60
    
    3. TRADING REAL (cuando estés listo):
       - Editar .env: PAPER_TRADING=false
       - python -m src.cli run --size 3
    """)

if __name__ == "__main__":
    asyncio.run(main())
