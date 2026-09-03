"""Alpaca client boundary (A-4): interface, domain models, and typed errors.

The concrete paper implementation (A-4 impl, wrapping alpaca-py) and the fake test double
(H-2) both implement ``AlpacaClient``.
"""

from __future__ import annotations

from .client import AlpacaClient
from .errors import (
    AlpacaError,
    AlpacaRequestError,
    AlpacaUnavailableError,
    OrderRejectedError,
)
from .models import (
    Account,
    Asset,
    MarketClock,
    OrderRequest,
    OrderSide,
    Position,
    Price,
    SubmittedOrder,
    TimeInForce,
)

__all__ = [
    "AlpacaClient",
    "AlpacaError",
    "AlpacaUnavailableError",
    "AlpacaRequestError",
    "OrderRejectedError",
    "Account",
    "Asset",
    "MarketClock",
    "OrderRequest",
    "OrderSide",
    "Position",
    "Price",
    "SubmittedOrder",
    "TimeInForce",
]
