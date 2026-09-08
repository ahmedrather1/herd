"""Intent → concrete order set (C-1, D53).

Turns a resolved intent (B-1/B-2) + B-3 symbol mappings + **live** account state into an
ordered list of buy/sell orders. Sizing rules (D53):

- Dollar-denominated buys and target adjustments → **notional**; position-relative sells,
  whole-position sells, and share counts → **qty** taken exactly from holdings.
- ``set_allocation`` target weights summing to ~100% are a **whole-portfolio rebalance**:
  unmentioned holdings are liquidated and targets adjusted to ``weight%×equity``. A partial
  set adjusts only that category.
- Orders are **sells-first, buys-second** (D15). Amounts round **down** (never oversell /
  overspend); sub-cent deltas are skipped.

This module does **not** validate (buying power / fractional / minimums are D-2) or apply
constraints (C-2). It reads ``get_account`` + ``get_positions`` from A-4 — notional avoids
needing a price fetch. Alpaca-unavailable propagates (A-5).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_DOWN, Decimal

from ..alpaca import OrderSide, Position
from ..alpaca.client import AlpacaClient
from ..parsing import AmountBasis, Intent, Operation, SymbolMapping
from .models import Plan, PlannedOrder

_CENT = Decimal("0.01")
_QTY_STEP = Decimal("0.000001")
_HUNDRED = Decimal("100")
_WEIGHT_TOLERANCE = Decimal("0.5")  # treat weights summing to 99.5–100.5 as a full rebalance


def _money(x: Decimal) -> Decimal:
    return x.quantize(_CENT, rounding=ROUND_DOWN)


def _qty(x: Decimal) -> Decimal:
    return x.quantize(_QTY_STEP, rounding=ROUND_DOWN)


class Planner:
    """Builds a :class:`Plan` from a resolved intent and its symbol mappings (C-1)."""

    def __init__(self, alpaca: AlpacaClient) -> None:
        self._alpaca = alpaca

    def plan(self, intent: Intent, mappings: Sequence[SymbolMapping]) -> Plan:
        account = self._alpaca.get_account()  # AlpacaUnavailable → propagates (A-5)
        positions = {p.symbol.upper(): p for p in self._alpaca.get_positions()}
        equity = account.equity
        by_key = {(m.target.strip().lower(), m.action): m for m in mappings}

        sells: list[PlannedOrder] = []
        buys: list[PlannedOrder] = []
        notes: list[str] = []
        handled: set[int] = set()

        rebalance_ops = [
            op
            for op in intent.operations
            if op.action == "set_allocation"
            and op.amount is not None
            and op.amount.basis is AmountBasis.TARGET_WEIGHT
            and op.amount.value is not None
        ]
        weight_sum = sum((op.amount.value for op in rebalance_ops), Decimal("0"))
        if rebalance_ops and abs(weight_sum - _HUNDRED) <= _WEIGHT_TOLERANCE:
            self._plan_full_rebalance(rebalance_ops, by_key, positions, equity, sells, buys, notes)
            handled = {id(op) for op in rebalance_ops}

        for op in intent.operations:
            if id(op) in handled:
                continue
            mapping = by_key.get((op.target.strip().lower(), op.action))
            symbols = list(mapping.symbols) if mapping else []
            if not symbols:
                notes.append(f"no symbols mapped for {op.target!r}; skipped")
                continue
            for order in self._plan_operation(op, symbols, positions, equity):
                (sells if order.side is OrderSide.SELL else buys).append(order)

        return Plan(orders=tuple(sells) + tuple(buys), notes=tuple(notes))  # sells-first (D15)

    # --- whole-portfolio rebalance -------------------------------------------

    def _plan_full_rebalance(self, rebalance_ops, by_key, positions, equity, sells, buys, notes):
        targets: dict[str, Decimal] = {}
        for op in rebalance_ops:
            mapping = by_key.get((op.target.strip().lower(), op.action))
            symbols = list(mapping.symbols) if mapping else []
            if not symbols:
                notes.append(f"no symbols mapped for {op.target!r}; skipped")
                continue
            per_symbol = (op.amount.value / _HUNDRED) * equity / len(symbols)
            for sym in symbols:
                targets[sym.upper()] = targets.get(sym.upper(), Decimal("0")) + per_symbol

        notes.append("Whole-portfolio rebalance: holdings outside the target set are sold.")

        # Liquidate everything not in the target set.
        for sym, pos in positions.items():
            if sym not in targets and pos.qty > 0:
                sells.append(
                    PlannedOrder(sym, OrderSide.SELL, f"liquidate {sym} (not in target allocation)", qty=_qty(pos.qty))
                )

        # Adjust each target symbol toward its target value.
        for sym, target_value in targets.items():
            current = positions[sym].market_value if sym in positions else Decimal("0")
            delta = target_value - current
            if delta > 0:
                amount = _money(delta)
                if amount > 0:
                    buys.append(PlannedOrder(sym, OrderSide.BUY, f"buy {sym} toward target", notional=amount))
            elif delta < 0:
                amount = _money(-delta)
                if amount > 0:
                    sells.append(PlannedOrder(sym, OrderSide.SELL, f"trim {sym} toward target", notional=amount))

    # --- individual operations -----------------------------------------------

    def _plan_operation(
        self, op: Operation, symbols: list[str], positions: dict[str, Position], equity: Decimal
    ) -> list[PlannedOrder]:
        amount = op.amount
        if amount is None:
            return self._plan_whole_position(op, symbols, positions)

        basis = amount.basis
        value = amount.value
        if value is None:
            return []

        if basis is AmountBasis.PERCENT_SOURCE_POSITION:
            return self._plan_source_percent(op, symbols, positions, value)
        if basis in (AmountBasis.TARGET_WEIGHT, AmountBasis.PERCENT_PORTFOLIO):
            return self._plan_target(op, symbols, positions, equity, value)
        if basis is AmountBasis.ABSOLUTE_CASH:
            return self._plan_absolute_cash(op, symbols, positions, value)
        if basis is AmountBasis.SHARES:
            return self._plan_shares(op, symbols, value)
        return []

    def _plan_whole_position(self, op, symbols, positions) -> list[PlannedOrder]:
        # "sell everything" / "sell all my tech" — only sells make sense with no amount.
        if op.action != "sell":
            return []
        out = []
        for sym in symbols:
            pos = positions.get(sym.upper())
            if pos and pos.qty > 0:
                out.append(PlannedOrder(sym.upper(), OrderSide.SELL, f"sell entire {sym} position", qty=_qty(pos.qty)))
        return out

    def _plan_source_percent(self, op, symbols, positions, value) -> list[PlannedOrder]:
        frac = value / _HUNDRED
        out = []
        for sym in symbols:
            pos = positions.get(sym.upper())
            if not pos or pos.qty <= 0:
                continue
            if op.action == "sell":
                shares = _qty(pos.qty * frac)
                if shares > 0:
                    out.append(PlannedOrder(sym.upper(), OrderSide.SELL, f"sell {value}% of {sym} position", qty=shares))
            else:  # add to the position by a % of its current value
                amount = _money(pos.market_value * frac)
                if amount > 0:
                    out.append(PlannedOrder(sym.upper(), OrderSide.BUY, f"add {value}% to {sym} position", notional=amount))
        return out

    def _plan_target(self, op, symbols, positions, equity, value) -> list[PlannedOrder]:
        per = (value / _HUNDRED) * equity / len(symbols)
        out = []
        for sym in symbols:
            current = positions[sym.upper()].market_value if sym.upper() in positions else Decimal("0")
            delta = per - current
            if delta > 0:
                amount = _money(delta)
                if amount > 0:
                    out.append(PlannedOrder(sym.upper(), OrderSide.BUY, f"buy to reach {value}% target in {sym}", notional=amount))
            elif delta < 0:
                amount = _money(-delta)
                if amount > 0:
                    out.append(PlannedOrder(sym.upper(), OrderSide.SELL, f"trim {sym} to {value}% target", notional=amount))
        return out

    def _plan_absolute_cash(self, op, symbols, positions, value) -> list[PlannedOrder]:
        out = []
        if op.action == "sell":
            total = sum((positions[s.upper()].market_value for s in symbols if s.upper() in positions), Decimal("0"))
            if total <= 0:
                return []
            for sym in symbols:
                pos = positions.get(sym.upper())
                if not pos:
                    continue
                share = _money(value * (pos.market_value / total))
                if share > 0:
                    out.append(PlannedOrder(sym.upper(), OrderSide.SELL, f"sell ${share} of {sym}", notional=share))
        else:
            per = _money(value / len(symbols))
            for sym in symbols:
                if per > 0:
                    out.append(PlannedOrder(sym.upper(), OrderSide.BUY, f"buy ${per} of {sym}", notional=per))
        return out

    def _plan_shares(self, op, symbols, value) -> list[PlannedOrder]:
        side = OrderSide.SELL if op.action == "sell" else OrderSide.BUY
        shares = _qty(value)
        if shares <= 0:
            return []
        return [
            PlannedOrder(sym.upper(), side, f"{op.action} {shares} shares of {sym}", qty=shares)
            for sym in symbols
        ]
