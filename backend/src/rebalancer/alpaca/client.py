"""The Alpaca client interface (A-4 — interface step).

This is the contract the rest of the app codes against. Two implementations satisfy it:
the real paper client (A-4 impl, wrapping alpaca-py) and the hand-written fake double
(H-2). Publishing the interface first unblocks H-2 and B-3 without waiting on the impl.

Boundary conventions:
- **Synchronous** (D46). The alpaca-py SDK is synchronous; the wrapper stays sync and
  FastAPI offloads calls to a threadpool. Keeps the fake double and tests simple.
- **Paper-locked** (A-2/D25/D44). Implementations MUST route trading calls through the
  pinned paper endpoint via ``rebalancer.paperlock``; there is no base-URL parameter here
  precisely so no caller can point the client at a live endpoint.
- **Typed errors only.** Every method raises ``AlpacaUnavailableError`` when Alpaca can't
  be reached and ``AlpacaRequestError`` / ``OrderRejectedError`` on rejection — never raw
  SDK/HTTP exceptions (see ``errors``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from .models import Account, Asset, MarketClock, OrderRequest, Position, Price, SubmittedOrder


class AlpacaClient(ABC):
    """Thin paper-only client over the Alpaca calls the app needs (A-4)."""

    # --- reads ---------------------------------------------------------------

    @abstractmethod
    def get_account(self) -> Account:
        """Return account cash / buying power / equity.

        Raises:
            AlpacaUnavailableError: if Alpaca can't be reached.
        """

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Return all currently open positions.

        Raises:
            AlpacaUnavailableError: if Alpaca can't be reached.
        """

    @abstractmethod
    def get_asset(self, symbol: str) -> Asset:
        """Return tradability metadata for ``symbol`` (B-3 validation, D-2 rules).

        Raises:
            AlpacaRequestError: if the symbol is unknown to Alpaca.
            AlpacaUnavailableError: if Alpaca can't be reached.
        """

    @abstractmethod
    def get_latest_prices(self, symbols: Sequence[str]) -> dict[str, Price]:
        """Return latest prices keyed by symbol (read-only market data, D44).

        Raises:
            AlpacaUnavailableError: if Alpaca can't be reached.
        """

    @abstractmethod
    def get_clock(self) -> MarketClock:
        """Return market open/closed state and next open/close (D17, D-3).

        Raises:
            AlpacaUnavailableError: if Alpaca can't be reached.
        """

    # --- writes --------------------------------------------------------------

    @abstractmethod
    def submit_order(self, order: OrderRequest) -> SubmittedOrder:
        """Submit a single order; used sequentially by execution (E-1).

        Success is reported at *accepted* granularity (D16).

        Raises:
            OrderRejectedError: if Alpaca rejects the order (reason attached, D18).
            AlpacaUnavailableError: if Alpaca can't be reached (execution stops, D15).
        """

    @abstractmethod
    def get_order(self, order_id: str) -> SubmittedOrder:
        """Fetch the current state of a previously submitted order.

        Raises:
            AlpacaRequestError: if the order id is unknown.
            AlpacaUnavailableError: if Alpaca can't be reached.
        """
