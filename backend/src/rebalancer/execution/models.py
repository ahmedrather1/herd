"""Execution outcome types (E-1/E-2, D15/D16)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"  # every order accepted (D16)
    PARTIAL = "partial"  # stopped on the first failure; earlier orders accepted (D15)
    REVALIDATE = "revalidate"  # confirm-time state changed → re-show the proposal (D-4/D19)
    MARKET_CLOSED = "market_closed"  # can't submit while closed (D17)
    UNAVAILABLE = "unavailable"  # couldn't reach Alpaca (A-5)
    NOTHING = "nothing"  # empty plan — nothing to do


@dataclass(frozen=True)
class SubmittedResult:
    """One order's submission outcome. ``status`` is 'accepted' / 'rejected' / 'failed'."""

    symbol: str
    side: str
    status: str
    order_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ExecutionReport:
    """Result of a confirm+execute (E-2): completed N of M, what failed, cash left."""

    status: ExecutionStatus
    message: str
    submitted: tuple[SubmittedResult, ...] = ()
    completed: int = 0
    total: int = 0
    failure: str | None = None
    cash_remaining: Decimal | None = None
    revalidation_problems: tuple[str, ...] = field(default_factory=tuple)
