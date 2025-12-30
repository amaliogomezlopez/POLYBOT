#!/usr/bin/env python3
"""Análisis de costes en Polymarket"""

print("""
================================================================================
                    ANÁLISIS DE COSTES EN POLYMARKET
================================================================================

  BUENAS NOTICIAS: POLYMARKET NO COBRA FEES DE TRADING

Segun la documentacion oficial:
- NO hay fees de deposito
- NO hay fees de retiro  
- NO hay fees de trading (maker/taker = 0%)
- NO hay comision por transaccion

================================================================================
                    EJEMPLO: APUESTA DE 2 EUR (~$2.15 USDC)
================================================================================

ESCENARIO: Compras tokens YES a $0.50 cada uno

   Inversion: $2.15 USDC
   Tokens comprados: 4.3 tokens YES (a $0.50)
   
   SI GANAS (evento ocurre):
   - Cada token vale $1.00
   - Recibes: 4.3 x $1.00 = $4.30 USDC
   - Beneficio: $4.30 - $2.15 = $2.15 (100% ROI)
   - Fees Polymarket: $0.00
   
   SI PIERDES (evento no ocurre):
   - Cada token vale $0.00
   - Recibes: $0.00
   - Perdida: -$2.15

================================================================================
                    COSTES REALES (EXTERNOS A POLYMARKET)
================================================================================

POSIBLES COSTES AL DEPOSITAR:

1. MOONPAY/TARJETA (si compras USDC directo en Polymarket):
   - Comision: ~3-5% del monto
   - Para EUR2: ~EUR0.06-0.10 de fee
   - TIP: Depositar mas de una vez es ineficiente por fees minimos

2. COINBASE/EXCHANGE:
   - Fee de retiro a Polygon: ~$0-1 (variable)
   - Fee de conversion EUR->USDC: ~0.5-1%
   
3. GAS EN POLYGON (si usas EOA wallet - MetaMask):
   - ~$0.01-0.05 por transaccion
   - TIP: Con GNOSIS_SAFE/POLY_PROXY, Polymarket paga el gas!

================================================================================
                    RECOMENDACION PARA EUR50 DE TEST
================================================================================

ESTRATEGIA OPTIMA:

1. Depositar todo de una vez (EUR50) para minimizar fees de entrada
2. Usar el metodo mas barato para depositar:
   - Mejor: Transferir USDC desde exchange (Coinbase/Binance) a Polygon
   - OK: Comprar con tarjeta en Polymarket (fee ~3-5%)

3. Con tu cuenta Email/Magic (SIGNATURE_TYPE=1):
   - GAS GRATIS - Polymarket lo paga via Relayer
   - Trading fees: $0.00

COSTES ESTIMADOS PARA EUR50:

   Opcion A - Tarjeta directa en Polymarket:
   - Deposito: EUR50
   - Fee MoonPay: ~EUR1.50-2.50 (3-5%)
   - Recibes: ~$51-53 USDC
   
   Opcion B - Desde exchange (Coinbase):
   - Comprar EUR50 en USDC: fee ~EUR0.25-0.50
   - Enviar a Polygon: fee ~$0.50-1
   - Recibes: ~$53-54 USDC
   
================================================================================
                    PARA NUESTRA ESTRATEGIA DE ARBITRAJE
================================================================================

CON DELTA-NEUTRAL (UP + DOWN < $1.00):

   Ejemplo con $10 por trade:
   - Compras UP a $0.48: $4.80 -> 10 tokens UP
   - Compras DOWN a $0.49: $4.90 -> 10 tokens DOWN
   - Total invertido: $9.70
   - Valor garantizado: $10.00 (uno siempre gana)
   - Ganancia garantizada: $10 - $9.70 = $0.30 (3.1%)
   - Fees Polymarket: $0.00
   - Ganancia neta: $0.30

   El unico "coste" es el spread del mercado, no fees.

================================================================================
                    RESUMEN DE FEES
================================================================================

+---------------------------+------------+----------------------------------+
| Concepto                  | Fee        | Notas                            |
+---------------------------+------------+----------------------------------+
| Trading (compra/venta)    | 0%         | Gratis                           |
| Maker fee                 | 0%         | Gratis                           |
| Taker fee                 | 0%         | Gratis                           |
| Deposito USDC             | 0%         | Polymarket no cobra              |
| Retiro USDC               | 0%         | Polymarket no cobra              |
| Gas (Email/Magic wallet)  | 0%         | Polymarket paga via relayer      |
| Gas (EOA/MetaMask)        | ~$0.01-0.05| Tu pagas en POL/MATIC            |
| MoonPay (tarjeta)         | 3-5%       | Externo a Polymarket             |
| Exchange (Coinbase, etc)  | 0.5-1%     | Externo a Polymarket             |
+---------------------------+------------+----------------------------------+

================================================================================
                    CONCLUSION
================================================================================

Para tu apuesta de EUR2:
- Fees de Polymarket: $0.00
- Si depositas con tarjeta: ~EUR0.06-0.10 de fee MoonPay
- Si ya tienes USDC en Polygon: $0.00 de fee total

Para los EUR50 de test:
- Deposita todo de una vez
- Elige el metodo mas barato (exchange > tarjeta)
- El bot operara SIN FEES de trading

================================================================================
""")
