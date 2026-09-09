"""Write/read API over the persistence layer (A-3, D49).

``AuditStore`` is the seam the rest of the app uses to record the audit trail (D20/D21)
and read it back for the viewable log (F-2). A-3 provides the foundation and core
operations; later epics call these as they build the propose/confirm/execute loop, and
F-1 wires the full end-to-end record.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.engine import Engine
from sqlalchemy.orm import selectinload
from sqlmodel import select

from .db import session_scope
from .models import (
    AppSession,
    Conversation,
    Intent,
    LlmCall,
    OrderExecution,
    Proposal,
    ProposedOrder,
    Request,
    RequestStatus,
)


class ProposedLeg:
    """Lightweight input for a proposal leg (avoids constructing ORM rows at call sites)."""

    def __init__(
        self,
        *,
        symbol: str,
        side: str,
        sequence_index: int,
        qty: Decimal | None = None,
        notional: Decimal | None = None,
    ) -> None:
        self.symbol = symbol
        self.side = side
        self.sequence_index = sequence_index
        self.qty = qty
        self.notional = notional


class AuditStore:
    """Records and reads the per-request audit graph."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # --- session / conversation / request ------------------------------------

    def create_session(self) -> str:
        with session_scope(self._engine) as s:
            row = AppSession()
            s.add(row)
            s.flush()
            return row.id

    def start_conversation(self, session_id: str) -> str:
        with session_scope(self._engine) as s:
            row = Conversation(session_id=session_id)
            s.add(row)
            s.flush()
            return row.id

    def record_request(
        self,
        conversation_id: str,
        raw_text: str,
        status: RequestStatus = RequestStatus.RECEIVED,
    ) -> str:
        with session_scope(self._engine) as s:
            row = Request(conversation_id=conversation_id, raw_text=raw_text, status=status)
            s.add(row)
            s.flush()
            return row.id

    def set_request_status(self, request_id: str, status: RequestStatus) -> None:
        with session_scope(self._engine) as s:
            row = s.get(Request, request_id)
            if row is None:
                raise KeyError(f"unknown request: {request_id}")
            row.status = status
            s.add(row)

    # --- derived records -----------------------------------------------------

    def record_llm_call(
        self, request_id: str, *, purpose: str, model: str, prompt: str, response: str
    ) -> str:
        with session_scope(self._engine) as s:
            row = LlmCall(
                request_id=request_id,
                purpose=purpose,
                model=model,
                prompt=prompt,
                response=response,
            )
            s.add(row)
            s.flush()
            return row.id

    def record_intent(
        self,
        request_id: str,
        *,
        action: str,
        amount: Decimal | None = None,
        amount_basis: str | None = None,
        notes: str | None = None,
    ) -> str:
        with session_scope(self._engine) as s:
            row = Intent(
                request_id=request_id,
                action=action,
                amount=amount,
                amount_basis=amount_basis,
                notes=notes,
            )
            s.add(row)
            s.flush()
            return row.id

    def record_proposal(
        self, request_id: str, *, summary: str | None = None, legs: list[ProposedLeg] = ()
    ) -> str:
        with session_scope(self._engine) as s:
            proposal = Proposal(request_id=request_id, summary=summary)
            s.add(proposal)
            s.flush()
            for leg in legs:
                s.add(
                    ProposedOrder(
                        proposal_id=proposal.id,
                        sequence_index=leg.sequence_index,
                        symbol=leg.symbol,
                        side=leg.side,
                        qty=leg.qty,
                        notional=leg.notional,
                    )
                )
            return proposal.id

    def record_execution(
        self,
        request_id: str,
        *,
        symbol: str,
        side: str,
        status: str,
        qty: Decimal | None = None,
        notional: Decimal | None = None,
        alpaca_order_id: str | None = None,
        raw_response: str | None = None,
    ) -> str:
        with session_scope(self._engine) as s:
            row = OrderExecution(
                request_id=request_id,
                symbol=symbol,
                side=side,
                status=status,
                qty=qty,
                notional=notional,
                alpaca_order_id=alpaca_order_id,
                raw_response=raw_response,
            )
            s.add(row)
            s.flush()
            return row.id

    # --- reads ---------------------------------------------------------------

    def get_request(self, request_id: str) -> Request | None:
        """Return a request with its children eagerly loaded (detached but populated)."""
        with session_scope(self._engine) as s:
            stmt = (
                select(Request)
                .where(Request.id == request_id)
                .options(
                    selectinload(Request.llm_calls),
                    selectinload(Request.intents),
                    selectinload(Request.proposals).selectinload(Proposal.legs),
                    selectinload(Request.executions),
                )
            )
            row = s.exec(stmt).one_or_none()
            if row is None:
                return None
            s.expunge_all()
            return row

    def list_requests(self, limit: int = 50) -> list[Request]:
        """Return recent requests (newest first), without children — for the history list (F-2)."""
        with session_scope(self._engine) as s:
            stmt = select(Request).order_by(Request.created_at.desc()).limit(limit)
            rows = list(s.exec(stmt).all())
            s.expunge_all()
            return rows

    def latest_proposal_summary(self, conversation_id: str) -> str | None:
        """Most recent proposal restatement in a conversation — context for follow-ups (B-4)."""
        with session_scope(self._engine) as s:
            stmt = (
                select(Proposal)
                .join(Request, Proposal.request_id == Request.id)
                .where(Request.conversation_id == conversation_id)
                .order_by(Proposal.created_at.desc())
                .limit(1)
            )
            row = s.exec(stmt).first()
            return row.summary if row is not None else None
