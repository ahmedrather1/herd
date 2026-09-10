"""Tests for the C-1 planner (D53).

Deterministic given intent + mappings + scripted account state, so these use the H-2 fake
Alpaca directly (no LLM). They cover each (action, basis) sizing rule, the whole-portfolio
rebalance (liquidate the rest), sells-first ordering (D15), qty-vs-notional choice, the
on-target no-op, and Alpaca-unavailable propagation (A-5).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fakes.fake_alpaca import FakeAlpacaClient

from rebalancer.alpaca import AlpacaUnavailableError, OrderSide
from rebalancer.parsing import Amount, AmountBasis, Intent, Operation, SymbolMapping
from rebalancer.planning import Planner


def _amt(value, basis):
    return Amount(value=Decimal(str(value)), basis=basis)


def _op(action, target, value=None, basis=None):
    amount = _amt(value, basis) if value is not None else None
    return Operation(action=action, target=target, amount=amount)


def _map(target, action, *symbols):
    return SymbolMapping(target=target, action=action, symbols=tuple(symbols), source="proposed")


def _plan(alpaca, ops, maps):
    return Planner(alpaca).plan(Intent(operations=ops), maps)


def _by_symbol(plan):
    return {o.symbol: o for o in plan.orders}


# --- whole-portfolio rebalance (D53 / Q2) ------------------------------------


def test_full_rebalance_liquidates_and_buys_targets():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_position("AAPL", qty="100", price="100")  # entire $10k portfolio
    plan = _plan(
        alpaca,
        [
            _op("set_allocation", "stocks", 60, AmountBasis.TARGET_WEIGHT),
            _op("set_allocation", "bonds", 40, AmountBasis.TARGET_WEIGHT),
        ],
        [_map("stocks", "set_allocation", "VTI"), _map("bonds", "set_allocation", "BND")],
    )
    # Sells-first (D15): AAPL is liquidated before the buys.
    assert plan.orders[0].symbol == "AAPL" and plan.orders[0].side is OrderSide.SELL
    orders = _by_symbol(plan)
    assert orders["AAPL"].qty == Decimal("100") and orders["AAPL"].notional is None
    assert orders["VTI"].side is OrderSide.BUY and orders["VTI"].notional == Decimal("6000")
    assert orders["BND"].notional == Decimal("4000")
    assert all(o.side is OrderSide.BUY for o in plan.orders[1:])  # buys after the sell


def test_rebalance_fills_the_remaining_bucket():
    # "50% VOO, 20% AAPL, the rest in gold" — gold has no explicit weight → gets the leftover 30%.
    alpaca = FakeAlpacaClient(equity="100000")
    plan = _plan(
        alpaca,
        [
            _op("set_allocation", "stocks", 50, AmountBasis.TARGET_WEIGHT),
            _op("set_allocation", "tech", 20, AmountBasis.TARGET_WEIGHT),
            Operation(action="set_allocation", target="gold"),  # no amount → the remainder
        ],
        [
            _map("stocks", "set_allocation", "VOO"),
            _map("tech", "set_allocation", "AAPL"),
            _map("gold", "set_allocation", "GLD"),
        ],
    )
    orders = _by_symbol(plan)
    assert orders["VOO"].notional == Decimal("50000")
    assert orders["AAPL"].notional == Decimal("20000")
    assert orders["GLD"].notional == Decimal("30000")  # the remaining 30% — no longer dropped


def test_rebalance_leaves_cash_bucket_uninvested():
    # "90% stocks, 10% cash" — cash is reserved (source="cash"), never bought.
    alpaca = FakeAlpacaClient(equity="10000")
    plan = _plan(
        alpaca,
        [
            _op("set_allocation", "stocks", 90, AmountBasis.TARGET_WEIGHT),
            _op("set_allocation", "cash", 10, AmountBasis.TARGET_WEIGHT),
        ],
        [
            _map("stocks", "set_allocation", "VTI"),
            SymbolMapping(target="cash", action="set_allocation", symbols=(), source="cash"),
        ],
    )
    orders = _by_symbol(plan)
    assert orders["VTI"].notional == Decimal("9000")  # 90% bought
    assert all(o.symbol.upper() != "CASH" for o in plan.orders)  # cash never bought


def test_full_rebalance_already_on_target_is_noop():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_position("VTI", qty="60", price="100")  # $6000 = 60%
    alpaca.set_position("BND", qty="40", price="100")  # $4000 = 40%
    plan = _plan(
        alpaca,
        [
            _op("set_allocation", "stocks", 60, AmountBasis.TARGET_WEIGHT),
            _op("set_allocation", "bonds", 40, AmountBasis.TARGET_WEIGHT),
        ],
        [_map("stocks", "set_allocation", "VTI"), _map("bonds", "set_allocation", "BND")],
    )
    assert plan.orders == ()


def test_full_rebalance_trims_overweight_target():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_position("VTI", qty="80", price="100")  # $8000, target 60% = $6000 → trim $2000
    plan = _plan(
        alpaca,
        [
            _op("set_allocation", "stocks", 60, AmountBasis.TARGET_WEIGHT),
            _op("set_allocation", "bonds", 40, AmountBasis.TARGET_WEIGHT),
        ],
        [_map("stocks", "set_allocation", "VTI"), _map("bonds", "set_allocation", "BND")],
    )
    orders = _by_symbol(plan)
    assert orders["VTI"].side is OrderSide.SELL and orders["VTI"].notional == Decimal("2000")
    assert orders["BND"].side is OrderSide.BUY and orders["BND"].notional == Decimal("4000")
    assert plan.orders[0].side is OrderSide.SELL  # trim (sell) before buy


# --- individual operations ---------------------------------------------------


def test_sell_half_position_uses_qty_per_symbol():
    alpaca = FakeAlpacaClient(equity="2000")
    alpaca.set_position("AAPL", qty="10", price="100")
    alpaca.set_position("MSFT", qty="5", price="200")
    plan = _plan(
        alpaca,
        [_op("sell", "tech", 50, AmountBasis.PERCENT_SOURCE_POSITION)],
        [_map("tech", "sell", "AAPL", "MSFT")],
    )
    orders = _by_symbol(plan)
    assert orders["AAPL"].qty == Decimal("5") and orders["AAPL"].notional is None
    assert orders["MSFT"].qty == Decimal("2.5")  # fractional, exact from holdings
    assert all(o.side is OrderSide.SELL for o in plan.orders)


def test_percent_portfolio_buys_to_target_without_liquidating_others():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_position("AAPL", qty="50", price="100")  # unrelated holding, must be untouched
    plan = _plan(
        alpaca,
        [_op("buy", "bonds", 10, AmountBasis.PERCENT_PORTFOLIO)],
        [_map("bonds", "buy", "BND")],
    )
    orders = _by_symbol(plan)
    assert "AAPL" not in orders  # not a full rebalance → no liquidation
    assert orders["BND"].side is OrderSide.BUY and orders["BND"].notional == Decimal("1000")


def test_absolute_cash_buy_uses_notional():
    alpaca = FakeAlpacaClient(equity="10000")
    plan = _plan(
        alpaca,
        [_op("buy", "VTI", 5000, AmountBasis.ABSOLUTE_CASH)],
        [_map("VTI", "buy", "VTI")],
    )
    (order,) = plan.orders
    assert order.side is OrderSide.BUY and order.notional == Decimal("5000") and order.qty is None


def test_absolute_cash_sell_splits_proportional_to_holdings():
    alpaca = FakeAlpacaClient(equity="3000")
    alpaca.set_position("AAPL", qty="20", price="100")  # $2000
    alpaca.set_position("MSFT", qty="10", price="100")  # $1000
    plan = _plan(
        alpaca,
        [_op("sell", "tech", 3000, AmountBasis.ABSOLUTE_CASH)],
        [_map("tech", "sell", "AAPL", "MSFT")],
    )
    orders = _by_symbol(plan)
    # Proportional split, each rounded DOWN (never oversell) → a harmless penny of dust.
    assert orders["AAPL"].notional == Decimal("2000")  # 2/3 of $3000
    assert orders["MSFT"].notional == Decimal("999.99")  # 1/3, rounded down
    total = orders["AAPL"].notional + orders["MSFT"].notional
    assert total <= Decimal("3000")


def test_shares_basis_uses_qty():
    alpaca = FakeAlpacaClient(equity="10000")
    plan = _plan(
        alpaca,
        [_op("buy", "AAPL", 10, AmountBasis.SHARES)],
        [_map("AAPL", "buy", "AAPL")],
    )
    (order,) = plan.orders
    assert order.qty == Decimal("10") and order.notional is None


def test_sell_everything_liquidates_mapped_holdings():
    alpaca = FakeAlpacaClient(equity="3000")
    alpaca.set_position("AAPL", qty="10", price="100")
    alpaca.set_position("MSFT", qty="10", price="200")
    plan = _plan(
        alpaca,
        [_op("sell", "everything")],  # no amount
        [_map("everything", "sell", "AAPL", "MSFT")],
    )
    orders = _by_symbol(plan)
    assert orders["AAPL"].qty == Decimal("10") and orders["MSFT"].qty == Decimal("10")
    assert all(o.side is OrderSide.SELL for o in plan.orders)


# --- edges -------------------------------------------------------------------


def test_unmapped_target_is_skipped_with_note():
    alpaca = FakeAlpacaClient(equity="10000")
    plan = _plan(alpaca, [_op("buy", "mystery", 10, AmountBasis.PERCENT_PORTFOLIO)], [])
    assert plan.orders == ()
    assert any("mystery" in n for n in plan.notes)


def test_planned_order_converts_to_order_request():
    alpaca = FakeAlpacaClient(equity="10000")
    plan = _plan(
        alpaca, [_op("buy", "VTI", 5000, AmountBasis.ABSOLUTE_CASH)], [_map("VTI", "buy", "VTI")]
    )
    req = plan.orders[0].to_order_request()
    assert req.symbol == "VTI" and req.side is OrderSide.BUY and req.notional == Decimal("5000")


def test_alpaca_unavailable_propagates():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_unavailable(True)
    with pytest.raises(AlpacaUnavailableError):
        _plan(alpaca, [_op("buy", "VTI", 100, AmountBasis.ABSOLUTE_CASH)], [_map("VTI", "buy", "VTI")])
