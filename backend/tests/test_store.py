"""Tests for the local persistence layer (A-3, D49).

Covers: the normalized session→conversation→request→children graph round-trips; money is
stored as exact TEXT and returns as ``Decimal`` (D45); state survives a "restart" (a fresh
engine on the same file); the default path auto-creates; and status transitions persist.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from rebalancer.store import (
    AuditStore,
    ProposedLeg,
    RequestStatus,
    create_db_and_tables,
    make_engine,
    session_scope,
)


@pytest.fixture
def engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    create_db_and_tables(eng)
    return eng


@pytest.fixture
def store(engine):
    return AuditStore(engine)


def _seed_request(store: AuditStore, raw_text="rebalance to 60/40") -> str:
    session_id = store.create_session()
    conversation_id = store.start_conversation(session_id)
    return store.record_request(conversation_id, raw_text)


# --- graph round-trip --------------------------------------------------------


def test_full_graph_round_trips(store):
    request_id = _seed_request(store)
    store.record_llm_call(
        request_id, purpose="parse", model="claude", prompt="P", response="R"
    )
    store.record_intent(
        request_id, action="rebalance", amount=Decimal("60"), amount_basis="portfolio"
    )
    store.record_proposal(
        request_id,
        summary="sell BND, buy VTI",
        legs=[
            ProposedLeg(symbol="BND", side="sell", sequence_index=0, qty=Decimal("5")),
            ProposedLeg(symbol="VTI", side="buy", sequence_index=1, notional=Decimal("750.25")),
        ],
    )
    store.record_execution(
        request_id, symbol="BND", side="sell", status="accepted", qty=Decimal("5"),
        alpaca_order_id="ord-1", raw_response='{"id": "ord-1", "status": "accepted"}',
    )

    req = store.get_request(request_id)
    assert req is not None
    assert req.raw_text == "rebalance to 60/40"
    assert len(req.llm_calls) == 1 and req.llm_calls[0].purpose == "parse"
    assert req.intents[0].amount == Decimal("60")
    assert len(req.proposals) == 1
    legs = sorted(req.proposals[0].legs, key=lambda leg: leg.sequence_index)
    assert [leg.symbol for leg in legs] == ["BND", "VTI"]
    assert legs[1].notional == Decimal("750.25")
    assert req.executions[0].alpaca_order_id == "ord-1"


def test_get_missing_request_returns_none(store):
    assert store.get_request("nope") is None


# --- Decimal exactness (D45) -------------------------------------------------


def test_decimal_returns_as_decimal_not_float(store):
    request_id = _seed_request(store)
    store.record_intent(request_id, action="buy", amount=Decimal("10.005"))
    amount = store.get_request(request_id).intents[0].amount
    assert isinstance(amount, Decimal)
    assert amount == Decimal("10.005")


def test_money_column_is_stored_as_text(engine, store):
    # A value 0.1 + 0.2 would misbehave as a float; confirm the DB keeps exact TEXT.
    request_id = _seed_request(store)
    store.record_intent(request_id, action="buy", amount=Decimal("0.30"))
    with session_scope(engine) as s:
        typ = s.exec(text("SELECT typeof(amount) FROM intent")).one()[0]
        raw = s.exec(text("SELECT amount FROM intent")).one()[0]
    assert typ == "text"
    assert raw == "0.30"  # exact string, trailing zero preserved


# --- durability + lifecycle --------------------------------------------------


def test_state_survives_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'persist.db'}"
    first = make_engine(url)
    create_db_and_tables(first)
    request_id = _seed_request(AuditStore(first), raw_text="only new deposits")
    first.dispose()  # simulate process exit

    # Fresh engine on the same file — data is still there.
    second = make_engine(url)
    reread = AuditStore(second).get_request(request_id)
    assert reread is not None and reread.raw_text == "only new deposits"


def test_default_path_auto_creates(tmp_path, monkeypatch):
    import rebalancer.store.db as db

    target = tmp_path / "data" / "rebalancer.db"
    monkeypatch.delenv(db.DB_URL_ENV, raising=False)
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", target)
    assert not target.parent.exists()

    engine = db.make_engine()  # no url -> default path, dir created on demand
    db.create_db_and_tables(engine)
    AuditStore(engine).create_session()

    assert target.exists()


def test_request_status_transition_persists(store):
    request_id = _seed_request(store)
    assert store.get_request(request_id).status is RequestStatus.RECEIVED
    store.set_request_status(request_id, RequestStatus.PROPOSED)
    assert store.get_request(request_id).status is RequestStatus.PROPOSED


def test_set_status_unknown_request_raises(store):
    with pytest.raises(KeyError):
        store.set_request_status("ghost", RequestStatus.COMPLETED)
