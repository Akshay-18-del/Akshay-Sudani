"""
bot/client.py
─────────────
Binance USDT-M Futures Testnet REST client + exception hierarchy.

Exceptions (merged from exceptions.py)
---------------------------------------
TradingBotError
├── ConfigurationError
├── ValidationError
└── APIError
    ├── AuthenticationError
    ├── BinanceAPIError
    │   ├── RateLimitError
    │   └── InsufficientFundsError
    └── NetworkError
        ├── TimeoutError
        └── ConnectionError
"""

from __future__ import annotations

import hashlib
import hmac
import random
import time
import uuid
from typing import Any, Optional
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bot.logging_config import clear_request_id, get_logger, set_request_id
import bot as cfg

log = get_logger(__name__)

_SENSITIVE_KEYS: frozenset[str] = frozenset({"signature", "api_secret", "apiSecret"})


# ═══════════════════════════════════════════════════════════════════════════════
# Exception hierarchy
# ═══════════════════════════════════════════════════════════════════════════════

class TradingBotError(Exception):
    """Root exception for all trading bot errors."""

    def __init__(self, message: str, *, hint: Optional[str] = None) -> None:
        self.message = message
        self.hint    = hint
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class ConfigurationError(TradingBotError):
    """Raised when required configuration or environment variables are missing."""


class ValidationError(TradingBotError):
    """Raised when user-supplied order parameters fail validation."""

    def __init__(self, field: str, value: object, reason: str, *, hint: Optional[str] = None) -> None:
        self.field  = field
        self.value  = value
        self.reason = reason
        super().__init__(f"Invalid {field} ({value!r}): {reason}", hint=hint)


class APIError(TradingBotError):
    """Base for all errors that originate from communicating with Binance."""


class AuthenticationError(APIError):
    """Raised when API credentials are absent or rejected by Binance."""


class BinanceAPIError(APIError):
    """Raised when Binance returns an error payload."""

    def __init__(self, code: int, message: str, *, status: int = 0, hint: Optional[str] = None) -> None:
        self.code   = code
        self.status = status
        super().__init__(f"Binance error [{code}]: {message}", hint=hint or _code_hint(code))


class RateLimitError(BinanceAPIError):
    """Raised on HTTP 429 or Binance error code -1003."""

    def __init__(self, retry_after: Optional[int] = None) -> None:
        self.retry_after = retry_after
        hint = f"Wait {retry_after}s before retrying." if retry_after else "Back off and retry."
        super().__init__(code=-1003, message="Rate limit exceeded.", hint=hint)


class InsufficientFundsError(BinanceAPIError):
    """Raised when the account has insufficient margin (code -2019)."""

    def __init__(self) -> None:
        super().__init__(
            code=-2019,
            message="Insufficient margin balance.",
            hint="Reduce order quantity or add USDT to your testnet wallet.",
        )


class NetworkError(APIError):
    """Base for transport-level failures."""


class TimeoutError(NetworkError):  # noqa: A001
    """Raised when the HTTP request exceeds the configured timeout."""

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(
            f"Request timed out after {timeout_seconds}s.",
            hint="Check your internet connection or increase REQUEST_TIMEOUT.",
        )


