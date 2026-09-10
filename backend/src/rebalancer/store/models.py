"""Normalized audit/session schema (A-3, D49).

Real typed tables — no JSON-blob dodge for structured data. Only genuinely-freeform
*external* payloads are TEXT: LLM prompt/response (D21) and raw Alpaca responses (D20).
Money/quantities use ``DecimalString`` so they round-trip as exact ``Decimal`` (D45).

Graph::

    AppSession
      └─ Conversation
           └─ Request
                ├─ LlmCall          (parse/mapping prompts + raw responses, D21)
                ├─ Intent           (lean first-cut; expanded by B-1)
                ├─ Proposal
                │    └─ ProposedOrder (legs; sequence_index = sells-first/buys-second, D15)
                └─ OrderExecution   (submitted order + raw Alpaca response, D20)

``Intent`` and ``Proposal`` are intentionally lean here (A-3); B-1 and D-1 define those
shapes and expand these tables via drop-and-recreate (D49). F-1 populates the full record
end to end as features land.

NOTE: this module intentionally does **not** use ``from __future__ import annotations``.
SQLModel/SQLAlchemy 2.0 must see real relationship annotations at class-definition time;
stringized annotations break mapper initialization for ``Relationship`` fields.
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship, SQLModel

from .db import DecimalString


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class RequestStatus(str, Enum):
    """Lifecycle of a single user request through the propose/confirm/execute loop."""

    RECEIVED = "received"
    PARSED = "parsed"
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUSED = "refused"  # unsatisfiable/unmappable — refuse + explain (D10)


class AppSession(SQLModel, table=True):
    """A run/session for the single local user (D11); groups conversations across restarts."""

    __tablename__ = "app_session"

    id: str = Field(default_factory=_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=_now)

    conversations: list["Conversation"] = Relationship(back_populates="session")


class Conversation(SQLModel, table=True):
    """A thread of related requests (conversational follow-ups, D7/B-4)."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(foreign_key="app_session.id", index=True)
    created_at: datetime = Field(default_factory=_now)

    session: AppSession | None = Relationship(back_populates="conversations")
    requests: list["Request"] = Relationship(back_populates="conversation")


class Request(SQLModel, table=True):
    """One user request and everything derived from it (the audit record spine, D20)."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    conversation_id: str = Field(foreign_key="conversation.id", index=True)
    created_at: datetime = Field(default_factory=_now)
    raw_text: str
    status: RequestStatus = Field(default=RequestStatus.RECEIVED)

    conversation: Conversation | None = Relationship(back_populates="requests")
    llm_calls: list["LlmCall"] = Relationship(back_populates="request")
    intents: list["Intent"] = Relationship(back_populates="request")
    mappings: list["Mapping"] = Relationship(back_populates="request")
    proposals: list["Proposal"] = Relationship(back_populates="request")
    executions: list["OrderExecution"] = Relationship(back_populates="request")
    validation_problems: list["ValidationProblem"] = Relationship(back_populates="request")


class LlmCall(SQLModel, table=True):
    """A single LLM call's prompt + raw response (D21). A request may have several."""

    __tablename__ = "llm_call"

    id: str = Field(default_factory=_uuid, primary_key=True)
    request_id: str = Field(foreign_key="request.id", index=True)
    created_at: datetime = Field(default_factory=_now)
    purpose: str  # e.g. "parse", "category_map"
    model: str
    prompt: str = Field(sa_column=Column(Text))
    response: str = Field(sa_column=Column(Text))

    request: Request | None = Relationship(back_populates="llm_calls")


