"""
bot/validators.py
─────────────────
Input validation helpers for all order parameters.
All validators raise ValueError with clear, user-friendly messages.
"""

from __future__ import annotations

import re
from typing import Optional

from bot import (
    VALID_SIDES,
    VALID_ORDER_TYPES,
    SYMBOL_MIN_LEN,
    SYMBOL_MAX_LEN,
)


# ── Symbol ─────────────────────────────────────────────────────────────────────

def validate_symbol(symbol: str) -> str:
    """Validate and normalise a futures trading symbol."""
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Symbol must be a non-empty string.")

    symbol = symbol.strip().upper()

    if not re.fullmatch(r"[A-Z]+", symbol):
        raise ValueError(
            f"Invalid symbol '{symbol}'. Symbols must contain only letters "
            f"(e.g. BTCUSDT, ETHUSDT)."
        )

    if not (SYMBOL_MIN_LEN <= len(symbol) <= SYMBOL_MAX_LEN):
        raise ValueError(
            f"Invalid symbol '{symbol}'. Length must be between "
            f"{SYMBOL_MIN_LEN} and {SYMBOL_MAX_LEN} characters."
        )

    return symbol


# ── Side ───────────────────────────────────────────────────────────────────────

def validate_side(side: str) -> str:
    """Validate the order side (BUY or SELL)."""
    if not side or not isinstance(side, str):
        raise ValueError("Side must be a non-empty string.")

    side = side.strip().upper()

    if side not in VALID_SIDES:
        raise ValueError(
            f"Invalid side '{side}'. Choose from: {', '.join(VALID_SIDES)}."
        )

    return side


# ── Order type ─────────────────────────────────────────────────────────────────

def validate_order_type(order_type: str) -> str:
    """Validate the order type (MARKET, LIMIT, TWAP)."""
    if not order_type or not isinstance(order_type, str):
        raise ValueError("Order type must be a non-empty string.")

    order_type = order_type.strip().upper()

    if order_type not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Invalid order type '{order_type}'. "
            f"Choose from: {', '.join(VALID_ORDER_TYPES)}."
        )

    return order_type


# ── Quantity ───────────────────────────────────────────────────────────────────

def validate_quantity(quantity: float) -> float:
    """Validate the order quantity (must be > 0)."""
    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid quantity '{quantity}'. Must be a positive number.")

    if quantity <= 0:
        raise ValueError(f"Quantity must be greater than 0. Got: {quantity}.")

    return quantity


# ── Price ──────────────────────────────────────────────────────────────────────

def validate_price(price: Optional[float], order_type: str) -> Optional[float]:
    """
    Validate the order price.
    - MARKET orders: price is ignored (returns None).
    - TWAP orders:   price is optional (market execution if omitted).
    - LIMIT orders:  price is required.
    """
    order_type = order_type.upper()

    if order_type == "MARKET":
        return None

    if order_type == "TWAP":
        if price is None:
            return None

    if price is None:
        raise ValueError(
            f"--price is required for {order_type} orders. "
            "Example: --price 30000.50"
        )

    try:
        price = float(price)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid price '{price}'. Must be a positive number.")

    if price <= 0:
        raise ValueError(f"Price must be greater than 0. Got: {price}.")

    return price


# ── TWAP params ────────────────────────────────────────────────────────────────

def validate_twap_params(
    interval: Optional[int], chunks: Optional[int], order_type: str
) -> tuple[Optional[int], Optional[int]]:
    """Validate TWAP execution parameters."""
    if order_type.upper() != "TWAP":
        return None, None

    if interval is None or chunks is None:
        raise ValueError(
            "--interval and --chunks are required for TWAP orders. "
            "Example: --chunks 5 --interval 10"
        )

    try:
        interval = int(interval)
        chunks   = int(chunks)
    except (TypeError, ValueError):
        raise ValueError("Interval and chunks must be positive integers.")

    if interval <= 0 or chunks <= 0:
        raise ValueError("Interval and chunks must be greater than 0.")

    return interval, chunks


# ── Convenience wrapper ────────────────────────────────────────────────────────

def validate_order_params(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None,
    interval: Optional[int] = None,
    chunks: Optional[int] = None,
) -> dict:
    """
    Run all order-parameter validators and return a clean parameter dict.

    Returns
    -------
    dict with keys: symbol, side, order_type, quantity, price, interval, chunks.
    """
    symbol     = validate_symbol(symbol)
    side       = validate_side(side)
    order_type = validate_order_type(order_type)
    quantity   = validate_quantity(quantity)
    price      = validate_price(price, order_type)
    interval, chunks = validate_twap_params(interval, chunks, order_type)

    return {
        "symbol":     symbol,
        "side":       side,
        "order_type": order_type,
        "quantity":   quantity,
        "price":      price,
        "interval":   interval,
        "chunks":     chunks,
    }
