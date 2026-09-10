"""HTTP routes: propose → confirm (D24, D1/D4).

- ``POST /api/propose`` runs the read-side pipeline (D-1) and returns the proposal or a
  non-proposal outcome (clarify / refuse / …).
- ``POST /api/confirm`` reconstructs the plan from the **persisted proposal** and runs
  confirm-time re-validation + execution (D-4/E). Reconstructing from the audit store keeps
  the API stateless between the two calls; flagged in QUESTIONS.md as the confirm contract.

Endpoints are ``def`` (sync) so FastAPI offloads the synchronous Alpaca/LLM work to a
threadpool (D46).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException

from ..alpaca import AlpacaUnavailableError, OrderSide
from ..alpaca.client import AlpacaClient
from ..execution import ExecutionService
from ..planning import Plan, PlannedOrder
from ..proposal import ProposalService
from ..store import AuditStore
from .deps import get_alpaca, get_execution_service, get_proposal_service, get_store
from .schemas import (
    AllocationHolding,
    BalancePointSchema,
    ConfirmRequest,
    ConfirmResponse,
    PortfolioResponse,
    ProposeRequest,
    ProposeResponse,
    RequestDetailSchema,
    RequestSummarySchema,
    outcome_to_schema,
    report_to_schema,
    request_to_detail,
    request_to_summary,
)

router = APIRouter(prefix="/api", tags=["rebalancer"])


@router.post("/propose", response_model=ProposeResponse)
def propose(
    body: ProposeRequest,
    service: ProposalService = Depends(get_proposal_service),
) -> ProposeResponse:
    outcome = service.propose(body.request_text, conversation_id=body.conversation_id)
    return outcome_to_schema(outcome)


@router.post("/confirm", response_model=ConfirmResponse)
def confirm(
    body: ConfirmRequest,
    store: AuditStore = Depends(get_store),
    execution: ExecutionService = Depends(get_execution_service),
) -> ConfirmResponse:
    plan = _load_plan(store, body.request_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="No proposal found for that request id.")
    report = execution.confirm_and_execute(plan, request_id=body.request_id)
    return report_to_schema(report)


@router.post("/cancel", response_model=ConfirmResponse)
def cancel(
    body: ConfirmRequest,
    execution: ExecutionService = Depends(get_execution_service),
) -> ConfirmResponse:
    """Cancel all currently-open orders (D62). ``request_id`` links the audit record."""
    report = execution.cancel_open_orders(request_id=body.request_id)
    return report_to_schema(report)


@router.get("/portfolio", response_model=PortfolioResponse)
def portfolio(alpaca: AlpacaClient = Depends(get_alpaca)) -> PortfolioResponse:
    """Current allocation + equity trendline for the dashboard (D24)."""
    try:
        account = alpaca.get_account()
        positions = alpaca.get_positions()
        history = alpaca.get_balance_history()
    except AlpacaUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Can't reach Alpaca right now.") from exc

    equity = account.equity
    holdings = [
        AllocationHolding(symbol=p.symbol, value=str(p.market_value), pct=_pct(p.market_value, equity))
        for p in positions
    ]
    if account.cash > 0:
        holdings.append(AllocationHolding(symbol="CASH", value=str(account.cash), pct=_pct(account.cash, equity)))
    return PortfolioResponse(
        equity=str(equity),
        cash=str(account.cash),
        holdings=holdings,
        # Drop pre-funding $0 points so the trendline starts where the account has value.
        balance=[
            BalancePointSchema(date=pt.as_of.date().isoformat(), equity=str(pt.equity))
            for pt in history
            if pt.equity > 0
        ],
    )


def _pct(value: Decimal, equity: Decimal) -> str:
    if equity <= 0:
        return "0.00"
    return str((value / equity * Decimal("100")).quantize(Decimal("0.01")))


@router.get("/requests", response_model=list[RequestSummarySchema])
def list_requests(
    limit: int = 50, store: AuditStore = Depends(get_store)
) -> list[RequestSummarySchema]:
    """Recent requests, newest first — the viewable audit log (F-2/D22)."""
    return [request_to_summary(r) for r in store.list_requests(limit=limit)]


@router.get("/requests/{request_id}", response_model=RequestDetailSchema)
def get_request(request_id: str, store: AuditStore = Depends(get_store)) -> RequestDetailSchema:
    """The full stored record for one request (raw text, LLM calls, proposal, executions)."""
    request = store.get_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="No such request.")
    return request_to_detail(request)


def _load_plan(store: AuditStore, request_id: str) -> Plan | None:
    """Rebuild the ordered plan from the request's most recent persisted proposal."""
    request = store.get_request(request_id)
    if request is None or not request.proposals:
        return None
    proposal = request.proposals[-1]
    legs = sorted(proposal.legs, key=lambda leg: leg.sequence_index)
    orders = tuple(
        PlannedOrder(leg.symbol, OrderSide(leg.side), reason="", qty=leg.qty, notional=leg.notional)
        for leg in legs
    )
    return Plan(orders=orders)
