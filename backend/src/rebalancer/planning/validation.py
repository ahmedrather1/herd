"""Order validation & reject-with-reason (D-2, D18).

Validates a :class:`Plan` against Alpaca's rules *before* it is shown or executed, so the
proposal contains no invalid orders (D18). Nothing is auto-adjusted (D-2 non-goal): an
invalid plan is rejected with specific, human-readable reasons and the user adjusts the
request. Checks:

- **Tradable** — the symbol is tradable (defense-in-depth over B-3).
- **Fractional / qty rules** — notional orders require a fractionable asset; a fractional
  ``qty`` on a non-fractionable asset is rejected; a sell ``qty`` may not exceed the held
  position (no shorting in v1).
- **Minimum size** — notional ≥ $1 (Alpaca's fractional minimum); qty > 0.
- **Buying power** — total buy cost must fit within ``buying_power`` **plus expected sell
  proceeds**, because execution is sells-first (D15) so sells free cash before buys run.

SIMPLIFICATION (flagged for review): sell proceeds are treated as immediately available and
margin/settlement (cash-account T+1) is not modeled — the H-2 fake doesn't simulate
settlement either. On the real paper sandbox, unsettled proceeds could still be rejected by
Alpaca at execution; that surfaces via the typed reject path (E), not here.

Alpaca-unavailable propagates (A-5).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..alpaca import AlpacaRequestError, OrderSide
from ..alpaca.client import AlpacaClient
from .models import Plan, PlannedOrder

MIN_NOTIONAL = Decimal("1")


@dataclass(frozen=True)
class OrderProblem:
    """One reason a plan is invalid. ``order`` is None for plan-level problems (buying power)."""

    reason: str
    order: PlannedOrder | None = None


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    problems: tuple[OrderProblem, ...] = ()


class OrderValidator:
    """Validates a plan against Alpaca rules (D-2)."""

    def __init__(self, alpaca: AlpacaClient) -> None:
        self._alpaca = alpaca

    def validate(self, plan: Plan) -> ValidationResult:
        if not plan.orders:
            return ValidationResult(ok=True)

        account = self._alpaca.get_account()  # AlpacaUnavailable → propagates (A-5)
        positions = {p.symbol.upper(): p for p in self._alpaca.get_positions()}
        prices = self._prices_for(plan, positions)

        problems: list[OrderProblem] = []
        buy_cost = Decimal("0")
        sell_proceeds = Decimal("0")

        for order in plan.orders:
            asset = self._get_asset(order.symbol)
            problems.extend(_check_order(order, asset, positions, prices))
            value = _order_value(order, prices)
            if order.side is OrderSide.BUY:
                buy_cost += value
            else:
                sell_proceeds += value

        available = account.buying_power + sell_proceeds
        if buy_cost > available:
            problems.append(
                OrderProblem(
                    reason=(
                        f"insufficient buying power: buys total ${buy_cost}, but only "
                        f"${available} is available (${account.buying_power} buying power "
                        f"+ ${sell_proceeds} from sells)"
                    )
                )
            )

        return ValidationResult(ok=not problems, problems=tuple(problems))

    # --- helpers -------------------------------------------------------------

    def _get_asset(self, symbol: str):
        try:
            return self._alpaca.get_asset(symbol)
        except AlpacaRequestError:
            return None  # unknown symbol → _check_order reports it

    def _prices_for(self, plan: Plan, positions: dict) -> dict[str, Decimal]:
        prices = {sym: pos.current_price for sym, pos in positions.items()}
        missing = sorted({o.symbol for o in plan.orders if o.qty is not None and o.symbol not in prices})
        if missing:
            for sym, price in self._alpaca.get_latest_prices(missing).items():
                prices[sym.upper()] = price.price
        return prices


def _check_order(order, asset, positions, prices) -> list[OrderProblem]:
    problems: list[OrderProblem] = []
    if asset is None:
        return [OrderProblem(f"{order.symbol} is not a known Alpaca symbol", order)]
    if not asset.tradable:
        problems.append(OrderProblem(f"{order.symbol} is not tradable", order))

    if order.notional is not None:
        if order.notional < MIN_NOTIONAL:
            problems.append(OrderProblem(f"{order.symbol}: order ${order.notional} is below the $1 minimum", order))
        if not asset.fractionable:
            problems.append(
                OrderProblem(f"{order.symbol}: dollar (notional) orders aren't allowed — it isn't fractionable", order)
            )
    elif order.qty is not None:
        if order.qty <= 0:
            problems.append(OrderProblem(f"{order.symbol}: quantity must be positive", order))
        if not asset.fractionable and order.qty != order.qty.to_integral_value():
            problems.append(OrderProblem(f"{order.symbol}: fractional shares aren't allowed — it isn't fractionable", order))
        if order.side is OrderSide.SELL:
            held = positions.get(order.symbol.upper())
            held_qty = held.qty if held else Decimal("0")
            if order.qty > held_qty:
                problems.append(
                    OrderProblem(f"{order.symbol}: can't sell {order.qty} shares — only {held_qty} held", order)
                )
    return problems


def _order_value(order: PlannedOrder, prices: dict[str, Decimal]) -> Decimal:
    if order.notional is not None:
        return order.notional
    return (order.qty or Decimal("0")) * prices.get(order.symbol, Decimal("0"))
