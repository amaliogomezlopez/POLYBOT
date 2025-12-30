#!/usr/bin/env python3
"""Análisis detallado de spreads en mercados Up/Down"""

import httpx
import json

def analyze_spreads():
    response = httpx.get(
        'https://gamma-api.polymarket.com/markets',
        params={'limit': 200, 'active': True},
        timeout=15
    )

    markets = response.json()

    print('ANÁLISIS DE SPREADS EN MERCADOS UP/DOWN')
    print('=' * 85)

    flash_markets = []
    for m in markets:
        q = m.get('question', '').lower()
        if 'up or down' in q or 'higher or lower' in q:
            outcomes = m.get('outcomePrices', '')
            try:
                prices = json.loads(outcomes) if outcomes else []
                if len(prices) >= 2:
                    up = float(prices[0])
                    down = float(prices[1])
                    spread = up + down
                    flash_markets.append({
                        'q': m.get('question', '')[:50],
                        'up': up,
                        'down': down,
                        'spread': spread,
                        'v': float(m.get('volume24hr', 0) or 0)
                    })
            except:
                pass

    flash_markets.sort(key=lambda x: x['spread'])

    print(f'\nEncontrados {len(flash_markets)} mercados Up/Down\n')
    print(f"{'Mercado':<50} {'UP':>7} {'DOWN':>7} {'SPREAD':>8} {'DIFF':>8}")
    print('-' * 85)

    for m in flash_markets[:30]:
        diff = m['spread'] - 1.0
        diff_str = f"+{diff:.4f}" if diff >= 0 else f"{diff:.4f}"
        symbol = "🎯" if diff < 0 else "  "
        print(f"{symbol}{m['q']:<48} ${m['up']:.2f}  ${m['down']:.2f}  ${m['spread']:.4f}  {diff_str}")

    # Estadísticas
    spreads = [m['spread'] for m in flash_markets]
    if spreads:
        print(f'\n' + '=' * 85)
        print(f'ESTADÍSTICAS:')
        print(f'  Spread mínimo: ${min(spreads):.4f}')
        print(f'  Spread máximo: ${max(spreads):.4f}')
        print(f'  Spread promedio: ${sum(spreads)/len(spreads):.4f}')
        print(f'  Mercados con spread < $1.00: {len([s for s in spreads if s < 1.0])} 🎯 OPORTUNIDAD')
        print(f'  Mercados con spread = $1.00: {len([s for s in spreads if abs(s - 1.0) < 0.001])}')
        print(f'  Mercados con spread > $1.00: {len([s for s in spreads if s > 1.0])}')
        
        under_one = [m for m in flash_markets if m['spread'] < 1.0]
        if under_one:
            print(f'\n' + '=' * 85)
            print('🎯 OPORTUNIDADES DE ARBITRAJE:')
            print('-' * 85)
            for m in under_one:
                profit = (1 - m['spread']) / m['spread'] * 100
                print(f"  {m['q']}")
                print(f"    UP: ${m['up']:.2f} + DOWN: ${m['down']:.2f} = ${m['spread']:.4f}")
                print(f"    Profit potencial: {profit:.2f}%")
                print()

if __name__ == "__main__":
    analyze_spreads()
