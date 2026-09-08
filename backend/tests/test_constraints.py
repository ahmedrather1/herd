"""Tests for constraint-solving (C-2, D8/D10).

Deterministic against the H-2 fake. Covers the default readings (D55): cash floor reduces
the investable base, exclusions set holdings aside, only-new-deposits and unsatisfiable
floors refuse (D10 — no partial orders).
"""

from __future__ import annotations

from decimal import Decimal

from fakes.fake_alpaca import FakeAlpacaClient

from rebalancer.alpaca import OrderSide
from rebalancer.parsing import Amount, AmountBasis, Constraint, Intent, Operation, SymbolMapping
from rebalancer.planning import ConstraintSolver


def _weight(target, pct):
    return Operation(
        action="set_allocation",
        target=target,
        amount=Amount(value=Decimal(str(pct)), basis=AmountBasis.TARGET_WEIGHT),
    )


def _map(target, action, *symbols):
    return SymbolMapping(target=target, action=action, symbols=tuple(symbols), source="proposed")


def _solve(alpaca, ops, maps, constraints):
    intent = Intent(operations=ops, constraints=constraints)
    return ConstraintSolver(alpaca).solve(intent, maps)


def _by_symbol(plan):
    return {o.symbol: o for o in plan.orders}


# --- exclusion ---------------------------------------------------------------


def test_exclusion_sets_holding_aside_and_rebalances_the_rest():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_position("AAPL", qty="20", price="100")  # $2000 kept aside
    result = _solve(
        alpaca,
        [_weight("stocks", 60), _weight("bonds", 40)],
        [_map("stocks", "set_allocation", "VTI"), _map("bonds", "set_allocation", "BND")],
        [Constraint(kind="exclude_asset", target="AAPL", raw_phrase="don't sell AAPL")],
    )
    assert result.ok
    orders = _by_symbol(result.plan)
    assert "AAPL" not in orders  # never sold
    # investable = 10000 - 2000 = 8000 → VTI 60% = 4800, BND 40% = 3200
    assert orders["VTI"].notional == Decimal("4800")
    assert orders["BND"].notional == Decimal("3200")
    assert "don't sell AAPL" in result.applied


def test_exclusion_skips_a_category_sell_leg():
    alpaca = FakeAlpacaClient(equity="2000")
    alpaca.set_position("AAPL", qty="10", price="100")
    alpaca.set_position("MSFT", qty="10", price="100")
    result = _solve(
        alpaca,
        [Operation(action="sell", target="tech", amount=Amount(value=Decimal("50"), basis=AmountBasis.PERCENT_SOURCE_POSITION))],
        [_map("tech", "sell", "AAPL", "MSFT")],
        [Constraint(kind="exclude_asset", target="AAPL", raw_phrase="keep AAPL")],
    )
    assert result.ok
    orders = _by_symbol(result.plan)
    assert "AAPL" not in orders and orders["MSFT"].qty == Decimal("5")


# --- cash floor --------------------------------------------------------------


def test_cash_floor_reduces_investable_base():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_position("AAPL", qty="100", price="100")  # entire $10k, liquidated
    result = _solve(
        alpaca,
        [_weight("stocks", 60), _weight("bonds", 40)],
        [_map("stocks", "set_allocation", "VTI"), _map("bonds", "set_allocation", "BND")],
        [Constraint(kind="cash_floor", value=Decimal("2000"), raw_phrase="keep $2k")],
    )
    assert result.ok
    orders = _by_symbol(result.plan)
    assert orders["AAPL"].side is OrderSide.SELL  # liquidated (not protected)
    # investable = 10000 - 2000 = 8000 → 4800 / 3200, leaving $2000 cash
    assert orders["VTI"].notional == Decimal("4800")
    assert orders["BND"].notional == Decimal("3200")
    assert "keep $2000 in cash" in result.applied


# --- refusals (D10) ----------------------------------------------------------


def test_only_new_deposits_is_refused():
    alpaca = FakeAlpacaClient(equity="10000")
    result = _solve(
        alpaca,
        [_weight("stocks", 100)],
        [_map("stocks", "set_allocation", "VTI")],
        [Constraint(kind="only_new_deposits", raw_phrase="only new deposits")],
    )
    assert result.ok is False and result.plan is None
    assert "new deposits" in result.refusal


def test_floor_over_equity_is_refused():
    alpaca = FakeAlpacaClient(equity="1000")
    result = _solve(
        alpaca,
        [_weight("stocks", 100)],
        [_map("stocks", "set_allocation", "VTI")],
        [Constraint(kind="cash_floor", value=Decimal("5000"), raw_phrase="keep $5k")],
    )
    assert result.ok is False
    assert "only worth" in result.refusal


def test_excluding_everything_leaves_nothing_to_invest():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_position("AAPL", qty="100", price="100")  # the whole portfolio
    result = _solve(
        alpaca,
        [_weight("stocks", 60), _weight("bonds", 40)],
        [_map("stocks", "set_allocation", "VTI"), _map("bonds", "set_allocation", "BND")],
        [Constraint(kind="exclude_asset", target="AAPL", raw_phrase="keep AAPL")],
    )
    assert result.ok is False
    assert "nothing left to invest" in result.refusal


# --- no constraints ----------------------------------------------------------


def test_no_constraints_behaves_like_the_planner():
    alpaca = FakeAlpacaClient(equity="10000")
    result = _solve(
        alpaca,
        [_weight("stocks", 60), _weight("bonds", 40)],
        [_map("stocks", "set_allocation", "VTI"), _map("bonds", "set_allocation", "BND")],
        [],
    )
    assert result.ok and result.applied == ()
    orders = _by_symbol(result.plan)
    assert orders["VTI"].notional == Decimal("6000") and orders["BND"].notional == Decimal("4000")
