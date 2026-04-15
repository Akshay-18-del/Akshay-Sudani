# Binance Futures Testnet Trading Bot v3.0

A **production-quality Python 3 CLI trading bot** for Binance USDT-M Futures Testnet.  
Supports **MARKET**, **LIMIT**, and **TWAP** orders with per-type log routing, account balance checks, and open order listing — all via the Binance REST API with HMAC-SHA256 signing.

---

## Project Structure

```
trading_bot/
│
├── bot/
│   ├── __init__.py          ← Config constants, env loading, credential guard
│   ├── client.py            ← Binance REST client + full exception hierarchy
│   ├── orders.py            ← Order placement logic (MARKET, LIMIT, TWAP)
│   ├── validators.py        ← Input validation for all order parameters
│   ├── logging_config.py    ← Rotating logs, request-ID tracking, secrets masking
│   └── cli.py               ← CLI entry point (argparse, signal handlers, display)
│
├── .env                     ← Your real credentials (never commit this)
├── .env.example             ← Credential template
├── README.md
├── requirements.txt
├── trading_bot.log          ← All activity (DEBUG+)
├── market_order.log         ← MARKET orders only
└── limit_order.log          ← LIMIT and TWAP orders only
```

---

## Assumptions

- **Python 3.10+** is required (uses `match` syntax features in type hints).
- **Virtual environment** is located at `./venv/` inside the project root.
- The bot is designed exclusively for the **Binance Futures USDT-M Testnet** — not mainnet.
- TWAP orders are executed **client-side** as a series of MARKET (or LIMIT) sub-orders with time delays. There is no server-side TWAP endpoint.
- The script must **remain running** during TWAP execution. Killing it mid-run will leave partial orders open on the exchange.
- Log files are created in the **project root** directory automatically on first run.
- Credentials are loaded exclusively from `.env` — never hardcoded in source code.

---

## Setup Steps

### 1. Clone / navigate to the project
```powershell
cd "f:\python developer"
```

### 2. Create and activate the virtual environment
```powershell
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure credentials
```powershell
copy .env.example .env
```
Open `.env` and fill in your **Binance Futures Testnet** API credentials:
```
BINANCE_TESTNET_API_KEY=your_testnet_api_key_here
BINANCE_TESTNET_API_SECRET=your_testnet_api_secret_here
```
Get free testnet keys at → **https://testnet.binancefuture.com** → *API Keys* tab.

---

## How to Run

All commands use `python -m bot.cli` as the entry point.

### Show help
```powershell
python -m bot.cli --help
python -m bot.cli order --help
```

### Check version
```powershell
python -m bot.cli --version
# → trading_bot 3.0.0
```

---

### Place a MARKET order
```powershell
python -m bot.cli order --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
```

### Place a LIMIT order
```powershell
python -m bot.cli order --symbol BTCUSDT --side BUY --type LIMIT --quantity 0.01 --price 60000
```

### Place a TWAP order (5 chunks × every 10 seconds)
```powershell
python -m bot.cli order --symbol BTCUSDT --side BUY --type TWAP --quantity 0.05 --chunks 5 --interval 10
```

### Dry-run (validate without hitting the API)
```powershell
python -m bot.cli order --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001 --dry-run
python -m bot.cli order --symbol BTCUSDT --side BUY --type TWAP --quantity 0.05 --chunks 5 --interval 10 --dry-run
```

### Check account balances
```powershell
python -m bot.cli balance
```

### List open orders
```powershell
python -m bot.cli orders
python -m bot.cli orders --symbol BTCUSDT
```

---

## CLI Arguments — `order` subcommand

| Argument       | Required                  | Description                                             |
|----------------|---------------------------|---------------------------------------------------------|
| `--symbol`     | ✅ Always                 | Trading pair e.g. `BTCUSDT`, `ETHUSDT`                 |
| `--side`       | ✅ Always                 | `BUY` or `SELL`                                        |
| `--type`       | ✅ Always                 | `MARKET`, `LIMIT`, or `TWAP`                           |
| `--quantity`   | ✅ Always                 | Positive float — total base asset amount               |
| `--price`      | ✅ LIMIT / optional TWAP  | Limit price (ignored for MARKET)                       |
| `--chunks`     | ✅ TWAP only              | Number of sub-orders to split the total quantity into  |
| `--interval`   | ✅ TWAP only              | Seconds to wait between each TWAP chunk                |
| `--tif`        | ❌ Optional               | Time-in-force: `GTC` (default), `IOC`, `FOK`          |
| `--dry-run`    | ❌ Optional               | Validate + print summary, skip the API call            |

---

## Sample Output

**MARKET order:**
```
════════════════════════════════════════════
  ORDER REQUEST SUMMARY
  2026-04-15 18:06:54 UTC
