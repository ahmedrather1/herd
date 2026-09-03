"""Typed errors for the Alpaca client boundary (A-4).

Callers (A-5, Epic D validation, Epic E execution) branch on these rather than on raw
SDK/HTTP exceptions. The real client (A-4 impl) and the fake double (H-2) both raise
only these types, so behavior is identical in tests and production.

Hierarchy::

    AlpacaError
    ├── AlpacaUnavailableError   # can't reach Alpaca (network/timeout/5xx) — A-5
    └── AlpacaRequestError       # Alpaca rejected the request (4xx) with a reason
        └── OrderRejectedError   # an order was rejected (buying power, qty rules) — D18
"""

from __future__ import annotations


class AlpacaError(RuntimeError):
    """Base class for all errors surfaced by the Alpaca client wrapper."""


class AlpacaUnavailableError(AlpacaError):
    """Alpaca could not be reached or returned a server error.

    Distinguishes "we don't know what happened, nothing was necessarily applied" from a
    definite rejection. Drives the A-5 "can't reach Alpaca, try again" state and the
    mid-execution stop-on-failure path (D15).
    """


class AlpacaRequestError(AlpacaError):
    """Alpaca reached us but rejected the request (typically HTTP 4xx).

    Args:
        message: human-readable reason from Alpaca.
        status_code: originating HTTP status, if known.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OrderRejectedError(AlpacaRequestError):
    """A submitted (or would-be-submitted) order was rejected with a specific reason.

    Used to surface reject-with-reason (D18) — e.g. insufficient buying power, invalid
    quantity/fractional rules — so the user is told exactly what to adjust.

    Args:
        message: human-readable rejection reason.
        symbol: the order's symbol, if applicable.
        status_code: originating HTTP status, if known.
    """

    def __init__(
        self, message: str, *, symbol: str | None = None, status_code: int | None = None
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.symbol = symbol
