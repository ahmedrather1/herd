"""Real Alpaca paper client (A-4 impl, D36).

Wraps the official ``alpaca-py`` SDK behind the ``AlpacaClient`` interface. The rest of
the app depends only on ``AlpacaClient`` + the domain models, never on SDK shapes: this
module is the single translation layer between the two.

Invariants enforced here:

- **Paper-lock (D25/D44).** The trading client is always built with ``paper=True`` — the
  ``paper``/live flag is never exposed to callers — and, belt-and-suspenders, the SDK
  client's resolved base URL is run through ``paperlock.verify_paper_only`` at
  construction. If the SDK ever resolved to the live host, construction fails fast rather
  than trading live. The read-only market-data host (``data.alpaca.markets``) is a
  separate concern (D44): it cannot place orders, so it is intentionally NOT run through
  the trading-only guard (which would reject it).
- **Decimal money (D45).** Every amount that crosses back into the app is converted to
  ``Decimal`` via ``str(...)`` so we never construct a binary float ourselves. Amounts
  handed *to* the SDK are passed as decimal strings; the SDK coerces them to ``float``
  internally — that lossy step lives entirely inside the SDK, not in our types.
- **Typed errors only.** SDK ``APIError`` and transport (``requests``) exceptions are
  translated into the ``AlpacaError`` hierarchy so callers (A-5, Epic D/E) never see raw
  SDK/HTTP exceptions. 5xx / no-response → ``AlpacaUnavailableError``; 4xx →
  ``AlpacaRequestError`` (``OrderRejectedError`` for order submission).
- **Synchronous (D46).** The SDK is synchronous; this wrapper stays sync and FastAPI
  offloads calls to a threadpool at the route layer.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from typing import TypeVar

from alpaca.common.exceptions import APIError
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as SdkOrderSide
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.enums import TimeInForce as SdkTimeInForce
from alpaca.trading.requests import GetOrdersRequest, GetPortfolioHistoryRequest, MarketOrderRequest

try:  # transport layer under alpaca-py is `requests`; catch its failures as "unavailable"
    from requests.exceptions import RequestException
except ImportError:  # pragma: no cover - requests ships with alpaca-py
    class RequestException(Exception):  # type: ignore[no-redef]
        ...

from ..config import Settings, get_settings
from ..paperlock import verify_paper_only
from .client import AlpacaClient
from .errors import (
    AlpacaRequestError,
    AlpacaUnavailableError,
    OrderRejectedError,
)
from .models import (
    Account,
    Asset,
    BalancePoint,
    MarketClock,
    OrderRequest,
    OrderSide,
    Position,
    Price,
    SubmittedOrder,
)

T = TypeVar("T")


def _dec(value: object) -> Decimal | None:
    """Convert an SDK numeric (str/float/None) to ``Decimal`` without going through float.

    ``None`` passes through as ``None`` (for optional amounts like ``filled_qty``).
    """
    if value is None:
        return None
    return Decimal(str(value))


def _req_dec(value: object) -> Decimal:
    """Convert a required SDK numeric to ``Decimal``; a missing value is a real error."""
    if value is None:
        raise AlpacaRequestError("Alpaca returned a null value for a required amount")
    return Decimal(str(value))


class PaperAlpacaClient(AlpacaClient):
    """``AlpacaClient`` backed by the real alpaca-py SDK, pinned to the paper endpoint."""

    def __init__(
        self,
        *,
        trading_client: TradingClient,
        data_client: StockHistoricalDataClient,
    ) -> None:
        # Paper-lock (D25/D44): verify the trading client's resolved base URL is the pinned
        # paper host. BaseURL is a str-enum, so prefer its `.value` when present.
        base_url = getattr(trading_client, "_base_url", None)
        base_url = getattr(base_url, "value", base_url)
        verify_paper_only(str(base_url))

        self._trading = trading_client
        self._data = data_client

    @classmethod
    def from_settings(cls, settings: Settings) -> "PaperAlpacaClient":
        """Build a client from validated settings. ``paper=True`` is hard-coded (D25)."""
        trading_client = TradingClient(
            settings.alpaca_key, settings.alpaca_secret, paper=True
        )
        data_client = StockHistoricalDataClient(
            settings.alpaca_key, settings.alpaca_secret
        )
        return cls(trading_client=trading_client, data_client=data_client)

    # --- error translation ---------------------------------------------------

    @staticmethod
    def _call(fn: Callable[[], T], *, order_symbol: str | None = None) -> T:
        """Run an SDK call, translating SDK/transport errors into typed ``AlpacaError``s.

        - Transport failure or 5xx / status-less error → ``AlpacaUnavailableError`` ("we
          don't know what happened", drives A-5 / stop-on-failure D15).
        - 4xx → ``AlpacaRequestError``; for order submission (``order_symbol`` given) →
          ``OrderRejectedError`` carrying the symbol (reject-with-reason, D18).
        """
        try:
            return fn()
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            if status is None or status >= 500:
                raise AlpacaUnavailableError(str(exc)) from exc
            if order_symbol is not None:
                raise OrderRejectedError(
                    str(exc), symbol=order_symbol, status_code=status
                ) from exc
            raise AlpacaRequestError(str(exc), status_code=status) from exc
        except RequestException as exc:  # connection reset / timeout / DNS — no response
            raise AlpacaUnavailableError(str(exc)) from exc

    # --- reads ---------------------------------------------------------------

    def get_account(self) -> Account:
        a = self._call(self._trading.get_account)
        return Account(
            cash=_req_dec(a.cash),
            buying_power=_req_dec(a.buying_power),
            equity=_req_dec(a.equity),
            currency=a.currency or "USD",
        )

    def get_positions(self) -> list[Position]:
        positions = self._call(self._trading.get_all_positions)
        return [
            Position(
                symbol=p.symbol,
                qty=_req_dec(p.qty),
                market_value=_req_dec(p.market_value),
                current_price=_req_dec(p.current_price),
            )
            for p in positions
        ]

    def get_asset(self, symbol: str) -> Asset:
        a = self._call(lambda: self._trading.get_asset(symbol))
        return Asset(
            symbol=a.symbol,
            tradable=bool(a.tradable),
            fractionable=bool(a.fractionable),
            name=a.name,
        )

    def get_latest_prices(self, symbols: Sequence[str]) -> dict[str, Price]:
        symbols = list(symbols)
        if not symbols:
            return {}
        request = StockLatestTradeRequest(symbol_or_symbols=symbols)
        trades = self._call(lambda: self._data.get_stock_latest_trade(request))
        missing = [s for s in symbols if s not in trades]
        if missing:
            raise AlpacaRequestError(
                f"no latest price returned for: {', '.join(missing)}", status_code=404
            )
        return {
            s: Price(symbol=s, price=_req_dec(trades[s].price), as_of=trades[s].timestamp)
            for s in symbols
        }

    def get_clock(self) -> MarketClock:
        c = self._call(self._trading.get_clock)
        return MarketClock(
            is_open=bool(c.is_open), next_open=c.next_open, next_close=c.next_close
        )

    # --- writes --------------------------------------------------------------

    def submit_order(self, order: OrderRequest) -> SubmittedOrder:
        # Pass amounts as decimal strings so we never construct a float (D45); the SDK
        # coerces to float internally, a lossy step contained entirely within the SDK.
        request = MarketOrderRequest(
            symbol=order.symbol,
            side=_to_sdk_side(order.side),
            time_in_force=SdkTimeInForce.DAY,
            qty=str(order.qty) if order.qty is not None else None,
            notional=str(order.notional) if order.notional is not None else None,
        )
        submitted = self._call(
            lambda: self._trading.submit_order(request), order_symbol=order.symbol
        )
        return _to_submitted_order(submitted)

    def get_order(self, order_id: str) -> SubmittedOrder:
        order = self._call(lambda: self._trading.get_order_by_id(order_id))
        return _to_submitted_order(order)

    def get_open_orders(self) -> list[SubmittedOrder]:
        request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        orders = self._call(lambda: self._trading.get_orders(filter=request))
        return [_to_submitted_order(o) for o in orders]

    def cancel_order(self, order_id: str) -> None:
        self._call(lambda: self._trading.cancel_order_by_id(order_id))

    def get_balance_history(self) -> list[BalancePoint]:
        request = GetPortfolioHistoryRequest(period="1M", timeframe="1D")
        history = self._call(lambda: self._trading.get_portfolio_history(history_filter=request))
        timestamps = getattr(history, "timestamp", None) or []
        equities = getattr(history, "equity", None) or []
        points: list[BalancePoint] = []
        for ts, eq in zip(timestamps, equities):
            if eq is None:
                continue
            points.append(
                BalancePoint(as_of=datetime.fromtimestamp(int(ts), tz=UTC), equity=Decimal(str(eq)))
            )
        return points


# --- SDK <-> domain mapping helpers ------------------------------------------


def _to_sdk_side(side: OrderSide) -> SdkOrderSide:
    return SdkOrderSide.BUY if side is OrderSide.BUY else SdkOrderSide.SELL


def _enum_value(value: object) -> str:
    """Return an enum's ``.value`` (SDK enums) or the plain string."""
    return str(getattr(value, "value", value))


def _to_submitted_order(order: object) -> SubmittedOrder:
    """Map an SDK ``Order`` to the domain ``SubmittedOrder`` (keeping raw for audit, D20)."""
    raw: dict = {}
    dump = getattr(order, "model_dump", None)
    if callable(dump):
        raw = dump(mode="json")
    return SubmittedOrder(
        id=str(order.id),
        symbol=order.symbol,
        side=OrderSide(_enum_value(order.side)),
        status=_enum_value(order.status),
        submitted_at=order.submitted_at or order.created_at,
        qty=_dec(order.qty),
        notional=_dec(order.notional),
        filled_qty=_dec(order.filled_qty),
        raw=raw,
    )


@lru_cache(maxsize=1)
def get_alpaca_client() -> PaperAlpacaClient:
    """Cached process-wide paper client, built from validated settings.

    Used by future route/dependency wiring (Epics D/E). Constructing the SDK clients does
    not perform any network I/O, so this is safe to call at import/startup time.
    """
    return PaperAlpacaClient.from_settings(get_settings())
