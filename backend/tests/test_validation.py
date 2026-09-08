"""Tests for order validation & reject-with-reason (D-2, D18).

Deterministic against the H-2 fake. Covers each rule and, crucially, that buying power
counts sell proceeds (sells-first, D15) so a self-funding rebalance validates, while an
over-budget plan is rejected with a specific reason. No auto-adjustment (D-2 non-goal).
"""

from __future__ import annotations

from decimal import Decimal

from fakes.fake_alpaca import FakeAlpacaClient

from rebalancer.alpaca import OrderSide
from rebalancer.planning import OrderValidator, Plan, PlannedOrder


def _validate(alpaca, *orders):
    return OrderValidator(alpaca).validate(Plan(orders=tuple(orders)))


def _buy(symbol, notional=None, qty=None):
    return PlannedOrder(symbol, OrderSide.BUY, "buy", notional=notional, qty=qty)


def _sell(symbol, notional=None, qty=None):
    return PlannedOrder(symbol, OrderSide.SELL, "sell", notional=notional, qty=qty)


# --- buying power (counts sell proceeds, D15) --------------------------------


def test_self_funding_rebalance_validates():
    # Buying power is ~0, but liquidating AAPL funds the buys.
    alpaca = FakeAlpacaClient(buying_power="0")
    alpaca.set_position("AAPL", qty="100", price="100")  # $10k, sold via qty
    result = _validate(
        alpaca,
        _sell("AAPL", qty=Decimal("100")),
        _buy("VTI", notional=Decimal("6000")),
        _buy("BND", notional=Decimal("4000")),
    )
    assert result.ok, [p.reason for p in result.problems]


def test_over_budget_plan_is_rejected():
    alpaca = FakeAlpacaClient(buying_power="1000")
    result = _validate(alpaca, _buy("VTI", notional=Decimal("5000")))
    assert result.ok is False
    assert any("insufficient buying power" in p.reason for p in result.problems)


def test_buying_power_alone_covers_buys():
    alpaca = FakeAlpacaClient(buying_power="5000")
    result = _validate(alpaca, _buy("VTI", notional=Decimal("5000")))
    assert result.ok


# --- fractional / qty rules --------------------------------------------------


def test_notional_on_non_fractionable_is_rejected():
    alpaca = FakeAlpacaClient(buying_power="10000")
    alpaca.set_asset("BRKA", fractionable=False)
    result = _validate(alpaca, _buy("BRKA", notional=Decimal("5000")))
    assert result.ok is False
    assert any("fractionable" in p.reason for p in result.problems)


def test_fractional_qty_on_non_fractionable_is_rejected():
    alpaca = FakeAlpacaClient(buying_power="10000")
    alpaca.set_asset("BRKA", fractionable=False)
    alpaca.set_position("BRKA", qty="10", price="100")
    result = _validate(alpaca, _sell("BRKA", qty=Decimal("2.5")))
    assert result.ok is False
    assert any("fractional shares" in p.reason for p in result.problems)


def test_whole_share_on_non_fractionable_is_ok():
    alpaca = FakeAlpacaClient(buying_power="10000")
    alpaca.set_asset("BRKA", fractionable=False)
    alpaca.set_position("BRKA", qty="10", price="100")
    result = _validate(alpaca, _sell("BRKA", qty=Decimal("2")))
    assert result.ok


def test_oversell_is_rejected():
    alpaca = FakeAlpacaClient(buying_power="0")
    alpaca.set_position("AAPL", qty="5", price="100")
    result = _validate(alpaca, _sell("AAPL", qty=Decimal("10")))
    assert result.ok is False
    assert any("only 5 held" in p.reason for p in result.problems)


# --- minimums & tradability --------------------------------------------------


def test_below_minimum_notional_is_rejected():
    alpaca = FakeAlpacaClient(buying_power="10000")
    result = _validate(alpaca, _buy("VTI", notional=Decimal("0.50")))
    assert result.ok is False
    assert any("below the $1 minimum" in p.reason for p in result.problems)


def test_non_tradable_symbol_is_rejected():
    alpaca = FakeAlpacaClient(buying_power="10000")
    alpaca.set_asset("HALT", tradable=False)
    result = _validate(alpaca, _buy("HALT", notional=Decimal("100")))
    assert result.ok is False
    assert any("not tradable" in p.reason for p in result.problems)


def test_unknown_symbol_is_rejected():
    alpaca = FakeAlpacaClient(buying_power="10000")
    alpaca.set_unknown_asset("ZZZZ")
    result = _validate(alpaca, _buy("ZZZZ", notional=Decimal("100")))
    assert result.ok is False
    assert any("not a known Alpaca symbol" in p.reason for p in result.problems)


def test_empty_plan_is_valid():
    assert OrderValidator(FakeAlpacaClient()).validate(Plan()).ok


def test_valid_plan_has_no_problems():
    alpaca = FakeAlpacaClient(buying_power="10000")
    result = _validate(alpaca, _buy("VTI", notional=Decimal("5000")))
    assert result.ok and result.problems == ()
