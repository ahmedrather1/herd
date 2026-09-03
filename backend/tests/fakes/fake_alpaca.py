"""Hand-written fake Alpaca client double (H-2, D37).

A deterministic, in-memory implementation of the A-4 ``AlpacaClient`` interface for
unit/integration tests. No HTTP, no live calls, no extra dependency (D37). It is
scriptable along every axis integration tests need:

- **State:** account (cash/buying-power/equity), positions, latest prices, market
  open/closed, per-symbol asset tradability.
- **Order outcomes:** a FIFO queue of accept / reject / fail results, so a test can make
  the *N*th order in a sequence reject (D18) or fail mid-sequence to exercise
  stop-on-failure / land-in-cash (D15).
- **Alpaca-down:** a global switch making every call raise ``AlpacaUnavailableError`` to
  exercise A-5.

The fake deliberately does **not** simulate settlement (accepting an order does not mutate
cash/positions): execution ordering and the land-in-cash *report* are the app's logic
(E-1) and are asserted there against a scripted fake, not baked into the double.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from rebalancer.alpaca import (
    Account,
    AlpacaRequestError,
    AlpacaUnavailableError,
    Asset,
    MarketClock,
    OrderRejectedError,
    OrderRequest,
    Position,
    Price,
    SubmittedOrder,
)
from rebalancer.alpaca.client import AlpacaClient

# --- scripted order outcomes -------------------------------------------------


@dataclass(frozen=True)
class Reject:
    """Next submit_order raises OrderRejectedError (reject-with-reason, D18)."""

    reason: str
    symbol: str | None = None
    status_code: int | None = 403


@dataclass(frozen=True)
class Fail:
    """Next submit_order raises AlpacaUnavailableError (mid-sequence failure, D15/A-5)."""

    reason: str = "Alpaca unavailable"


ACCEPT = "accept"  # sentinel: next submit_order is accepted


class FakeAlpacaClient(AlpacaClient):
    def __init__(
        self,
        *,
        cash: Decimal | str | int = 0,
        buying_power: Decimal | str | int = 0,
        equity: Decimal | str | int = 0,
        positions: list[Position] | None = None,
        prices: dict[str, Decimal | str | int] | None = None,
        is_open: bool = True,
    ) -> None:
        self._account = Account(
            cash=Decimal(str(cash)),
            buying_power=Decimal(str(buying_power)),
            equity=Decimal(str(equity)),
        )
        self._positions: list[Position] = list(positions or [])
        self._prices: dict[str, Decimal] = {
            s: Decimal(str(p)) for s, p in (prices or {}).items()
        }
        self._is_open = is_open
        self._assets: dict[str, Asset] = {}
        self._unknown_assets: set[str] = set()

        self._outcomes: deque = deque()
        self._unavailable = False

        # Observability for assertions:
        self.attempts: list[OrderRequest] = []          # every submit_order arg
        self.submitted: list[SubmittedOrder] = []        # only the accepted ones
        self._orders_by_id: dict[str, SubmittedOrder] = {}
        self._next_id = 1

    # --- scripting API -------------------------------------------------------

    def set_account(self, *, cash=None, buying_power=None, equity=None) -> None:
        self._account = Account(
            cash=Decimal(str(cash)) if cash is not None else self._account.cash,
            buying_power=Decimal(str(buying_power)) if buying_power is not None else self._account.buying_power,
            equity=Decimal(str(equity)) if equity is not None else self._account.equity,
        )

    def set_position(self, symbol: str, qty, price) -> None:
        qty_d, price_d = Decimal(str(qty)), Decimal(str(price))
        pos = Position(symbol=symbol, qty=qty_d, market_value=qty_d * price_d, current_price=price_d)
        self._positions = [p for p in self._positions if p.symbol != symbol] + [pos]
        self._prices.setdefault(symbol, price_d)

    def set_price(self, symbol: str, price) -> None:
        self._prices[symbol] = Decimal(str(price))

    def set_market_open(self, is_open: bool) -> None:
        self._is_open = is_open

    def set_asset(self, symbol: str, *, tradable: bool = True, fractionable: bool = True) -> None:
        self._assets[symbol] = Asset(symbol=symbol, tradable=tradable, fractionable=fractionable)
        self._unknown_assets.discard(symbol)

    def set_unknown_asset(self, symbol: str) -> None:
        """Mark a symbol as unknown to Alpaca so get_asset rejects it (B-3 unmappable)."""
        self._unknown_assets.add(symbol)

    def set_unavailable(self, flag: bool = True) -> None:
        """Simulate Alpaca being unreachable for all calls (A-5)."""
        self._unavailable = flag

    def queue_outcomes(self, *outcomes) -> None:
        """Enqueue submit_order outcomes (ACCEPT / Reject(...) / Fail(...)) FIFO."""
        self._outcomes.extend(outcomes)

    def fail_after(self, n: int, reason: str = "Alpaca unavailable") -> None:
        """Accept the next ``n`` orders, then fail — for stop-on-failure (D15)."""
        self.queue_outcomes(*([ACCEPT] * n), Fail(reason))

    # --- AlpacaClient interface ---------------------------------------------

    def _guard_available(self) -> None:
        if self._unavailable:
            raise AlpacaUnavailableError("Alpaca is unreachable (simulated)")

    def get_account(self) -> Account:
        self._guard_available()
        return self._account

    def get_positions(self) -> list[Position]:
        self._guard_available()
        return list(self._positions)

    def get_asset(self, symbol: str) -> Asset:
        self._guard_available()
        if symbol in self._unknown_assets:
            raise AlpacaRequestError(f"asset not found: {symbol}", status_code=404)
        return self._assets.get(symbol, Asset(symbol=symbol, tradable=True, fractionable=True))

    def get_latest_prices(self, symbols) -> dict[str, Price]:
        self._guard_available()
        missing = [s for s in symbols if s not in self._prices]
        if missing:
            raise AlpacaRequestError(f"no price scripted for: {', '.join(missing)}")
        return {s: Price(symbol=s, price=self._prices[s]) for s in symbols}

    def get_clock(self) -> MarketClock:
        self._guard_available()
        return MarketClock(is_open=self._is_open)

    def submit_order(self, order: OrderRequest) -> SubmittedOrder:
        self._guard_available()
        self.attempts.append(order)
        outcome = self._outcomes.popleft() if self._outcomes else ACCEPT

        if isinstance(outcome, Reject):
            raise OrderRejectedError(
                outcome.reason, symbol=outcome.symbol or order.symbol, status_code=outcome.status_code
            )
        if isinstance(outcome, Fail):
            raise AlpacaUnavailableError(outcome.reason)

        order_id = f"fake-{self._next_id}"
        self._next_id += 1
        submitted = SubmittedOrder(
            id=order_id,
            symbol=order.symbol,
            side=order.side,
            status="accepted",
            submitted_at=datetime.now(UTC),
            qty=order.qty,
            notional=order.notional,
        )
        self.submitted.append(submitted)
        self._orders_by_id[order_id] = submitted
        return submitted

    def get_order(self, order_id: str) -> SubmittedOrder:
        self._guard_available()
        if order_id not in self._orders_by_id:
            raise AlpacaRequestError(f"order not found: {order_id}", status_code=404)
        return self._orders_by_id[order_id]
