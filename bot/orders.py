"""
bot/orders.py
─────────────
Order placement logic for MARKET, LIMIT, and TWAP order types.

Uses ORDER_TYPE: markers in log messages so logging_config.py can route
entries to the appropriate per-type log file.
"""

from __future__ import annotations

import time
from typing import Optional

from bot.client import BinanceFuturesClient
from bot.logging_config import get_logger

log = get_logger(__name__)


def place_market_order(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    quantity: float,
) -> dict:
    """
    Place a single MARKET order.

    Parameters
    ----------
    client   : BinanceFuturesClient
    symbol   : str  e.g. 'BTCUSDT'
    side     : str  'BUY' or 'SELL'
    quantity : float

    Returns
    -------
    dict  – Raw Binance order response.
    """
    log.info(
        "ORDER_TYPE:MARKET | Placing MARKET order | symbol=%s side=%s qty=%s",
        symbol, side, quantity,
    )
    response = client.place_order(
        symbol=symbol,
        side=side,
        order_type="MARKET",
        quantity=quantity,
    )
    log.info(
        "ORDER_TYPE:MARKET | MARKET order placed | orderId=%s status=%s",
        response.get("orderId"), response.get("status"),
    )
    return response


def place_limit_order(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    time_in_force: str = "GTC",
) -> dict:
    """
    Place a single LIMIT order.

    Parameters
    ----------
    client        : BinanceFuturesClient
    symbol        : str
    side          : str
    quantity      : float
    price         : float
    time_in_force : str  GTC | IOC | FOK

    Returns
    -------
    dict – Raw Binance order response.
    """
    log.info(
        "ORDER_TYPE:LIMIT | Placing LIMIT order | symbol=%s side=%s qty=%s price=%s tif=%s",
        symbol, side, quantity, price, time_in_force,
    )
    response = client.place_order(
        symbol=symbol,
        side=side,
        order_type="LIMIT",
        quantity=quantity,
        price=price,
        time_in_force=time_in_force,
    )
    log.info(
        "ORDER_TYPE:LIMIT | LIMIT order placed | orderId=%s status=%s",
        response.get("orderId"), response.get("status"),
    )
    return response


def place_twap_order(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    quantity: float,
    chunks: int,
    interval: int,
    price: Optional[float] = None,
    time_in_force: str = "GTC",
    progress_callback=None,
) -> list[dict]:
    """
    Execute a TWAP strategy by splitting the order into equal-sized chunks.

    Parameters
    ----------
    client            : BinanceFuturesClient
    symbol            : str
    side              : str
    quantity          : float  Total quantity to execute
    chunks            : int    Number of sub-orders
    interval          : int    Seconds to wait between chunks
    price             : float, optional  Limit price per chunk (MARKET if None)
    time_in_force     : str
    progress_callback : callable(chunk_num, total, response), optional

    Returns
    -------
    list[dict] – Responses from each chunk order.
    """
    chunk_qty   = quantity / chunks
    sub_type    = "LIMIT" if price is not None else "MARKET"
    responses: list[dict] = []

    log.info(
        "ORDER_TYPE:TWAP | Starting TWAP | symbol=%s side=%s total_qty=%s "
        "chunks=%d interval=%ds sub_type=%s",
        symbol, side, quantity, chunks, interval, sub_type,
    )

    for i in range(1, chunks + 1):
        log.info(
            "ORDER_TYPE:TWAP | Chunk %d/%d | symbol=%s qty=%s",
            i, chunks, symbol, chunk_qty,
        )

        if sub_type == "LIMIT":
            resp = client.place_order(
                symbol=symbol,
                side=side,
                order_type="LIMIT",
                quantity=chunk_qty,
                price=price,
                time_in_force=time_in_force,
            )
        else:
            resp = client.place_order(
                symbol=symbol,
                side=side,
                order_type="MARKET",
                quantity=chunk_qty,
            )

        responses.append(resp)
        log.info(
            "ORDER_TYPE:TWAP | Chunk %d/%d placed | orderId=%s status=%s",
            i, chunks, resp.get("orderId"), resp.get("status"),
        )

        if progress_callback:
            progress_callback(i, chunks, resp)

        if i < chunks:
            time.sleep(interval)

    log.info(
        "ORDER_TYPE:TWAP | TWAP completed | symbol=%s total_chunks=%d",
        symbol, chunks,
    )
    return responses
