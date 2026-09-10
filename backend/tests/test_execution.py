"""Tests for confirm-time re-validation + execution + reporting (D-4/E-1/E-2).

Uses the H-2 fake's order-outcome scripting (ACCEPT / Reject / Fail) to drive sequential
submission and stop-on-failure (D15), plus the re-validation, market-closed, unavailable,
and persistence paths.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fakes.fake_alpaca import ACCEPT, FakeAlpacaClient, Fail, Reject

from rebalancer.alpaca import OrderSide
from rebalancer.execution import ExecutionService, ExecutionStatus
from rebalancer.planning import Plan, PlannedOrder


def _buy(symbol, notional):
    return PlannedOrder(symbol, OrderSide.BUY, "buy", notional=Decimal(str(notional)))


def _sell_qty(symbol, qty):
    return PlannedOrder(symbol, OrderSide.SELL, "sell", qty=Decimal(str(qty)))


def _plan(*orders):
    return Plan(orders=tuple(orders))


# --- happy path --------------------------------------------------------------


def test_all_accepted_is_completed():
    alpaca = FakeAlpacaClient(cash="5000", buying_power="10000")
    report = ExecutionService(alpaca).confirm_and_execute(_plan(_buy("VTI", 1000)))
    assert report.status is ExecutionStatus.COMPLETED
    assert report.completed == 1 and report.total == 1
    assert report.submitted[0].status == "accepted"
    assert report.cash_remaining == Decimal("5000")


# --- stop-on-failure (D15) ---------------------------------------------------


def test_stops_on_first_failure_leaves_rest_in_cash():
    alpaca = FakeAlpacaClient(buying_power="10000")
    alpaca.set_position("AAPL", qty="10", price="100")  # funds the sell → validation ok
    alpaca.queue_outcomes(ACCEPT, Fail("Alpaca 503"))  # sell ok, buy fails
    report = ExecutionService(alpaca).confirm_and_execute(
        _plan(_sell_qty("AAPL", 5), _buy("VTI", 500))
    )
    assert report.status is ExecutionStatus.PARTIAL
    assert report.completed == 1 and report.total == 2
    assert report.failure is not None
    assert [s.symbol for s in report.submitted] == ["AAPL", "VTI"]
    assert report.submitted[1].status == "failed"


def test_rejected_order_halts_with_reason():
    alpaca = FakeAlpacaClient(buying_power="10000")
    alpaca.queue_outcomes(Reject("insufficient day trading buying power", symbol="VTI"))
    report = ExecutionService(alpaca).confirm_and_execute(_plan(_buy("VTI", 500)))
    assert report.status is ExecutionStatus.PARTIAL
    assert report.completed == 0
    assert "buying power" in report.failure


# --- confirm-time re-validation (D-4) ----------------------------------------


def test_revalidation_blocks_when_state_changed():
    # Buying power dropped since the proposal → plan no longer valid → re-show, no submit.
    alpaca = FakeAlpacaClient(buying_power="1000")
    report = ExecutionService(alpaca).confirm_and_execute(_plan(_buy("VTI", 5000)))
    assert report.status is ExecutionStatus.REVALIDATE
    assert report.revalidation_problems
    assert alpaca.attempts == []  # nothing was submitted


def test_market_closed_blocks_submission():
    alpaca = FakeAlpacaClient(buying_power="10000", is_open=False)
    report = ExecutionService(alpaca).confirm_and_execute(_plan(_buy("VTI", 500)))
    assert report.status is ExecutionStatus.MARKET_CLOSED
    assert alpaca.attempts == []


def test_alpaca_unavailable():
    alpaca = FakeAlpacaClient(buying_power="10000")
    alpaca.set_unavailable(True)
    report = ExecutionService(alpaca).confirm_and_execute(_plan(_buy("VTI", 500)))
    assert report.status is ExecutionStatus.UNAVAILABLE


def test_empty_plan_is_nothing():
    report = ExecutionService(FakeAlpacaClient()).confirm_and_execute(Plan())
    assert report.status is ExecutionStatus.NOTHING


# --- cancel open orders (D62) ------------------------------------------------


def test_cancel_open_orders():
    from rebalancer.alpaca import OrderRequest

    alpaca = FakeAlpacaClient(buying_power="10000")
    alpaca.submit_order(OrderRequest(symbol="VTI", side=OrderSide.BUY, notional=Decimal("500")))
    alpaca.submit_order(OrderRequest(symbol="BND", side=OrderSide.BUY, notional=Decimal("400")))

    report = ExecutionService(alpaca).cancel_open_orders()
    assert report.status is ExecutionStatus.CANCELED
    assert report.completed == 2 and report.total == 2
    assert all(s.status == "canceled" for s in report.submitted)
    assert alpaca.get_open_orders() == []  # all gone


def test_cancel_with_no_open_orders_is_nothing():
    report = ExecutionService(FakeAlpacaClient()).cancel_open_orders()
    assert report.status is ExecutionStatus.NOTHING


def test_cancel_unavailable():
    alpaca = FakeAlpacaClient()
    alpaca.set_unavailable(True)
    report = ExecutionService(alpaca).cancel_open_orders()
    assert report.status is ExecutionStatus.UNAVAILABLE


# --- persistence (D20) -------------------------------------------------------


def test_executions_and_status_persisted(tmp_path):
    from rebalancer.store import AuditStore, RequestStatus, create_db_and_tables, make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    create_db_and_tables(engine)
    store = AuditStore(engine)
    request_id = store.record_request(store.start_conversation(store.create_session()), "buy VTI")

    alpaca = FakeAlpacaClient(buying_power="10000")
    report = ExecutionService(alpaca, store).confirm_and_execute(_plan(_buy("VTI", 1000)), request_id=request_id)
    assert report.status is ExecutionStatus.COMPLETED

    request = store.get_request(request_id)
    assert request.status is RequestStatus.COMPLETED
    assert len(request.executions) == 1 and request.executions[0].status == "accepted"
