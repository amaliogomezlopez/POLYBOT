# Production & Testing Workflow

Moving from development to production requires a multi-stage validation process.

## Stage 1: Local Paper Trading
- **Goal**: Verify bot logic without financial risk.
- **Config**: Set `.env` flag `PAPER_TRADING=true`.
- **Criteria**: 48 hours of uptime without crashes and positive theoretical P&L.

## Stage 2: Live Validation (Small Stakes)
- **Goal**: Verify real-world execution, transaction signing, and latency.
- **Config**: 
    - `PAPER_TRADING=false`
    - `ORDER_AMOUNT_USDC=1` (Smallest possible size)
    - `MIN_PROFIT_THRESHOLD=0.02` (High threshold for safety)
- **Monitoring**: Check for slippage between `detected_price` and `executed_price`.

## Stage 3: Full Production
- **Goal**: Deploy full capital as per reverse-engineered strategy.
- **Prerequisites**:
    - **Latency Check**: Bot should be running on a VPS in the same region as Polymarket CLOB servers (AWS `us-east-1` is typical for many Web3 APIs).
    - **Balance Monitor**: Use `AlertManager` to notify if balance drops below `X`.
    - **Deadman Switch**: Ensure the bot can be remotely killed via Telegram if needed.

## Maintenance Checklist
- [ ] Weekly database backup.
- [ ] Review performance reports for alpha decay.
- [ ] Update `py-clob-client` if Polymarket changes their API version.
- [ ] Monitor gas fees (MATIC) in the wallet.
