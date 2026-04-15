"""
bot/__init__.py
───────────────
Central configuration and constants for the trading bot.
Loads .env from the project root and exposes all settings.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ── Load .env from project root ───────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Binance Futures Testnet
# ═══════════════════════════════════════════════════════════════════════════════

TESTNET_BASE_URL: str = "https://testnet.binancefuture.com"
API_KEY: str          = os.environ.get("BINANCE_TESTNET_API_KEY", "")
API_SECRET: str       = os.environ.get("BINANCE_TESTNET_API_SECRET", "")


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP / Retry
# ═══════════════════════════════════════════════════════════════════════════════

REQUEST_TIMEOUT: int       = int(os.environ.get("REQUEST_TIMEOUT", "10"))
MAX_RETRIES: int           = int(os.environ.get("MAX_RETRIES", "3"))
RETRY_BACKOFF_FACTOR: float = float(os.environ.get("RETRY_BACKOFF_FACTOR", "0.5"))
RETRY_JITTER: bool         = os.environ.get("RETRY_JITTER", "true").lower() == "true"
RETRY_STATUS_CODES: tuple[int, ...] = (429, 500, 502, 503, 504)
RECV_WINDOW: int           = int(os.environ.get("RECV_WINDOW", "5000"))


# ═══════════════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════════════

LOG_FILE: str          = os.environ.get("LOG_FILE", "trading_bot.log")
LOG_LEVEL: str         = os.environ.get("LOG_LEVEL", "DEBUG").upper()
CONSOLE_LOG_LEVEL: str = os.environ.get("CONSOLE_LOG_LEVEL", "WARNING").upper()
LOG_FORMAT: str        = (
    "%(asctime)s | %(levelname)-8s | %(name)-28s | %(request_id)-12s | %(message)s"
)
LOG_DATE_FORMAT: str   = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES: int     = int(os.environ.get("LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT: int  = int(os.environ.get("LOG_BACKUP_COUNT", "5"))

MARKET_ORDER_LOG: str  = "market_order.log"
LIMIT_ORDER_LOG: str   = "limit_order.log"


# ═══════════════════════════════════════════════════════════════════════════════
# Order constants
# ═══════════════════════════════════════════════════════════════════════════════

VALID_SIDES: tuple[str, ...]        = ("BUY", "SELL")
VALID_ORDER_TYPES: tuple[str, ...]  = ("MARKET", "LIMIT", "TWAP")
VALID_TIME_IN_FORCE: tuple[str, ...] = ("GTC", "IOC", "FOK")
DEFAULT_TIME_IN_FORCE: str          = "GTC"

SYMBOL_MIN_LEN: int = 2
SYMBOL_MAX_LEN: int = 20


# ═══════════════════════════════════════════════════════════════════════════════
# App metadata
# ═══════════════════════════════════════════════════════════════════════════════

APP_NAME: str    = "binance-futures-bot"
APP_VERSION: str = "3.0.0"


# ═══════════════════════════════════════════════════════════════════════════════
# Credential guard
# ═══════════════════════════════════════════════════════════════════════════════

def assert_credentials_present() -> None:
    """Raise ConfigurationError if API credentials are missing."""
    from bot.client import ConfigurationError  # local import avoids circularity
    missing: list[str] = []
    if not API_KEY:
        missing.append("BINANCE_TESTNET_API_KEY")
    if not API_SECRET:
        missing.append("BINANCE_TESTNET_API_SECRET")
    if missing:
        raise ConfigurationError(
            f"Missing required environment variable(s): {', '.join(missing)}",
            hint=(
                f"Copy .env.example to .env in {_PROJECT_ROOT} "
                "and fill in your Testnet credentials."
            ),
        )
