"""Tests for the real Alpaca paper client wrapper (A-4 impl, D36).

These are unit tests of the *translation layer*, not of alpaca-py or the network. The SDK
trading/data clients are replaced with hand-built stubs returning SDK-shaped objects (or
raising SDK exceptions), so we assert exactly three things this wrapper is responsible for:

1. **Paper-lock (D25/D44):** construction refuses a client resolved to a non-paper host.
2. **SDK → domain mapping:** SDK objects become our Pydantic models with ``Decimal`` money.
3. **Error translation:** SDK ``APIError`` / transport errors become typed ``AlpacaError``s.

Behavioural coverage of the *interface contract* lives against the fake double (H-2); the
real integration against the paper sandbox is the e2e suite (D30/D31).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from alpaca.common.enums import BaseURL
from alpaca.common.exceptions import APIError
from requests.exceptions import ConnectionError as RequestsConnectionError

from rebalancer.alpaca import (
    AlpacaRequestError,
    AlpacaUnavailableError,
    OrderRejectedError,
    OrderRequest,
    OrderSide,
    PaperAlpacaClient,
)
from rebalancer.paperlock import PAPER_TRADING_BASE_URL, PaperLockError


# --- SDK exception/object builders -------------------------------------------


def _api_error(message: str, status_code: int) -> APIError:
    """Build an APIError whose ``.status_code`` resolves to ``status_code``."""
    http_error = SimpleNamespace(response=SimpleNamespace(status_code=status_code))
    return APIError(message, http_error=http_error)


def _sdk_account(**kw):
    base = dict(cash="1000.50", buying_power="2000", equity="3000.25", currency="USD")
    base.update(kw)
    return SimpleNamespace(**base)


def _sdk_position(symbol="AAPL", qty="10", market_value="1500.00", current_price="150"):
    return SimpleNamespace(
        symbol=symbol, qty=qty, market_value=market_value, current_price=current_price
    )


def _sdk_asset(symbol="AAPL", tradable=True, fractionable=True, name="Apple Inc."):
    return SimpleNamespace(
        symbol=symbol, tradable=tradable, fractionable=fractionable, name=name
    )


def _sdk_clock(is_open=True):
    now = datetime.now(UTC)
    return SimpleNamespace(is_open=is_open, next_open=now, next_close=now)


def _sdk_trade(price="151.25"):
    return SimpleNamespace(price=price, timestamp=datetime.now(UTC))


def _sdk_order(order_id="abc-123", symbol="AAPL", side="buy", status="accepted", qty="2"):
    return SimpleNamespace(
        id=order_id,
        symbol=symbol,
        side=SimpleNamespace(value=side),
        status=SimpleNamespace(value=status),
        submitted_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        qty=qty,
        notional=None,
        filled_qty="0",
        model_dump=lambda mode="json": {"id": order_id, "status": status},
    )


# --- stub SDK clients --------------------------------------------------------


class StubTrading:
    """Minimal stand-in for alpaca-py TradingClient."""

    def __init__(self, base_url=BaseURL.TRADING_PAPER):
        self._base_url = base_url
        self.account = _sdk_account()
        self.positions = [_sdk_position()]
        self.clock = _sdk_clock()
        self.assets: dict[str, object] = {"AAPL": _sdk_asset()}
        self.submitted_requests: list[object] = []
        self.next_order = _sdk_order()
        self.raise_on: dict[str, Exception] = {}

    def _maybe_raise(self, key):
        if key in self.raise_on:
            raise self.raise_on[key]

    def get_account(self):
        self._maybe_raise("get_account")
        return self.account

    def get_all_positions(self):
        self._maybe_raise("get_all_positions")
        return self.positions

    def get_asset(self, symbol):
        self._maybe_raise("get_asset")
        if symbol not in self.assets:
            raise _api_error(f"asset not found: {symbol}", 404)
        return self.assets[symbol]

    def get_clock(self):
        self._maybe_raise("get_clock")
        return self.clock

    def submit_order(self, request):
        self.submitted_requests.append(request)
        self._maybe_raise("submit_order")
        return self.next_order

    def get_order_by_id(self, order_id):
        self._maybe_raise("get_order_by_id")
        return _sdk_order(order_id=order_id)


class StubData:
    """Minimal stand-in for alpaca-py StockHistoricalDataClient."""

    def __init__(self):
        self._base_url = BaseURL.DATA
        self.trades = {"AAPL": _sdk_trade(), "BND": _sdk_trade("72.50")}
        self.raise_on: Exception | None = None

    def get_stock_latest_trade(self, request):
        if self.raise_on is not None:
            raise self.raise_on
        return {s: self.trades[s] for s in request.symbol_or_symbols if s in self.trades}


def _client(trading=None, data=None):
    return PaperAlpacaClient(
        trading_client=trading or StubTrading(), data_client=data or StubData()
    )


def _buy(symbol="AAPL", qty="2"):
    return OrderRequest(symbol=symbol, side=OrderSide.BUY, qty=Decimal(qty))


# --- paper-lock at construction (D25/D44) ------------------------------------


def test_construction_accepts_paper_host():
    c = _client(StubTrading(base_url=BaseURL.TRADING_PAPER))
    assert c.get_account().cash == Decimal("1000.50")


def test_construction_accepts_plain_paper_url_string():
    # base_url may be a plain string rather than the BaseURL enum.
    _client(StubTrading(base_url=PAPER_TRADING_BASE_URL))


def test_construction_refuses_live_host():
    with pytest.raises(PaperLockError):
        _client(StubTrading(base_url=BaseURL.TRADING_LIVE))


def test_construction_refuses_arbitrary_host():
    with pytest.raises(PaperLockError):
        _client(StubTrading(base_url="https://evil.example.com"))


# --- SDK -> domain mapping (D45 Decimal) -------------------------------------


def test_get_account_maps_to_decimal():
    acct = _client().get_account()
    assert acct.cash == Decimal("1000.50")
    assert acct.buying_power == Decimal("2000")
    assert acct.equity == Decimal("3000.25")
    assert isinstance(acct.cash, Decimal)


def test_get_positions_maps():
    positions = _client().get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].market_value == Decimal("1500.00")
    assert isinstance(positions[0].qty, Decimal)


def test_get_asset_maps_tradability():
    trading = StubTrading()
    trading.assets["PINK"] = _sdk_asset("PINK", tradable=False, fractionable=False)
    c = _client(trading)
    assert c.get_asset("AAPL").tradable is True
    pink = c.get_asset("PINK")
    assert pink.tradable is False and pink.fractionable is False


def test_get_asset_unknown_raises_request_error():
    with pytest.raises(AlpacaRequestError):
        _client().get_asset("ZZZZ")


def test_get_latest_prices_maps():
    prices = _client().get_latest_prices(["AAPL", "BND"])
    assert prices["BND"].price == Decimal("72.50")
    assert isinstance(prices["AAPL"].price, Decimal)


def test_get_latest_prices_missing_symbol_raises():
    with pytest.raises(AlpacaRequestError):
        _client().get_latest_prices(["AAPL", "NOPE"])


def test_get_latest_prices_empty_is_noop():
    assert _client().get_latest_prices([]) == {}


def test_get_clock_maps():
    trading = StubTrading()
    trading.clock = _sdk_clock(is_open=False)
    assert _client(trading).get_clock().is_open is False


# --- order submission --------------------------------------------------------


def test_submit_order_maps_and_passes_decimal_string():
    trading = StubTrading()
    c = _client(trading)
    out = c.submit_order(_buy(qty="2.5"))
    assert out.id == "abc-123"
    assert out.symbol == "AAPL"
    assert out.side is OrderSide.BUY
    assert out.status == "accepted"
    assert out.raw == {"id": "abc-123", "status": "accepted"}
    # We hand the SDK a decimal *string* for qty, never a float we constructed (D45).
    sent = trading.submitted_requests[0]
    assert str(sent.qty) in ("2.5", "2.50")


def test_submit_order_reject_becomes_order_rejected_error():
    trading = StubTrading()
    trading.raise_on["submit_order"] = _api_error("insufficient buying power", 403)
    with pytest.raises(OrderRejectedError) as exc:
        _client(trading).submit_order(_buy())
    assert exc.value.symbol == "AAPL"
    assert exc.value.status_code == 403


def test_get_order_maps():
    out = _client().get_order("xyz-9")
    assert out.id == "xyz-9"


# --- error translation -------------------------------------------------------


def test_server_error_becomes_unavailable():
    trading = StubTrading()
    trading.raise_on["get_account"] = _api_error("upstream boom", 503)
    with pytest.raises(AlpacaUnavailableError):
        _client(trading).get_account()


def test_statusless_api_error_becomes_unavailable():
    trading = StubTrading()
    trading.raise_on["get_clock"] = APIError("no http error attached")  # status_code None
    with pytest.raises(AlpacaUnavailableError):
        _client(trading).get_clock()


def test_transport_error_becomes_unavailable():
    trading = StubTrading()
    trading.raise_on["get_all_positions"] = RequestsConnectionError("connection reset")
    with pytest.raises(AlpacaUnavailableError):
        _client(trading).get_positions()


def test_client_side_request_error_passes_through_as_request_error():
    trading = StubTrading()
    trading.raise_on["get_clock"] = _api_error("bad request", 422)
    with pytest.raises(AlpacaRequestError):
        _client(trading).get_clock()