════════════════════════════════════════════
  Symbol          : BTCUSDT
  Side            : BUY
  Type            : MARKET
  Quantity        : 0.001
  Price           : Market (best available)
════════════════════════════════════════════

════════════════════════════════════════════
  ORDER RESPONSE
  2026-04-15 18:06:57 UTC
════════════════════════════════════════════
  Order ID        : 13037500448
  Symbol          : BTCUSDT
  Side            : BUY
  Type            : MARKET
  Status          : NEW
  Orig Qty        : 0.0010
  Executed Qty    : 0.0000
  Avg Price       : —
  Timestamp       : 2026-04-15 18:06:56 UTC
════════════════════════════════════════════

  [OK]  Order #13037500448 placed successfully!
```

**TWAP order (3 chunks, 3s interval):**
```
  [OK]  Chunk 1/3 placed. ID: 13037504139
  [OK]  Chunk 2/3 placed. ID: 13037504463
  [OK]  Chunk 3/3 placed. ID: 13037504819
  [OK]  TWAP Execution Completed successfully!
```

---

## Environment Variables

All settings can be tuned in `.env` without touching source code:

| Variable                     | Default           | Description                              |
|------------------------------|-------------------|------------------------------------------|
| `BINANCE_TESTNET_API_KEY`    | *(required)*      | Testnet API key                          |
| `BINANCE_TESTNET_API_SECRET` | *(required)*      | Testnet API secret                       |
| `REQUEST_TIMEOUT`            | `10`              | HTTP timeout in seconds                  |
| `MAX_RETRIES`                | `3`               | Retry count for 429 / 5xx errors         |
| `RETRY_BACKOFF_FACTOR`       | `0.5`             | Exponential back-off base (seconds)      |
| `RETRY_JITTER`               | `true`            | Add random jitter between retries        |
| `RECV_WINDOW`                | `5000`            | Binance timestamp recv window (ms)       |
| `LOG_FILE`                   | `trading_bot.log` | Main log file path                       |
| `LOG_LEVEL`                  | `DEBUG`           | File log level                           |
| `CONSOLE_LOG_LEVEL`          | `WARNING`         | Console (stderr) log level               |
| `LOG_MAX_BYTES`              | `5242880` (5 MB)  | Max log size before rotation             |
| `LOG_BACKUP_COUNT`           | `5`               | Number of rotating backup files to keep  |

---

## Log Files

| File               | Contents                              |
|--------------------|---------------------------------------|
| `trading_bot.log`  | All activity — DEBUG and above        |
| `market_order.log` | MARKET order entries only             |
| `limit_order.log`  | LIMIT and TWAP order entries only     |

Every log line format:
```
YYYY-MM-DD HH:MM:SS | LEVEL    | module                       | request_id   | message
```

---

## Exception Hierarchy (inside `bot/client.py`)

```
TradingBotError
├── ConfigurationError       Missing / invalid environment config
├── ValidationError          Bad user input (field + reason + hint)
└── APIError
    ├── AuthenticationError  Missing credentials
    ├── BinanceAPIError      Binance returned an error payload
    │   ├── RateLimitError   HTTP 429 / code -1003
    │   └── InsufficientFundsError  code -2019
    └── NetworkError
        ├── TimeoutError     Request timed out
        └── ConnectionError  TCP connection failed
```

---

## Error Handling & Exit Codes

| Scenario                    | Exit Code | Shown to user                    |
|-----------------------------|-----------|----------------------------------|
| Validation failure          | `1`       | Field, reason, and hint          |
| Missing credentials         | `1`       | Which vars + setup hint          |
| Binance API error           | `2`       | Error code, message, hint        |
| Rate limit exceeded         | `2`       | Back-off hint                    |
| Insufficient funds          | `2`       | Fund top-up hint                 |
| Network / timeout           | `3`       | Connectivity hint                |
| Unexpected exception        | `4`       | Pointer to log file              |
| SIGINT / SIGTERM / Ctrl-C   | `0`       | Clean shutdown message           |

---

## Security

- ✅ API keys loaded from `.env` only — never hardcoded in source
- ✅ HMAC signatures stripped from all log output before writing
- ✅ Testnet credentials only — no real funds at risk
- ✅ Fail-fast at startup if credentials are missing or empty
