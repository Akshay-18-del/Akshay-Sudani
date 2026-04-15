"""
bot/cli.py
──────────
CLI entry point for the Binance Futures Testnet Trading Bot.

Usage
-----
    python -m bot.cli --help
    python -m bot.cli order --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
    python -m bot.cli order --symbol BTCUSDT --side BUY --type LIMIT  --quantity 0.01 --price 60000
    python -m bot.cli order --symbol BTCUSDT --side BUY --type TWAP   --quantity 0.05 --chunks 5 --interval 5
    python -m bot.cli balance
    python -m bot.cli orders
    python -m bot.cli orders --symbol BTCUSDT
"""

from __future__ import annotations

import io
import signal
import sys

# ── UTF-8 stdout (Windows cp1252 fix) ─────────────────────────────────────────
if hasattr(sys.stdout, "buffer") and (
    not sys.stdout.encoding or sys.stdout.encoding.lower() != "utf-8"
):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import argparse
from datetime import datetime, timezone
from typing import Optional

import bot as cfg
from bot.client import (
    BinanceFuturesClient,
    ConfigurationError,
    RateLimitError,
    InsufficientFundsError,
    BinanceAPIError,
    NetworkError,
    TradingBotError,
)
from bot.logging_config import get_logger
from bot.orders import place_market_order, place_limit_order, place_twap_order
from bot.validators import validate_order_params

log = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ANSI colours
# ═══════════════════════════════════════════════════════════════════════════════

_USE_COLOUR = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False

_RESET  = "\033[0m"  if _USE_COLOUR else ""
_BOLD   = "\033[1m"  if _USE_COLOUR else ""
_DIM    = "\033[2m"  if _USE_COLOUR else ""
_GREEN  = "\033[92m" if _USE_COLOUR else ""
_RED    = "\033[91m" if _USE_COLOUR else ""
_CYAN   = "\033[96m" if _USE_COLOUR else ""
_YELLOW = "\033[93m" if _USE_COLOUR else ""
_WHITE  = "\033[97m" if _USE_COLOUR else ""


def _c(text: str, colour: str) -> str:
    return f"{colour}{text}{_RESET}"


# ── Exit codes ─────────────────────────────────────────────────────────────────

class ExitCode:
    OK         = 0
    VALIDATION = 1
    AUTH       = 1
    BINANCE_API = 2
    NETWORK     = 3
    UNEXPECTED  = 4


# ── Display helpers ────────────────────────────────────────────────────────────

_SEP  = _c("─" * 44, _CYAN)
_SEP2 = _c("═" * 44, _CYAN)