class Intent(SQLModel, table=True):
    """Interpreted intent (F-1) — normalized into operations + constraints (D49)."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    request_id: str = Field(foreign_key="request.id", index=True)
    created_at: datetime = Field(default_factory=_now)

    request: Request | None = Relationship(back_populates="intents")
    operations: list["IntentOperation"] = Relationship(back_populates="intent")
    constraints: list["IntentConstraint"] = Relationship(back_populates="intent")


class IntentOperation(SQLModel, table=True):
    """One operation of an interpreted intent, with its resolved basis (B-1/B-2, F-1)."""

    __tablename__ = "intent_operation"

    id: str = Field(default_factory=_uuid, primary_key=True)
    intent_id: str = Field(foreign_key="intent.id", index=True)
    sequence_index: int
    action: str  # "buy" | "sell" | "set_allocation"
    target: str
    amount_value: Decimal | None = Field(default=None, sa_column=Column(DecimalString, nullable=True))
    amount_basis: str | None = None
    amount_raw_phrase: str | None = None
    basis_explicit: bool = True
    basis_defaulted: bool = False

    intent: Intent | None = Relationship(back_populates="operations")


class IntentConstraint(SQLModel, table=True):
    """One constraint of an interpreted intent (D8, F-1)."""

    __tablename__ = "intent_constraint"

    id: str = Field(default_factory=_uuid, primary_key=True)
    intent_id: str = Field(foreign_key="intent.id", index=True)
    kind: str
    target: str | None = None
    value: Decimal | None = Field(default=None, sa_column=Column(DecimalString, nullable=True))
    raw_phrase: str | None = None

    intent: Intent | None = Relationship(back_populates="constraints")


class Mapping(SQLModel, table=True):
    """A resolved category→symbol mapping shown at confirm (B-3/D5, F-1)."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    request_id: str = Field(foreign_key="request.id", index=True)
    created_at: datetime = Field(default_factory=_now)
    target: str
    action: str
    source: str  # "literal" | "holdings" | "proposed"
    note: str | None = Field(default=None, sa_column=Column(Text))

    request: Request | None = Relationship(back_populates="mappings")
    symbols: list["MappedSymbol"] = Relationship(back_populates="mapping")


class MappedSymbol(SQLModel, table=True):
    """One concrete symbol a mapping resolved to."""

    __tablename__ = "mapped_symbol"

    id: str = Field(default_factory=_uuid, primary_key=True)
    mapping_id: str = Field(foreign_key="mapping.id", index=True)
    symbol: str

    mapping: Mapping | None = Relationship(back_populates="symbols")


class ValidationProblem(SQLModel, table=True):
    """A validation reject reason recorded when a request is refused (D-2/D18, F-1)."""

    __tablename__ = "validation_problem"

    id: str = Field(default_factory=_uuid, primary_key=True)
    request_id: str = Field(foreign_key="request.id", index=True)
    reason: str = Field(sa_column=Column(Text))

    request: Request | None = Relationship(back_populates="validation_problems")


class Proposal(SQLModel, table=True):
    """A proposed set of orders shown at confirm time (lean; D-1 expands)."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    request_id: str = Field(foreign_key="request.id", index=True)
    created_at: datetime = Field(default_factory=_now)
    summary: str | None = Field(default=None, sa_column=Column(Text))

    request: Request | None = Relationship(back_populates="proposals")
    legs: list["ProposedOrder"] = Relationship(back_populates="proposal")
    allocation_rows: list["AllocationSnapshot"] = Relationship(back_populates="proposal")


class ProposedOrder(SQLModel, table=True):
    """One leg of a proposal. ``sequence_index`` encodes sells-first/buys-second (D15)."""

    __tablename__ = "proposed_order"

    id: str = Field(default_factory=_uuid, primary_key=True)
    proposal_id: str = Field(foreign_key="proposal.id", index=True)
    sequence_index: int
    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal | None = Field(default=None, sa_column=Column(DecimalString, nullable=True))
    notional: Decimal | None = Field(default=None, sa_column=Column(DecimalString, nullable=True))

    proposal: Proposal | None = Relationship(back_populates="legs")


class AllocationSnapshot(SQLModel, table=True):
    """A per-symbol current-vs-target row captured with a proposal (C-3/D24, F-1)."""

    __tablename__ = "allocation_snapshot"

    id: str = Field(default_factory=_uuid, primary_key=True)
    proposal_id: str = Field(foreign_key="proposal.id", index=True)
    symbol: str
    current_value: Decimal = Field(sa_column=Column(DecimalString))
    current_pct: Decimal = Field(sa_column=Column(DecimalString))
    target_value: Decimal = Field(sa_column=Column(DecimalString))
    target_pct: Decimal = Field(sa_column=Column(DecimalString))
    delta_value: Decimal = Field(sa_column=Column(DecimalString))

    proposal: Proposal | None = Relationship(back_populates="allocation_rows")


class OrderExecution(SQLModel, table=True):
    """A submitted order and its raw Alpaca response (D20). Success at 'accepted' (D16)."""

    __tablename__ = "order_execution"

    id: str = Field(default_factory=_uuid, primary_key=True)
    request_id: str = Field(foreign_key="request.id", index=True)
    created_at: datetime = Field(default_factory=_now)
    symbol: str
    side: str
    qty: Decimal | None = Field(default=None, sa_column=Column(DecimalString, nullable=True))
    notional: Decimal | None = Field(default=None, sa_column=Column(DecimalString, nullable=True))
    alpaca_order_id: str | None = None
    status: str  # accepted / rejected / failed / filled ...
    raw_response: str | None = Field(default=None, sa_column=Column(Text))

    request: Request | None = Relationship(back_populates="executions")
