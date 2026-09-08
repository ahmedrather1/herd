"""Planner output types (C-1, D53).

A ``Plan`` is an ordered list of ``PlannedOrder`` (sells-first, buys-second — D15). Each
carries a human-readable ``reason`` for the confirm screen (D4). A ``PlannedOrder`` mirrors
the Alpaca ``OrderRequest`` (exactly one of qty/notional) and converts to one for validation
(D-2) and execution (E-1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..alpaca import OrderRequest, OrderSide


@dataclass(frozen=True)
class PlannedOrder:
    """One intended order. Exactly one of ``qty`` / ``notional`` is set (D53)."""

    symbol: str
    side: OrderSide
    reason: str
    qty: Decimal | None = None
    notional: Decimal | None = None

    def to_order_request(self) -> OrderRequest:
        """Convert to the A-4 ``OrderRequest`` (validates exactly-one-amount on construction)."""
        return OrderRequest(
            symbol=self.symbol, side=self.side, qty=self.qty, notional=self.notional
        )


@dataclass(frozen=True)
class Plan:
    """The ordered order set produced from an intent (C-1)."""

    orders: tuple[PlannedOrder, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)