def _header(title: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print()
    print(_SEP2)
    print(_c(f"  {title}", _BOLD))
    print(_c(f"  {ts}", _DIM))
    print(_SEP2)


def _row(label: str, value: str, colour: str = _WHITE) -> None:
    print(f"  {_c(label.ljust(16), _DIM)}: {_c(value, colour)}")


def _ok(msg: str) -> None:
    print()
    print(_c(f"  [OK]  {msg}", _GREEN))
    print()


def _fail(msg: str, hint: Optional[str] = None) -> None:
    print()
    print(_c(f"  [FAIL]  {msg}", _RED))
    if hint:
        print(_c(f"  Hint: {hint}", _YELLOW))
    print()


def _warn(msg: str) -> None:
    print(_c(f"  [WARN]  {msg}", _YELLOW))


def _print_order_summary(params: dict) -> None:
    _header("ORDER REQUEST SUMMARY")
    _row("Symbol",   params["symbol"],     _BOLD)
    _row("Side",     params["side"],       _GREEN if params["side"] == "BUY" else _RED)
    _row("Type",     params["order_type"])
    _row("Quantity", str(params["quantity"]))

    price = params.get("price")
    if price is not None:
        _row("Price", str(price))
    elif params["order_type"] != "TWAP":
        _row("Price", "Market (best available)", _YELLOW)

    if params.get("chunks"):
        _row("Chunks",   str(params["chunks"]))
    if params.get("interval"):
        _row("Interval", f"{params['interval']}s")

    print(_SEP2)
    print()


def _print_order_response(resp: dict) -> None:
    order_id   = str(resp.get("orderId",    "N/A"))
    status     = str(resp.get("status",     "N/A"))
    exec_qty   = str(resp.get("executedQty","N/A"))
    orig_qty   = str(resp.get("origQty",   "N/A"))
    avg_price  = resp.get("avgPrice")
    symbol     = str(resp.get("symbol",     "N/A"))
    side       = str(resp.get("side",       "N/A"))
    order_type = str(resp.get("type",       "N/A"))
    created_ms = resp.get("time") or resp.get("updateTime")

    status_colour = (
        _GREEN  if status in {"FILLED", "NEW", "PARTIALLY_FILLED"} else
        _RED    if status in {"REJECTED", "EXPIRED", "CANCELED"} else
        _YELLOW
    )

    _header("ORDER RESPONSE")
    _row("Order ID",     order_id,  _BOLD)
    _row("Symbol",       symbol)
    _row("Side",         side,      _GREEN if side == "BUY" else _RED)
    _row("Type",         order_type)
    _row("Status",       status,    status_colour)
    _row("Orig Qty",     orig_qty)
    _row("Executed Qty", exec_qty)

    if avg_price is not None:
        try:
            ap = float(avg_price)
            _row("Avg Price", f"{ap:,.4f}" if ap > 0 else "—", _CYAN)
        except (ValueError, TypeError):
            _row("Avg Price", str(avg_price))
    else:
        _row("Avg Price", "pending fill", _YELLOW)

    if created_ms:
        ts = datetime.fromtimestamp(int(created_ms) / 1000, tz=timezone.utc)
        _row("Timestamp", ts.strftime("%Y-%m-%d %H:%M:%S UTC"), _DIM)

    print(_SEP2)
    print()


def _print_balances(balances: list[dict]) -> None:
    _header("ACCOUNT BALANCES")
    non_zero = [
        b for b in balances
        if float(b.get("balance", 0)) > 0 or float(b.get("availableBalance", 0)) > 0
    ]
    if not non_zero:
        print(_c("  No non-zero balances found.", _YELLOW))
    else:
        print(_c(f"  {'ASSET':<10} {'BALANCE':>18} {'AVAILABLE':>18}", _DIM))
        print(_SEP)
        for b in non_zero:
            asset = b.get("asset", "?")
            bal   = float(b.get("balance", 0))
            avail = float(b.get("availableBalance", 0))
            print(
                f"  {_c(asset, _BOLD):<10} "
                f"{_c(f'{bal:>18.6f}', _WHITE)} "
                f"{_c(f'{avail:>18.6f}', _GREEN)}"
            )
    print(_SEP2)
    print()


def _print_open_orders(orders: list[dict]) -> None:
    _header("OPEN ORDERS")
    if not orders:
        print(_c("  No open orders.", _YELLOW))
    else:
        print(_c(
            f"  {'ORDER ID':<14} {'SYMBOL':<12} {'SIDE':<6} {'TYPE':<10} "
            f"{'STATUS':<20} {'ORIG QTY':>10} {'PRICE':>12}",
            _DIM,
        ))
        print(_SEP)
        for o in orders:
            side_colour = _GREEN if o.get("side") == "BUY" else _RED
            print(
                f"  {str(o.get('orderId', '?')):<14} "
                f"{str(o.get('symbol',  '?')):<12} "
                f"{_c(str(o.get('side', '?')), side_colour):<6} "
                f"{str(o.get('type',   '?')):<10} "
                f"{str(o.get('status', '?')):<20} "
                f"{str(o.get('origQty','?')):>10} "
                f"{str(o.get('price', 'market')):>12}"
            )
    print(_SEP2)
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# Argument parser
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading_bot",
        description=(
            "Binance Futures Testnet (USDT-M) Trading Bot\n"
            "Credentials are loaded from BINANCE_TESTNET_API_KEY / "
            "BINANCE_TESTNET_API_SECRET environment variables (.env)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Subcommands:\n"
            "  order    Place a MARKET, LIMIT, or TWAP order\n"
            "  balance  Show account asset balances\n"
            "  orders   List open orders\n\n"
            "Examples:\n"
            "  python -m bot.cli order --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001\n"
            "  python -m bot.cli order --symbol BTCUSDT --side BUY --type LIMIT  --quantity 0.01 --price 60000\n"
            "  python -m bot.cli order --symbol BTCUSDT --side BUY --type TWAP   --quantity 0.05 --chunks 5 --interval 5\n"
            "  python -m bot.cli balance\n"
            "  python -m bot.cli orders --symbol BTCUSDT\n"
        ),
    )
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {cfg.APP_VERSION}")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── order ──────────────────────────────────────────────────────────────────
    order_p = sub.add_parser(
        "order",
        help="Place a MARKET, LIMIT, or TWAP order.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m bot.cli order --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001\n"
            "  python -m bot.cli order --symbol BTCUSDT --side BUY --type LIMIT  --quantity 0.01 --price 60000\n"
            "  python -m bot.cli order --symbol BTCUSDT --side BUY --type TWAP   --quantity 0.05 --chunks 5 --interval 5\n"
        ),
    )
    order_p.add_argument("--symbol",   required=True,  metavar="SYMBOL",
                         help="Trading pair, e.g. BTCUSDT")
    order_p.add_argument("--side",     required=True,  choices=list(cfg.VALID_SIDES),
                         type=str.upper, metavar="SIDE", help="BUY or SELL")
    order_p.add_argument("--type",     required=True,  dest="order_type",
                         choices=list(cfg.VALID_ORDER_TYPES), type=str.upper,
                         metavar="TYPE", help="MARKET | LIMIT | TWAP")
    order_p.add_argument("--quantity", required=True,  type=float, metavar="QTY",
                         help="Total amount of base asset (must be > 0)")
    order_p.add_argument("--price",    required=False, type=float, default=None,
                         metavar="PRICE",
                         help="Limit price (required for LIMIT, optional for TWAP)")
    order_p.add_argument("--tif",      required=False, default="GTC",
                         choices=list(cfg.VALID_TIME_IN_FORCE), dest="time_in_force",
                         help="Time-in-force for LIMIT chunks: GTC (default), IOC, FOK")
    order_p.add_argument("--interval", required=False, type=int, default=None,
                         help="Seconds between TWAP chunks")
    order_p.add_argument("--chunks",   required=False, type=int, default=None,
                         help="Number of chunks to split a TWAP order into")
    order_p.add_argument("--dry-run",  action="store_true", dest="dry_run",
                         help="Validate inputs and print summary WITHOUT sending to API")

    # ── balance ────────────────────────────────────────────────────────────────
    sub.add_parser("balance", help="Show account asset balances.")

    # ── orders ─────────────────────────────────────────────────────────────────
    orders_p = sub.add_parser("orders", help="List open orders.")
    orders_p.add_argument("--symbol", default=None, metavar="SYMBOL",
                          help="Filter by symbol (e.g. BTCUSDT). Omit for all.")

    return parser


