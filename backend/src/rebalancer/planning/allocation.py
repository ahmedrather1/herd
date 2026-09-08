"""Current-vs-target allocation for the confirm screen (C-3, D24).

Given a :class:`Plan` (C-1) and live account state, compute per-symbol **current %** and the
**target %** the orders would reach, plus the dollar delta each order attempts. The target
is derived from the plan itself (current value + each order's signed value effect), so the
numbers reconcile with the concrete order set by construction (the C-3 acceptance criterion).

This is display-only (D24). Success is defined as *accepted* (D16), so the target reflects
intended post-order allocation, not a guaranteed fill. Per-**category** grouping can layer on
top later using the B-3 mappings; v1 reports the concrete, reconcilable per-symbol view.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..alpaca import OrderSide
from ..alpaca.client import AlpacaClient
from .models import Plan, PlannedOrder

_PCT = Decimal("0.01")


@dataclass(frozen=True)
class AllocationRow:
    symbol: str
    current_value: Decimal
    current_pct: Decimal  # percent of equity, 0..100
    target_value: Decimal
    target_pct: Decimal
    delta_value: Decimal  # signed: + means the orders add exposure, - means they reduce it


@dataclass(frozen=True)
class AllocationReport:
    equity: Decimal
    rows: tuple[AllocationRow, ...]


def compute_allocation(plan: Plan, alpaca: AlpacaClient) -> AllocationReport:
    """Build the current-vs-target report for ``plan`` against live state (C-3)."""
    account = alpaca.get_account()  # AlpacaUnavailable → propagates (A-5)
    positions = {p.symbol.upper(): p for p in alpaca.get_positions()}
    equity = account.equity

    prices = _prices_for(plan, positions, alpaca)
    current = {sym: pos.market_value for sym, pos in positions.items()}

    deltas: dict[str, Decimal] = {}
    for order in plan.orders:
        deltas[order.symbol] = deltas.get(order.symbol, Decimal("0")) + _order_value(order, prices)

    symbols = sorted(set(current) | set(deltas))
    rows = []
    for sym in symbols:
        cur = current.get(sym, Decimal("0"))
        delta = deltas.get(sym, Decimal("0"))
        target = cur + delta
        rows.append(
            AllocationRow(
                symbol=sym,
                current_value=cur,
                current_pct=_pct(cur, equity),
                target_value=target,
                target_pct=_pct(target, equity),
                delta_value=delta,
            )
        )
    return AllocationReport(equity=equity, rows=tuple(rows))


def _order_value(order: PlannedOrder, prices: dict[str, Decimal]) -> Decimal:
    """Signed dollar effect of an order (+ for buys, − for sells)."""
    if order.notional is not None:
        magnitude = order.notional
    else:  # qty order → value at the symbol's price
        magnitude = (order.qty or Decimal("0")) * prices.get(order.symbol, Decimal("0"))
    return magnitude if order.side is OrderSide.BUY else -magnitude


def _prices_for(plan: Plan, positions: dict, alpaca: AlpacaClient) -> dict[str, Decimal]:
    """Prices to value qty orders: from holdings when held, else fetched (read-only, D44)."""
    prices = {sym: pos.current_price for sym, pos in positions.items()}
    missing = sorted(
        {o.symbol for o in plan.orders if o.qty is not None and o.symbol not in prices}
    )
    if missing:
        for sym, price in alpaca.get_latest_prices(missing).items():
            prices[sym.upper()] = price.price
    return prices


def _pct(value: Decimal, equity: Decimal) -> Decimal:
    if equity <= 0:
        return Decimal("0.00")
    return (value / equity * Decimal("100")).quantize(_PCT)
