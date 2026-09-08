"""Tests for current-vs-target allocation (C-3, D24).

Deterministic given a plan + scripted account state (H-2 fake). The key property is
reconciliation with the C-1 order set: target = current + the orders' signed value effect.
"""

from __future__ import annotations

from decimal import Decimal

from fakes.fake_alpaca import FakeAlpacaClient

from rebalancer.alpaca import OrderSide
from rebalancer.planning import Plan, PlannedOrder, compute_allocation


def _rows_by_symbol(report):
    return {r.symbol: r for r in report.rows}


def test_current_and_target_percentages():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_position("AAPL", qty="100", price="100")  # $10k = 100% now
    # Plan: liquidate AAPL, buy VTI $6000 + BND $4000.
    plan = Plan(
        orders=(
            PlannedOrder("AAPL", OrderSide.SELL, "liquidate", qty=Decimal("100")),
            PlannedOrder("VTI", OrderSide.BUY, "buy", notional=Decimal("6000")),
            PlannedOrder("BND", OrderSide.BUY, "buy", notional=Decimal("4000")),
        )
    )
    rows = _rows_by_symbol(compute_allocation(plan, alpaca))
    assert rows["AAPL"].current_pct == Decimal("100.00")
    assert rows["AAPL"].target_pct == Decimal("0.00")  # fully sold
    assert rows["VTI"].current_pct == Decimal("0.00") and rows["VTI"].target_pct == Decimal("60.00")
    assert rows["BND"].target_pct == Decimal("40.00")


def test_reconciles_target_equals_current_plus_delta():
    alpaca = FakeAlpacaClient(equity="8000")
    alpaca.set_position("VTI", qty="80", price="100")  # $8000
    plan = Plan(orders=(PlannedOrder("VTI", OrderSide.SELL, "trim", notional=Decimal("2000")),))
    (row,) = compute_allocation(plan, alpaca).rows
    assert row.current_value == Decimal("8000")
    assert row.delta_value == Decimal("-2000")
    assert row.target_value == row.current_value + row.delta_value == Decimal("6000")


def test_qty_orders_valued_at_holdings_price():
    alpaca = FakeAlpacaClient(equity="1500")
    alpaca.set_position("AAPL", qty="10", price="100")  # $1000
    alpaca.set_position("MSFT", qty="1", price="500")  # $500
    plan = Plan(orders=(PlannedOrder("AAPL", OrderSide.SELL, "sell half", qty=Decimal("5")),))
    rows = _rows_by_symbol(compute_allocation(plan, alpaca))
    assert rows["AAPL"].delta_value == Decimal("-500")  # 5 shares * $100
    assert rows["AAPL"].target_value == Decimal("500")


def test_qty_buy_of_unheld_symbol_fetches_price():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_price("NVDA", "200")  # not held → price must be fetched
    plan = Plan(orders=(PlannedOrder("NVDA", OrderSide.BUY, "buy 10 shares", qty=Decimal("10")),))
    (row,) = compute_allocation(plan, alpaca).rows
    assert row.current_value == Decimal("0")
    assert row.delta_value == Decimal("2000")  # 10 * $200
    assert row.target_pct == Decimal("20.00")


def test_untouched_holding_still_reported():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_position("AAPL", qty="50", price="100")  # $5000, not in the plan
    plan = Plan(orders=(PlannedOrder("BND", OrderSide.BUY, "buy", notional=Decimal("1000")),))
    rows = _rows_by_symbol(compute_allocation(plan, alpaca))
    assert rows["AAPL"].current_pct == Decimal("50.00") and rows["AAPL"].delta_value == Decimal("0")
    assert rows["AAPL"].target_pct == Decimal("50.00")  # unchanged


def test_empty_plan_reports_current_only():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_position("AAPL", qty="100", price="100")
    report = compute_allocation(Plan(), alpaca)
    (row,) = report.rows
    assert row.delta_value == Decimal("0") and row.current_pct == row.target_pct
