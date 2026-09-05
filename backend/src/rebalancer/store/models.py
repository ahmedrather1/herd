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
    proposals: list["Proposal"] = Relationship(back_populates="request")
    executions: list["OrderExecution"] = Relationship(back_populates="request")


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
    """Interpreted intent (lean first-cut, A-3). B-1 defines/expands the real shape."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    request_id: str = Field(foreign_key="request.id", index=True)
    created_at: datetime = Field(default_factory=_now)
    action: str  # e.g. "rebalance", "buy", "sell"
    amount: Decimal | None = Field(default=None, sa_column=Column(DecimalString, nullable=True))
    amount_basis: str | None = None  # "portfolio" | "cash" | "absolute" (D2) — refined at B-2
    notes: str | None = Field(default=None, sa_column=Column(Text))

    request: Request | None = Relationship(back_populates="intents")


class Proposal(SQLModel, table=True):
    """A proposed set of orders shown at confirm time (lean; D-1 expands)."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    request_id: str = Field(foreign_key="request.id", index=True)
    created_at: datetime = Field(default_factory=_now)
    summary: str | None = Field(default=None, sa_column=Column(Text))

    request: Request | None = Relationship(back_populates="proposals")
    legs: list["ProposedOrder"] = Relationship(back_populates="proposal")


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