class ConnectionError(NetworkError):  # noqa: A001
    """Raised when the bot cannot reach Binance."""

    def __init__(self) -> None:
        super().__init__(
            "Could not connect to Binance Futures Testnet.",
            hint="Verify your internet connection and that testnet.binancefuture.com is reachable.",
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _code_hint(code: int) -> Optional[str]:
    _HINTS: dict[int, str] = {
        -1000: "An unknown error occurred. Check trading_bot.log for details.",
        -1003: "Too many requests. Reduce request frequency.",
        -1013: "Invalid quantity or price precision for this symbol.",
        -1021: "Timestamp outside the recv window — check your system clock.",
        -1022: "Invalid signature. Verify your API secret.",
        -1100: "Illegal characters in a parameter.",
        -1102: "A mandatory parameter was sent as empty.",
        -1111: "Precision is over the allowed maximum for this symbol.",
        -1121: "Invalid trading pair symbol.",
        -2010: "New order rejected — account may be restricted.",
        -2011: "Cancel rejected — order not found or already filled.",
        -2013: "Order does not exist.",
        -2014: "API key format is invalid.",
        -2015: "Invalid API key, IP, or permissions.",
        -2019: "Insufficient margin. Add funds or reduce quantity.",
    }
    return _HINTS.get(code)


def _from_binance_payload(payload: dict, *, http_status: int = 0) -> BinanceAPIError:
    code = int(payload.get("code", 0))
    msg  = str(payload.get("msg", "Unknown error"))
    if code == -1003 or http_status == 429:
        return RateLimitError()
    if code == -2019:
        return InsufficientFundsError()
    return BinanceAPIError(code=code, message=msg, status=http_status)


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    return {k: ("<REDACTED>" if k in _SENSITIVE_KEYS else v) for k, v in params.items()}


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


# ═══════════════════════════════════════════════════════════════════════════════
# Binance REST Client
# ═══════════════════════════════════════════════════════════════════════════════

class BinanceFuturesClient:
    """Binance USDT-M Futures Testnet REST client."""

    def __init__(
        self,
        api_key: str = cfg.API_KEY,
        api_secret: str = cfg.API_SECRET,
        base_url: str = cfg.TESTNET_BASE_URL,
    ) -> None:
        cfg.assert_credentials_present()
        self._api_key    = api_key
        self._api_secret = api_secret
        self.base_url    = base_url.rstrip("/")
        self._session    = self._build_session()

    def __enter__(self) -> "BinanceFuturesClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=cfg.MAX_RETRIES,
            backoff_factor=cfg.RETRY_BACKOFF_FACTOR,
            status_forcelist=list(cfg.RETRY_STATUS_CODES),
            allowed_methods=frozenset({"GET", "POST", "DELETE"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://",  adapter)
        session.headers.update({
            "X-MBX-APIKEY": self._api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        })
        return session

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = cfg.RECV_WINDOW
        qs = urlencode(params)
        params["signature"] = hmac.new(
            self._api_secret.encode("utf-8"), qs.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return params

    def _request(self, method: str, endpoint: str, params: Optional[dict[str, Any]] = None, signed: bool = True) -> Any:
        if params is None:
            params = {}
        if signed:
            params = self._sign(params)
        rid = _short_id()
        set_request_id(rid)
        url = f"{self.base_url}{endpoint}"
        log.debug("→ %s %s | params=%s", method, endpoint, _safe_params(params))
        try:
            response = self._dispatch(method, url, params)
        finally:
            clear_request_id()
        return self._handle_response(response)

    def _dispatch(self, method: str, url: str, params: dict[str, Any]) -> requests.Response:
        if cfg.RETRY_JITTER:
            time.sleep(random.uniform(0, 0.1))
        try:
            if method.upper() in {"GET", "DELETE"}:
                return self._session.request(method, url, params=params, timeout=cfg.REQUEST_TIMEOUT)
            return self._session.request(method, url, data=params, timeout=cfg.REQUEST_TIMEOUT)
        except requests.exceptions.Timeout:
            raise TimeoutError(cfg.REQUEST_TIMEOUT)
        except requests.exceptions.ConnectionError:
            raise ConnectionError()
        except requests.exceptions.RequestException as err:
            raise NetworkError(f"Network error: {err}")

    @staticmethod
    def _handle_response(response: requests.Response) -> Any:
        try:
            data = response.json()
        except ValueError:
            if not response.ok:
                raise BinanceAPIError(code=response.status_code, message=response.text[:300])
            return {}
        if isinstance(data, dict) and data.get("code", 0) < 0:
            raise _from_binance_payload(data, http_status=response.status_code)
        if not response.ok:
            raise BinanceAPIError(code=response.status_code, message=response.text[:300])
        return data

    # ── Public API ─────────────────────────────────────────────────────────────

    def check_server_time(self) -> int:
        data = self._request("GET", "/fapi/v1/time", signed=False)
        return data.get("serverTime", 0)

    def get_account_balance(self) -> list[dict]:
        return self._request("GET", "/fapi/v2/balance")

    def get_open_orders(self, symbol: Optional[str] = None) -> list[dict]:
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", "/fapi/v1/openOrders", params=params)

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        time_in_force: str = "GTC",
    ) -> dict:
        params: dict[str, Any] = {
            "symbol":   symbol,
            "side":     side,
            "type":     order_type,
            "quantity": quantity,
        }
        if order_type == "LIMIT":
            if price is not None:
                params["price"] = price
            params["timeInForce"] = time_in_force
        return self._request("POST", "/fapi/v1/order", params=params)
