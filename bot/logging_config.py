"""
bot/logging_config.py
─────────────────────
Production-grade logging setup with:
- Rotating main log  → trading_bot.log
- Market order log   → market_order.log
- Limit order log    → limit_order.log
- Request-ID tracking (context-var based, thread-safe)
- Sensitive data redaction
"""

from __future__ import annotations

import logging
import re
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from typing import Any

import bot as cfg


# ═══════════════════════════════════════════════════════════════════════════════
# Correlation ID
# ═══════════════════════════════════════════════════════════════════════════════

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(rid: str) -> None:
    _request_id_ctx.set(rid)


def clear_request_id() -> None:
    _request_id_ctx.set("-")


def get_request_id() -> str:
    return _request_id_ctx.get()


# ═══════════════════════════════════════════════════════════════════════════════
# Sensitive Data Filter
# ═══════════════════════════════════════════════════════════════════════════════

class _SensitiveDataFilter(logging.Filter):
    """Injects request_id and redacts API secrets from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        msg = str(record.msg)
        for key in ("signature", "api_secret", "apiSecret"):
            if key in msg:
                record.msg = re.sub(rf"('{key}':\s*')[^']+", r"\1<REDACTED>", msg)
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# Order-type specific log filters
# ═══════════════════════════════════════════════════════════════════════════════

class _MarketOrderFilter(logging.Filter):
    """Only passes log records that contain the MARKET order marker."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "ORDER_TYPE:MARKET" in str(record.getMessage())


class _LimitOrderFilter(logging.Filter):
    """Only passes log records that contain the LIMIT/TWAP order marker."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        return "ORDER_TYPE:LIMIT" in msg or "ORDER_TYPE:TWAP" in msg


# ═══════════════════════════════════════════════════════════════════════════════
# Root logger setup (runs once)
# ═══════════════════════════════════════════════════════════════════════════════

_configured: bool = False


def _make_rotating(filename: str, level: int, formatter: logging.Formatter, *filters: logging.Filter) -> RotatingFileHandler:
    h = RotatingFileHandler(
        filename=filename,
        maxBytes=cfg.LOG_MAX_BYTES,
        backupCount=cfg.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    h.setLevel(level)
    h.setFormatter(formatter)
    for f in filters:
        h.addFilter(f)
    return h


def _setup_root_logger() -> None:
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt     = logging.Formatter(fmt=cfg.LOG_FORMAT, datefmt=cfg.LOG_DATE_FORMAT)
    s_filt  = _SensitiveDataFilter()
    m_filt  = _MarketOrderFilter()
    l_filt  = _LimitOrderFilter()

    # ── trading_bot.log — everything ─────────────────────────────────────────
    root.addHandler(_make_rotating(cfg.LOG_FILE, getattr(logging, cfg.LOG_LEVEL), fmt, s_filt))

    # ── market_order.log — MARKET orders only ────────────────────────────────
    root.addHandler(_make_rotating(cfg.MARKET_ORDER_LOG, logging.INFO, fmt, s_filt, m_filt))

    # ── limit_order.log — LIMIT / TWAP orders only ───────────────────────────
    root.addHandler(_make_rotating(cfg.LIMIT_ORDER_LOG, logging.INFO, fmt, s_filt, l_filt))

    # ── Console (stderr, warnings+) ──────────────────────────────────────────
    console_h = logging.StreamHandler(sys.stderr)
    console_h.setLevel(getattr(logging, cfg.CONSOLE_LOG_LEVEL))
    console_h.setFormatter(fmt)
    console_h.addFilter(s_filt)
    root.addHandler(console_h)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger; root logger is configured on first call."""
    _setup_root_logger()
    return logging.getLogger(name)