# ═══════════════════════════════════════════════════════════════════════════════
# Subcommand handlers
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_order(args: argparse.Namespace) -> None:
    # 1. Validate
    try:
        params = validate_order_params(
            symbol=args.symbol,
            side=args.side,
            order_type=args.order_type,
            quantity=args.quantity,
            price=args.price,
            interval=args.interval,
            chunks=args.chunks,
        )
    except ValueError as err:
        log.warning("Validation failed | reason=%s", err)
        _fail(str(err))
        sys.exit(ExitCode.VALIDATION)

    # 2. Summary
    _print_order_summary(params)

    # 3. Dry-run
    if args.dry_run:
        _warn("DRY-RUN: No order sent.  Remove --dry-run to place this order.")
        log.info("Dry-run complete | params=%s", params)
        sys.exit(ExitCode.OK)

    # 4. Execute
    try:
        with BinanceFuturesClient() as client:
            client.check_server_time()

            if params["order_type"] == "TWAP":
                # TWAP: execute chunks with live progress output
                def _on_chunk(i: int, total: int, resp: dict) -> None:
                    _ok(f"Chunk {i}/{total} placed. ID: {resp.get('orderId')}")

                responses = place_twap_order(
                    client=client,
                    symbol=params["symbol"],
                    side=params["side"],
                    quantity=params["quantity"],
                    chunks=params["chunks"],
                    interval=params["interval"],
                    price=params["price"],
                    time_in_force=args.time_in_force,
                    progress_callback=_on_chunk,
                )
                _ok("TWAP Execution Completed successfully!")
                _print_order_response(responses[-1])
                _ok(f"Last chunk ID: {responses[-1].get('orderId')}")

            elif params["order_type"] == "MARKET":
                response = place_market_order(
                    client=client,
                    symbol=params["symbol"],
                    side=params["side"],
                    quantity=params["quantity"],
                )
                _print_order_response(response)
                _ok(f"Order #{response.get('orderId')} placed successfully!")

            else:  # LIMIT
                response = place_limit_order(
                    client=client,
                    symbol=params["symbol"],
                    side=params["side"],
                    quantity=params["quantity"],
                    price=params["price"],
                    time_in_force=args.time_in_force,
                )
                _print_order_response(response)
                _ok(f"Order #{response.get('orderId')} placed successfully!")

    except ConfigurationError as err:
        log.error("Configuration error: %s", err)
        _fail(str(err), hint=err.hint)
        sys.exit(ExitCode.AUTH)
    except RateLimitError as err:
        log.error("Rate limit hit: %s", err)
        _fail(str(err), hint=err.hint)
        sys.exit(ExitCode.BINANCE_API)
    except InsufficientFundsError as err:
        log.error("Insufficient funds: %s", err)
        _fail(str(err), hint=err.hint)
        sys.exit(ExitCode.BINANCE_API)
    except BinanceAPIError as err:
        log.error("Binance API error | code=%s | %s", err.code, err)
        _fail(str(err), hint=err.hint)
        sys.exit(ExitCode.BINANCE_API)
    except NetworkError as err:
        log.error("Network error: %s", err)
        _fail(str(err), hint=err.hint)
        sys.exit(ExitCode.NETWORK)
    except Exception as err:
        log.exception("Unexpected error during order placement: %s", err)
        _fail(f"Unexpected error: {err}", hint="Check trading_bot.log for details.")
        sys.exit(ExitCode.UNEXPECTED)


