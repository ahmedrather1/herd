"""Proposal outcome types (D-1).

The proposal pipeline returns a discriminated :class:`ProposalOutcome`: a ready-to-confirm
``Proposal``, or a non-proposal outcome (clarify / refuse / unavailable / error) so nothing
ambiguous or invalid ever reaches the confirm step (D4/D10/D18).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..parsing import SymbolMapping
from ..planning import AllocationReport, PlannedOrder


class ProposalStatus(str, Enum):
    PROPOSAL = "proposal"  # valid, ready to confirm
    CLARIFY = "clarify"  # ambiguous / low-confidence (D4)
    REFUSE = "refuse"  # unsupported / unmappable / unsatisfiable / invalid (D10/D18)
    UNAVAILABLE = "unavailable"  # couldn't reach Alpaca (A-5)
    ERROR = "error"  # LLM/system failure


@dataclass(frozen=True)
class Proposal:
    """Everything shown at confirm (D-1): restatement + orders + current-vs-target."""

    restatement: str
    basis_notes: tuple[str, ...]
    mappings: tuple[SymbolMapping, ...]
    orders: tuple[PlannedOrder, ...]
    allocation: AllocationReport
    applied_constraints: tuple[str, ...]
    market_open: bool
    market_warning: str | None = None


@dataclass(frozen=True)
class ProposalOutcome:
    status: ProposalStatus
    proposal: Proposal | None = None
    message: str | None = None  # clarify question / refusal / error text
    problems: tuple[str, ...] = field(default_factory=tuple)  # validation reject reasons
    request_id: str | None = None  # audit-trail link when persisted
