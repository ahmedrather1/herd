"""Confirm-time re-validation + sequential execution + reporting (D-4/E-1/E-2).

On confirm, this service:

1. **Re-validates (D-4/D19).** Re-fetches state via the validator and, if the plan is no
   longer valid (a *material change* — validity flipped: buying power moved, a holding
   changed), returns ``REVALIDATE`` without submitting so the proposal is re-shown. It also
   holds if the market is now closed (D17).
2. **Executes (E-1/D15).** Submits orders one at a time in the plan's sells-first order and
   **stops on the first failure** (a reject or an Alpaca outage), leaving the account in its
   safe cash residue. Success is *accepted* granularity (D16).
3. **Reports (E-2).** Returns completed N of M, the accepted orders, any failure reason, and
   best-effort cash remaining. Each submission + response is recorded (D20) when a store is
   given.

Material change is defined narrowly for v1: re-validation flips to invalid. Re-planning on
price drift (recomputing targets at confirm) is a possible enhancement, flagged in QUESTIONS.
"""

from __future__ import annotations

from decimal import Decimal

from ..alpaca import AlpacaUnavailableError, OrderRejectedError
from ..alpaca.client import AlpacaClient
from ..planning import OrderValidator, Plan
from ..store import AuditStore, RequestStatus
from .models import ExecutionReport, ExecutionStatus, SubmittedResult


class ExecutionService:
    """Runs the confirm → re-validate → execute → report flow (D-4/E-1/E-2)."""

    def __init__(self, alpaca: AlpacaClient, store: AuditStore | None = None) -> None:
        self._alpaca = alpaca
        self._store = store

    def confirm_and_execute(self, plan: Plan, *, request_id: str | None = None) -> ExecutionReport:
        if not plan.orders:
            return ExecutionReport(ExecutionStatus.NOTHING, "There were no orders to place.")
        try:
            return self._run(plan, request_id)
        except AlpacaUnavailableError:
            self._set_status(request_id, RequestStatus.FAILED)
            return ExecutionReport(
                ExecutionStatus.UNAVAILABLE,
                "Can't reach Alpaca right now — nothing was submitted. Please try again.",
            )

    def _run(self, plan: Plan, request_id: str | None) -> ExecutionReport:
        # D-4: re-validate against fresh state.
        validation = OrderValidator(self._alpaca).validate(plan)
        if not validation.ok:
            return ExecutionReport(
                ExecutionStatus.REVALIDATE,
                "Your account changed since the proposal — here's an updated check before anything is placed.",
                revalidation_problems=tuple(p.reason for p in validation.problems),
            )
        if not self._alpaca.get_clock().is_open:  # D17: hold while closed
            return ExecutionReport(
                ExecutionStatus.MARKET_CLOSED,
                "The market is closed — nothing was submitted. Try again when it's open.",
            )

        self._set_status(request_id, RequestStatus.EXECUTING)
        total = len(plan.orders)
        submitted: list[SubmittedResult] = []
        failure: str | None = None

        for order in plan.orders:  # already sells-first, buys-second (D15)
            try:
                result = self._alpaca.submit_order(order.to_order_request())
            except OrderRejectedError as exc:
                failure = str(exc)
                submitted.append(SubmittedResult(order.symbol, order.side.value, "rejected", reason=failure))
                self._record(request_id, order, "rejected", raw=failure)
                break  # stop-on-failure (D15)
            except AlpacaUnavailableError:
                failure = "Alpaca became unreachable mid-execution."
                submitted.append(SubmittedResult(order.symbol, order.side.value, "failed", reason=failure))
                self._record(request_id, order, "failed", raw=failure)
                break  # stop-on-failure (D15) — remaining orders left unplaced, in cash
            else:
                submitted.append(SubmittedResult(order.symbol, order.side.value, "accepted", order_id=result.id))
                self._record(request_id, order, "accepted", order_id=result.id)

        completed = sum(1 for s in submitted if s.status == "accepted")
        cash = self._safe_cash()
        if failure is None:
            self._set_status(request_id, RequestStatus.COMPLETED)
            return ExecutionReport(
                ExecutionStatus.COMPLETED,
                f"Done — all {completed} orders were accepted.",
                submitted=tuple(submitted), completed=completed, total=total, cash_remaining=cash,
            )
        self._set_status(request_id, RequestStatus.FAILED)
        return ExecutionReport(
            ExecutionStatus.PARTIAL,
            f"Stopped after {completed} of {total} orders — the rest were left in cash.",
            submitted=tuple(submitted), completed=completed, total=total, failure=failure, cash_remaining=cash,
        )

    # --- helpers -------------------------------------------------------------

    def _safe_cash(self) -> Decimal | None:
        try:
            return self._alpaca.get_account().cash
        except AlpacaUnavailableError:
            return None

    def _record(self, request_id, order, status, *, order_id=None, raw=None) -> None:
        if self._store is None or request_id is None:
            return
        self._store.record_execution(
            request_id, symbol=order.symbol, side=order.side.value, status=status,
            qty=order.qty, notional=order.notional, alpaca_order_id=order_id, raw_response=raw,
        )

    def _set_status(self, request_id, status) -> None:
        if self._store is not None and request_id is not None:
            self._store.set_request_status(request_id, status)