def _handle_balance(_args: argparse.Namespace) -> None:
    try:
        with BinanceFuturesClient() as client:
            balances = client.get_account_balance()
    except ConfigurationError as err:
        _fail(str(err), hint=err.hint)
        sys.exit(ExitCode.AUTH)
    except TradingBotError as err:
        _fail(str(err), hint=err.hint)
        sys.exit(ExitCode.BINANCE_API)
    except Exception as err:
        log.exception("Unexpected error fetching balance: %s", err)
        _fail(f"Unexpected error: {err}")
        sys.exit(ExitCode.UNEXPECTED)

    _print_balances(balances)
    _ok("Balance retrieved successfully.")


def _handle_orders(args: argparse.Namespace) -> None:
    try:
        with BinanceFuturesClient() as client:
            orders = client.get_open_orders(symbol=args.symbol)
    except ConfigurationError as err:
        _fail(str(err), hint=err.hint)
        sys.exit(ExitCode.AUTH)
    except TradingBotError as err:
        _fail(str(err), hint=err.hint)
        sys.exit(ExitCode.BINANCE_API)
    except Exception as err:
        log.exception("Unexpected error fetching orders: %s", err)
        _fail(f"Unexpected error: {err}")
        sys.exit(ExitCode.UNEXPECTED)

    _print_open_orders(orders)
    _ok(f"Retrieved {len(orders)} open order(s).")


# ═══════════════════════════════════════════════════════════════════════════════
# Signal handlers + runner
# ═══════════════════════════════════════════════════════════════════════════════

_HANDLERS = {
    "order":   _handle_order,
    "balance": _handle_balance,
    "orders":  _handle_orders,
}


def _on_sigint(signum: int, frame: object) -> None:   # noqa: ARG001
    print("\n\n  Interrupted — exiting cleanly.\n", file=sys.stderr)
    log.info("Session interrupted by user (SIGINT).")
    sys.exit(0)


def _on_sigterm(signum: int, frame: object) -> None:  # noqa: ARG001
    print("\n  Received SIGTERM — shutting down.\n", file=sys.stderr)
    log.info("Session terminated (SIGTERM).")
    sys.exit(0)


def _register_signals() -> None:
    try:
        signal.signal(signal.SIGINT,  _on_sigint)
        signal.signal(signal.SIGTERM, _on_sigterm)
    except (OSError, ValueError):
        pass


def run_cli(argv: Optional[list] = None) -> None:
    """Parse CLI arguments and dispatch to the appropriate handler."""
    _register_signals()
    parser = build_parser()
    args   = parser.parse_args(argv)

    log.debug("Command=%s | args=%s", args.command, vars(args))

    handler = _HANDLERS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(ExitCode.UNEXPECTED)

    handler(args)


# ── Module entry point: `python -m bot.cli` ───────────────────────────────────
if __name__ == "__main__":
    log.debug(
        "Trading bot starting | python=%s | argv=%s",
        sys.version.split()[0],
        sys.argv[1:],
    )
    try:
        run_cli()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\n\n  Interrupted — exiting cleanly.\n", file=sys.stderr)
        sys.exit(0)
    except Exception as err:
        log.exception("Unhandled top-level exception: %s", err)
        print(
            f"\n  [FATAL] An unexpected error occurred: {err}"
            "\n  See trading_bot.log for the full traceback.\n",
            file=sys.stderr,
        )
        sys.exit(99)
    finally:
        log.debug("Trading bot exiting.")
