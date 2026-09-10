"""Tests for the Alpaca client interface (A-4 — interface step).

Verifies the contract is coherent and implementable before the real impl (A-4 impl) or
the full fake double (H-2) exist: the ABC can't be instantiated bare, a minimal stub can
implement every method, the domain models validate, and the error hierarchy branches as
callers expect.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from rebalancer.alpaca import (
    Account,
    AlpacaClient,
    AlpacaError,
    AlpacaRequestError,
    AlpacaUnavailableError,
    Asset,
    MarketClock,
    OrderRejectedError,
    OrderRequest,
    OrderSide,
    Position,
    Price,
    SubmittedOrder,
)


def test_cannot_instantiate_abstract_client():
    with pytest.raises(TypeError):
        AlpacaClient()  # type: ignore[abstract]


class _StubClient(AlpacaClient):
    """Minimal implementation proving every abstract method is satisfiable."""

    def get_account(self):
        return Account(cash=Decimal("100"), buying_power=Decimal("200"), equity=Decimal("300"))

    def get_positions(self):
        return [Position(symbol="AAPL", qty=Decimal("1"), market_value=Decimal("10"), current_price=Decimal("10"))]

    def get_asset(self, symbol):
        return Asset(symbol=symbol, tradable=True, fractionable=True)

    def get_latest_prices(self, symbols):
        return {s: Price(symbol=s, price=Decimal("1.23")) for s in symbols}

    def get_clock(self):
        return MarketClock(is_open=True)

    def submit_order(self, order):
        return SubmittedOrder(
            id="o1", symbol=order.symbol, side=order.side, status="accepted",
            submitted_at=datetime(2026, 9, 2), qty=order.qty, notional=order.notional,
        )

    def get_order(self, order_id):
        return SubmittedOrder(
            id=order_id, symbol="AAPL", side=OrderSide.BUY, status="filled",
            submitted_at=datetime(2026, 9, 2),
        )

    def get_open_orders(self):
        return []

    def cancel_order(self, order_id):
        return None

    def get_balance_history(self):
        return []


def test_stub_implements_full_interface():
    c = _StubClient()
    assert c.get_account().buying_power == Decimal("200")
    assert c.get_positions()[0].symbol == "AAPL"
    assert c.get_asset("MSFT").tradable is True
    assert c.get_latest_prices(["A", "B"]).keys() == {"A", "B"}
    assert c.get_clock().is_open is True
    order = OrderRequest(symbol="AAPL", side=OrderSide.BUY, qty=Decimal("2"))
    assert c.submit_order(order).status == "accepted"
    assert c.get_order("o1").status == "filled"
    assert c.get_open_orders() == [] and c.cancel_order("o1") is None
    assert c.get_balance_history() == []


def test_order_request_requires_exactly_one_amount():
    with pytest.raises(ValueError):
        OrderRequest(symbol="AAPL", side=OrderSide.BUY)  # neither
    with pytest.raises(ValueError):
        OrderRequest(symbol="AAPL", side=OrderSide.BUY, qty=Decimal("1"), notional=Decimal("1"))  # both


def test_order_request_amount_must_be_positive():
    with pytest.raises(ValueError):
        OrderRequest(symbol="AAPL", side=OrderSide.SELL, qty=Decimal("0"))
    with pytest.raises(ValueError):
        OrderRequest(symbol="AAPL", side=OrderSide.SELL, notional=Decimal("-5"))


def test_money_fields_are_decimal_not_float():
    # Pydantic coerces to Decimal; the stored type must be Decimal, not float.
    acct = Account(cash=10.10, buying_power=0, equity=0)  # type: ignore[arg-type]
    assert isinstance(acct.cash, Decimal)


def test_models_are_frozen():
    price = Price(symbol="AAPL", price=Decimal("1"))
    with pytest.raises(Exception):
        price.price = Decimal("2")  # type: ignore[misc]


def test_error_hierarchy():
    assert issubclass(AlpacaUnavailableError, AlpacaError)
    assert issubclass(AlpacaRequestError, AlpacaError)
    assert issubclass(OrderRejectedError, AlpacaRequestError)
    # Callers can catch the base to mean "any Alpaca problem".
    with pytest.raises(AlpacaError):
        raise OrderRejectedError("insufficient buying power", symbol="AAPL", status_code=403)


def test_order_rejected_carries_reason_and_symbol():
    err = OrderRejectedError("insufficient buying power", symbol="AAPL", status_code=403)
    assert err.symbol == "AAPL"
    assert err.status_code == 403
    assert "buying power" in str(err)
