"""JSON request/response schemas for the HTTP API (D24).

Money and quantities are serialized as **strings** to preserve exact ``Decimal`` values over
JSON (D45) — the SPA formats them for display. This is the wire contract the frontend (G)
codes against; it's flagged in QUESTIONS.md as a reviewable shape.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


def _s(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


class ProposeRequest(BaseModel):
    request_text: str
    conversation_id: str | None = None


class OrderSchema(BaseModel):
    symbol: str
    side: str
    qty: str | None = None
    notional: str | None = None
    reason: str = ""


class AllocationRowSchema(BaseModel):
    symbol: str
    current_value: str
    current_pct: str
    target_value: str
    target_pct: str
    delta_value: str


class AllocationSchema(BaseModel):
    equity: str
    rows: list[AllocationRowSchema]


class ProposeResponse(BaseModel):
    status: str
    request_id: str | None = None
    message: str | None = None
    problems: list[str] = []
    restatement: str | None = None
    orders: list[OrderSchema] = []
    allocation: AllocationSchema | None = None
    applied_constraints: list[str] = []
    market_open: bool | None = None
    market_warning: str | None = None


class ConfirmRequest(BaseModel):
    request_id: str


class SubmittedSchema(BaseModel):
    symbol: str
    side: str
    status: str
    order_id: str | None = None
    reason: str | None = None


class ConfirmResponse(BaseModel):
    status: str
    message: str
    completed: int = 0
    total: int = 0
    failure: str | None = None
    cash_remaining: str | None = None
    submitted: list[SubmittedSchema] = []
    revalidation_problems: list[str] = []


# --- mappers from domain objects to schemas ----------------------------------


def order_to_schema(order) -> OrderSchema:
    return OrderSchema(
        symbol=order.symbol, side=order.side.value, qty=_s(order.qty), notional=_s(order.notional), reason=order.reason
    )


def allocation_to_schema(report) -> AllocationSchema:
    return AllocationSchema(
        equity=str(report.equity),
        rows=[
            AllocationRowSchema(
                symbol=r.symbol,
                current_value=str(r.current_value),
                current_pct=str(r.current_pct),
                target_value=str(r.target_value),
                target_pct=str(r.target_pct),
                delta_value=str(r.delta_value),
            )
            for r in report.rows
        ],
    )


def outcome_to_schema(outcome) -> ProposeResponse:
    p = outcome.proposal
    return ProposeResponse(
        status=outcome.status.value,
        request_id=outcome.request_id,
        message=outcome.message,
        problems=list(outcome.problems),
        restatement=p.restatement if p else None,
        orders=[order_to_schema(o) for o in p.orders] if p else [],
        allocation=allocation_to_schema(p.allocation) if p else None,
        applied_constraints=list(p.applied_constraints) if p else [],
        market_open=p.market_open if p else None,
        market_warning=p.market_warning if p else None,
    )


class RequestSummarySchema(BaseModel):
    request_id: str
    raw_text: str
    status: str
    created_at: str


class LlmCallSchema(BaseModel):
    purpose: str
    model: str
    prompt: str
    response: str
    created_at: str


class ProposalLegSchema(BaseModel):
    symbol: str
    side: str
    sequence_index: int
    qty: str | None = None
    notional: str | None = None


class StoredProposalSchema(BaseModel):
    summary: str | None = None
    created_at: str
    legs: list[ProposalLegSchema] = []


class ExecutionSchema(BaseModel):
    symbol: str
    side: str
    status: str
    qty: str | None = None
    notional: str | None = None
    alpaca_order_id: str | None = None
    created_at: str


class RequestDetailSchema(RequestSummarySchema):
    llm_calls: list[LlmCallSchema] = []
    proposals: list[StoredProposalSchema] = []
    executions: list[ExecutionSchema] = []


def _iso(dt) -> str:
    return dt.isoformat() if dt is not None else ""


def request_to_summary(request) -> RequestSummarySchema:
    return RequestSummarySchema(
        request_id=request.id,
        raw_text=request.raw_text,
        status=request.status.value if hasattr(request.status, "value") else str(request.status),
        created_at=_iso(request.created_at),
    )


def request_to_detail(request) -> RequestDetailSchema:
    return RequestDetailSchema(
        **request_to_summary(request).model_dump(),
        llm_calls=[
            LlmCallSchema(purpose=c.purpose, model=c.model, prompt=c.prompt, response=c.response, created_at=_iso(c.created_at))
            for c in request.llm_calls
        ],
        proposals=[
            StoredProposalSchema(
                summary=p.summary,
                created_at=_iso(p.created_at),
                legs=[
                    ProposalLegSchema(symbol=leg.symbol, side=leg.side, sequence_index=leg.sequence_index, qty=_s(leg.qty), notional=_s(leg.notional))
                    for leg in sorted(p.legs, key=lambda leg: leg.sequence_index)
                ],
            )
            for p in request.proposals
        ],
        executions=[
            ExecutionSchema(
                symbol=e.symbol, side=e.side, status=e.status, qty=_s(e.qty), notional=_s(e.notional),
                alpaca_order_id=e.alpaca_order_id, created_at=_iso(e.created_at),
            )
            for e in request.executions
        ],
    )


def report_to_schema(report) -> ConfirmResponse:
    return ConfirmResponse(
        status=report.status.value,
        message=report.message,
        completed=report.completed,
        total=report.total,
        failure=report.failure,
        cash_remaining=_s(report.cash_remaining),
        submitted=[
            SubmittedSchema(symbol=s.symbol, side=s.side, status=s.status, order_id=s.order_id, reason=s.reason)
            for s in report.submitted
        ],
        revalidation_problems=list(report.revalidation_problems),
    )
