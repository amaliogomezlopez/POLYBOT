# Trading Strategy: Delta-Neutral Arbitrage

The bot implements a delta-neutral arbitrage strategy specifically tuned for Polymarket's **15-minute crypto flash markets**.

## 1. The Opportunity
Polymarket offers binary outcome markets on whether a cryptocurrency (BTC, ETH, SOL) will be "UP" or "DOWN" over a 15-minute window.
Because these markets are outcomes of a binary event, at expiration:
- The winning token is worth **$1.00**.
- The losing token is worth **$0.00**.

An arbitrage opportunity exists when the combined cost to purchase both tokens is **less than $1.00**.

## 2. Mathematical Foundation
Let:
- $P_{up}$ = Best Ask price of the UP token.
- $P_{down}$ = Best Ask price of the DOWN token.

The **Total Cost** ($C$) of a delta-neutral position is:
$$C = P_{up} + P_{down}$$

If $C < 1.0$, the guaranteed profit ($G$) is:
$$G = 1.0 - C$$

### Example
- Buy 1 UP @ $0.48$
- Buy 1 DOWN @ $0.49$
- **Total Cost**: $0.97$
- **Guaranteed Payout**: $1.00$
- **Net Profit**: $0.03$ (~3.1% ROI)

## 3. Market Selection: Flash Markets
Flash markets are ideal for this strategy because:
1.  **High Frequency**: New markets every 15 minutes.
2.  **Concentrated Liquidity**: High volume in a short timeframe.
3.  **Short Duration**: Capital is only locked for a few minutes.
4.  **Mispricing**: Rapid price movements in the underlying crypto often cause the individual tokens (UP/DOWN) to de-sync from their fair value sum.

## 4. Execution Workflow

1.  **Scan**: Filter for 15-minute duration markets.
2.  **Monitor**: Subscribe to real-time order books for both tokens in a pair.
3.  **Analyze**: Continuously calculate `AskPrice(UP) + AskPrice(DOWN)`.
4.  **Validate**: Check if spread > `min_profit_threshold` and if there is enough liquidity for the target size.
5.  **Risk Check**: Verify that adding the position doesn't exceed `max_exposure`.
6.  **Execute**: Place simultaneous market orders (or FOK orders) for both outcomes.
7.  **Manage**: Track the position until the market resolves or until a profitable exit exists (though holding to resolution is the baseline).

## 5. Potential Risks
- **Legging Risk**: Executing one side but failing to fill the other side, leaving the bot directionally exposed.
- **Slippage**: Final execution price being worse than detected price due to low liquidity or competing bots.
- **Latency**: Being slower than competitors who take the same liquidity.
- **Fees**: Transaction fees on Polygon must be accounted for (though they are negligible, CLOB fees might apply).
