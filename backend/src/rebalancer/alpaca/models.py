"""Domain types at the Alpaca client boundary (A-4).

These are the app's own types — the A-4 impl maps alpaca-py SDK objects into these, so
the rest of the app never depends on SDK shapes. They are Pydantic models (consistent
with the FastAPI/SQLModel stack) so they validate on construction and serialize cleanly
into the audit trail (F-1).

Money and quantities are ``Decimal``, never ``float`` (D45): binary floats can't
represent decimal cash/share amounts exactly, and this is a real-money-eventually system.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TimeInForce(str, Enum):
    # v1 places market orders good-for-day only; broaden deliberately if ever needed.
    DAY = "day"


class Account(BaseModel):
    """Account snapshot used for buying-power checks and current-vs-target (C-3, D-2)."""

    model_config = ConfigDict(frozen=True)

    cash: Decimal
    buying_power: Decimal
    equity: Decimal
    currency: str = "USD"


class Position(BaseModel):
    """A single open position."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: Decimal
    market_value: Decimal
    current_price: Decimal


class Price(BaseModel):
    """Latest price for a symbol (read-only market data — see D44)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    price: Decimal
    as_of: datetime | None = None


class MarketClock(BaseModel):
    """Market open/closed state for market-closed handling (D17, D-3)."""

    model_config = ConfigDict(frozen=True)

    is_open: bool
    next_open: datetime | None = None
    next_close: datetime | None = None


class Asset(BaseModel):
    """Tradability metadata for a symbol (B-3 validation, D-2 fractional rules)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    tradable: bool
    fractionable: bool
    name: str | None = None


class OrderRequest(BaseModel):
    """A single order to submit. Exactly one of ``qty`` or ``notional`` must be set.

    v1 is market orders only (type is implicit). ``qty`` is share count (may be
    fractional if the asset is fractionable); ``notional`` is a dollar amount.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: OrderSide
    qty: Decimal | None = None
    notional: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.DAY

    @model_validator(mode="after")
    def _exactly_one_amount(self) -> "OrderRequest":
        if (self.qty is None) == (self.notional is None):
            raise ValueError("OrderRequest requires exactly one of qty or notional")
        amount = self.qty if self.qty is not None else self.notional
        if amount is not None and amount <= 0:
            raise ValueError("OrderRequest amount (qty/notional) must be positive")
        return self


class SubmittedOrder(BaseModel):
    """The result of submitting an order (or a fetched order's status).

    ``status`` is Alpaca's raw status string (e.g. "accepted", "new", "filled").
    Success is defined at *accepted* granularity (D16); interpretation lives in E-2.
    ``raw`` preserves the full Alpaca response for the audit trail (D20/F-1).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    symbol: str
    side: OrderSide
    status: str
    submitted_at: datetime
    qty: Decimal | None = None
    notional: Decimal | None = None
    filled_qty: Decimal | None = None
    raw: dict = Field(default_factory=dict)
