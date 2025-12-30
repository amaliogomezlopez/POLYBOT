# System Setup & Configuration

## Prerequisites
- **Python 3.10+**
- **Pip** (or Poetry if preferred)
- **Polygon Wallet**: A private key with USDC and MATIC (for gas).
- **Polymarket Account**: API key and secret from the Polymarket CLOB dashboard.

## Installation

1.  **Clone the Repository**:
    ```bash
    git clone <repo-url>
    cd polymarket-bot
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    # OR using poetry
    poetry install
    ```

3.  **Environment Configuration**:
    Copy the example environment file and fill in your credentials:
    ```bash
    cp .env.example .env
    ```

### Environment Variables Reference

| Variable | Description | Example |
| :--- | :--- | :--- |
| `PK` | Your Polygon wallet private key | `0x123...` |
| `CLOB_API_KEY` | Polymarket CLOB API Key | `uuid-string` |
| `CLOB_SECRET` | Polymarket CLOB Secret | `long-hash` |
| `CLOB_PASSPHRASE` | Polymarket CLOB Passphrase | `secure-text` |
| `TELEGRAM_TOKEN` | Token from @BotFather | `12345:ABC...` |
| `TELEGRAM_CHAT_ID`| Your chat ID | `98765432` |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///bot.db` |

## Configuration Defaults
Common trading parameters can be found in `src/config/settings.py` or defined in `.env`:

- `MIN_PROFIT_THRESHOLD`: Minimum spread to execute (default: 0.005, i.e., 0.5%).
- `MAX_EXPOSURE`: Maximum USDC locked in open trades (default: 1000.0).
- `ORDER_AMOUNT_USDC`: Size of each arbitrage leg (default: 10.0).

## Running the Bot

### Live Mode
```bash
python -m src.cli run
```

### Paper Trading Mode (Safe)
```bash
python -m src.cli run --paper
```

### Scan Mode (Reporting only)
```bash
python -m src.cli scan
```
