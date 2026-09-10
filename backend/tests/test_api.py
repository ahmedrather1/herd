"""HTTP API tests (D24): propose → confirm over the FastAPI app.

The service dependencies are overridden with fakes (mocked LLM, H-2 Alpaca, a temp store),
so these exercise the real routing / serialization / confirm-reconstruction, not the LLM or
network. propose and confirm share one store + one Alpaca so confirm finds the proposal.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fakes.fake_alpaca import FakeAlpacaClient
from fakes.fake_anthropic import FakeAnthropic, make_response

from rebalancer.api.deps import get_execution_service, get_proposal_service, get_store
from rebalancer.execution import ExecutionService
from rebalancer.main import app
from rebalancer.parsing import IntentParser, ParseStatus, SymbolResolver
from rebalancer.parsing.mapping import WireMappedTarget, WireMapping
from rebalancer.parsing.parser import WireAmount, WireIntent, WireOperation, WireParsedIntent
from rebalancer.proposal import ProposalService
from rebalancer.store import AuditStore, create_db_and_tables, make_engine


def _parse(status=ParseStatus.PARSED, *, operations=(), summary="ok", clarification=None):
    intent = WireIntent(operations=list(operations)) if operations else None
    return make_response(
        WireParsedIntent(status=status, confidence=0.9, summary=summary, intent=intent, clarification_question=clarification)
    )


def _op(action, target, value, basis):
    return WireOperation(action=action, target=target, amount=WireAmount(value=str(value), basis=basis))


def _mapping(**t2s):
    return make_response(WireMapping(mappings=[WireMappedTarget(target=t, symbols=list(s)) for t, s in t2s.items()]))


def _config_env(monkeypatch):
    from rebalancer import config

    monkeypatch.setenv("ALPACA_KEY", "pk-test")
    monkeypatch.setenv("ALPACA_SECRET", "secret-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    config.get_settings.cache_clear()


@pytest.fixture
def client(tmp_path, monkeypatch):
    _config_env(monkeypatch)
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    create_db_and_tables(engine)
    store = AuditStore(engine)
    alpaca = FakeAlpacaClient(equity="10000", buying_power="10000", cash="10000")
    alpaca.set_unknown_asset("BONDS")
    fake_llm = FakeAnthropic(
        _parse(operations=[_op("buy", "bonds", 10, "percent_portfolio")], summary="Put 10% into bonds."),
        _mapping(bonds=["BND"]),
    )
    proposal_service = ProposalService(
        IntentParser(fake_llm, model="claude-sonnet-5"),
        SymbolResolver(fake_llm, alpaca, model="claude-sonnet-5"),
        alpaca,
        store,
    )
    execution_service = ExecutionService(alpaca, store)

    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_proposal_service] = lambda: proposal_service
    app.dependency_overrides[get_execution_service] = lambda: execution_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_propose_then_confirm_flow(client):
    r = client.post("/api/propose", json={"request_text": "put 10% of my portfolio in bonds"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "proposal"
    (order,) = body["orders"]
    assert order["symbol"] == "BND" and order["side"] == "buy"
    assert order["notional"] == "1000.00" and order["qty"] is None  # money quantized to cents
    assert body["allocation"]["equity"] == "10000"
    request_id = body["request_id"]

    r2 = client.post("/api/confirm", json={"request_id": request_id})
    assert r2.status_code == 200
    confirmed = r2.json()
    assert confirmed["status"] == "completed"
    assert confirmed["completed"] == 1 and confirmed["total"] == 1
    assert confirmed["submitted"][0]["symbol"] == "BND"


def test_confirm_unknown_request_is_404(client):
    r = client.post("/api/confirm", json={"request_id": "does-not-exist"})
    assert r.status_code == 404


def test_audit_history_endpoints(client):
    request_id = client.post("/api/propose", json={"request_text": "put 10% in bonds"}).json()["request_id"]
    client.post("/api/confirm", json={"request_id": request_id})

    listing = client.get("/api/requests").json()
    assert any(row["request_id"] == request_id for row in listing)

    detail = client.get(f"/api/requests/{request_id}").json()
    assert detail["raw_text"] == "put 10% in bonds"
    assert {c["purpose"] for c in detail["llm_calls"]} == {"parse", "category_map"}
    assert detail["proposals"][0]["legs"][0]["symbol"] == "BND"
    assert detail["executions"][0]["status"] == "accepted"
    # Full record (F-1): intent operations, mapping, allocation snapshot.
    assert detail["intent"]["operations"][0]["target"] == "bonds"
    assert detail["mappings"][0]["symbols"] == ["BND"]
    assert any(row["symbol"] == "BND" for row in detail["proposals"][0]["allocation"])


def test_get_unknown_request_is_404(client):
    assert client.get("/api/requests/nope").status_code == 404


def test_propose_clarify(tmp_path, monkeypatch):
    _config_env(monkeypatch)
    engine = make_engine(f"sqlite:///{tmp_path / 'c.db'}")
    create_db_and_tables(engine)
    store = AuditStore(engine)
    alpaca = FakeAlpacaClient(equity="10000")
    fake_llm = FakeAnthropic(_parse(ParseStatus.NEEDS_CLARIFICATION, clarification="Which assets?"))
    service = ProposalService(
        IntentParser(fake_llm, model="m"), SymbolResolver(fake_llm, alpaca, model="m"), alpaca, store
    )
    app.dependency_overrides[get_proposal_service] = lambda: service
    with TestClient(app) as c:
        body = c.post("/api/propose", json={"request_text": "make it 60/40"}).json()
    app.dependency_overrides.clear()
    assert body["status"] == "clarify" and body["message"] == "Which assets?"
