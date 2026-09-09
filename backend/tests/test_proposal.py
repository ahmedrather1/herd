"""Tests for proposal assembly (D-1).

The full read-side pipeline wired together, with the LLM mocked (FakeAnthropic, shared by
parser + resolver) and Alpaca as the H-2 fake. Covers the happy path plus every
short-circuit: clarify, unsupported/mapping/constraint/validation refusals, market-closed
warning, Alpaca-unavailable (A-5), and audit persistence (D20).
"""

from __future__ import annotations

from decimal import Decimal

from fakes.fake_alpaca import FakeAlpacaClient
from fakes.fake_anthropic import FakeAnthropic, make_response

from rebalancer.parsing import IntentParser, ParseStatus, SymbolResolver
from rebalancer.parsing.mapping import WireMappedTarget, WireMapping
from rebalancer.parsing.parser import WireAmount, WireIntent, WireOperation, WireParsedIntent
from rebalancer.proposal import ProposalService, ProposalStatus


def _parse(status=ParseStatus.PARSED, *, operations=(), summary="ok", clarification=None, explanation=None):
    intent = WireIntent(operations=list(operations)) if operations else None
    return make_response(
        WireParsedIntent(
            status=status, confidence=0.9, summary=summary, intent=intent,
            clarification_question=clarification, explanation=explanation,
        )
    )


def _op(action, target, value=None, basis=None, explicit=True):
    amount = WireAmount(value=str(value), basis=basis, basis_explicit=explicit) if value is not None else None
    return WireOperation(action=action, target=target, amount=amount)


def _mapping(**target_to_symbols):
    return make_response(
        WireMapping(mappings=[WireMappedTarget(target=t, symbols=list(s)) for t, s in target_to_symbols.items()])
    )


def _service(alpaca, *responses, store=None):
    fake = FakeAnthropic(*responses)
    parser = IntentParser(fake, model="claude-sonnet-5")
    resolver = SymbolResolver(fake, alpaca, model="claude-sonnet-5")
    return ProposalService(parser, resolver, alpaca, store)


# --- happy path --------------------------------------------------------------


def test_proposal_happy_path():
    alpaca = FakeAlpacaClient(equity="10000", buying_power="10000")
    alpaca.set_unknown_asset("BONDS")  # "bonds" is a category
    service = _service(
        alpaca,
        _parse(operations=[_op("buy", "bonds", 10, "percent_portfolio")], summary="Put 10% of the portfolio into bonds."),
        _mapping(bonds=["BND"]),
    )
    outcome = service.propose("put 10% of my portfolio in bonds")
    assert outcome.status is ProposalStatus.PROPOSAL
    p = outcome.proposal
    assert [o.symbol for o in p.orders] == ["BND"] and p.orders[0].notional == Decimal("1000")
    assert "bonds → BND" in p.restatement
    assert p.market_open is True and p.market_warning is None


def test_market_closed_proposal_carries_warning():
    alpaca = FakeAlpacaClient(equity="10000", buying_power="10000", is_open=False)
    alpaca.set_unknown_asset("BONDS")
    service = _service(
        alpaca,
        _parse(operations=[_op("buy", "bonds", 10, "percent_portfolio")]),
        _mapping(bonds=["BND"]),
    )
    outcome = service.propose("put 10% in bonds")
    assert outcome.status is ProposalStatus.PROPOSAL
    assert outcome.proposal.market_open is False and outcome.proposal.market_warning


# --- short-circuits ----------------------------------------------------------


def test_needs_clarification_becomes_clarify():
    alpaca = FakeAlpacaClient(equity="10000")
    service = _service(alpaca, _parse(ParseStatus.NEEDS_CLARIFICATION, clarification="Which assets?"))
    outcome = service.propose("make it 60/40")
    assert outcome.status is ProposalStatus.CLARIFY and outcome.message == "Which assets?"


def test_unsupported_becomes_refuse():
    alpaca = FakeAlpacaClient(equity="10000")
    service = _service(alpaca, _parse(ParseStatus.UNSUPPORTED, explanation="Crypto isn't supported."))
    outcome = service.propose("buy bitcoin")
    assert outcome.status is ProposalStatus.REFUSE and "Crypto" in outcome.message


def test_mapping_refusal_becomes_refuse():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_unknown_asset("WIDGETS")
    service = _service(
        alpaca,
        _parse(operations=[_op("buy", "widgets", 10, "percent_portfolio")]),
        _mapping(widgets=[]),  # model maps to nothing
    )
    outcome = service.propose("put 10% in widgets")
    assert outcome.status is ProposalStatus.REFUSE


def test_constraint_refusal_becomes_refuse():
    alpaca = FakeAlpacaClient(equity="10000", buying_power="10000")
    # Literal symbol VTI (no mapping LLM call) + an only-new-deposits constraint.
    parse = make_response(
        WireParsedIntent(
            status=ParseStatus.PARSED, confidence=0.9, summary="invest with new deposits",
            intent=WireIntent(
                operations=[_op("buy", "VTI", 1000, "absolute_cash")],
                constraints=[{"kind": "only_new_deposits", "raw_phrase": "only new deposits"}],
            ),
        )
    )
    outcome = _service(alpaca, parse).propose("invest $1000 using only new deposits")
    assert outcome.status is ProposalStatus.REFUSE and "new deposits" in outcome.message


def test_validation_refusal_lists_problems():
    alpaca = FakeAlpacaClient(equity="1000", buying_power="1000")
    service = _service(alpaca, _parse(operations=[_op("buy", "VTI", 5000, "absolute_cash")]))
    outcome = service.propose("buy $5000 of VTI")
    assert outcome.status is ProposalStatus.REFUSE
    assert any("buying power" in p for p in outcome.problems)


def test_alpaca_unavailable_becomes_unavailable():
    alpaca = FakeAlpacaClient(equity="10000")
    alpaca.set_unavailable(True)
    service = _service(alpaca, _parse(operations=[_op("buy", "VTI", 1000, "absolute_cash")]))
    outcome = service.propose("buy $1000 of VTI")
    assert outcome.status is ProposalStatus.UNAVAILABLE


# --- persistence (D20) -------------------------------------------------------


def test_followup_threads_prior_proposal_as_context(tmp_path):
    from rebalancer.store import AuditStore, create_db_and_tables, make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'conv.db'}")
    create_db_and_tables(engine)
    store = AuditStore(engine)

    alpaca = FakeAlpacaClient(equity="10000", buying_power="10000")
    alpaca.set_unknown_asset("BONDS")
    fake = FakeAnthropic(
        _parse(
            operations=[_op("set_allocation", "stocks", 60, "target_weight"), _op("set_allocation", "bonds", 40, "target_weight")],
            summary="Rebalance to 60% stocks / 40% bonds.",
        ),
        _mapping(stocks=["VTI"], bonds=["BND"]),
        _parse(
            operations=[_op("set_allocation", "stocks", 70, "target_weight"), _op("set_allocation", "bonds", 30, "target_weight")],
            summary="Rebalance to 70/30.",
        ),
        _mapping(stocks=["VTI"], bonds=["BND"]),
    )
    service = ProposalService(
        IntentParser(fake, model="m"), SymbolResolver(fake, alpaca, model="m"), alpaca, store
    )

    first = service.propose("make it 60/40 stocks and bonds")
    assert first.status is ProposalStatus.PROPOSAL and first.conversation_id

    second = service.propose("actually make it 70/30", conversation_id=first.conversation_id)
    assert second.status is ProposalStatus.PROPOSAL

    # The follow-up's parse call was seeded with the prior proposal as context (B-4).
    parse_calls = [c for c in fake.messages.calls if c["output_format"].__name__ == "WireParsedIntent"]
    turn2_context = parse_calls[1]["messages"][0]["content"]
    assert "60% stocks" in turn2_context and "70/30" in turn2_context


def test_proposal_is_persisted(tmp_path):
    from rebalancer.store import AuditStore, RequestStatus, create_db_and_tables, make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    create_db_and_tables(engine)
    store = AuditStore(engine)

    alpaca = FakeAlpacaClient(equity="10000", buying_power="10000")
    alpaca.set_unknown_asset("BONDS")
    service = _service(
        alpaca,
        _parse(operations=[_op("buy", "bonds", 10, "percent_portfolio")]),
        _mapping(bonds=["BND"]),
        store=store,
    )
    outcome = service.propose("put 10% in bonds")
    assert outcome.status is ProposalStatus.PROPOSAL and outcome.request_id

    request = store.get_request(outcome.request_id)
    assert request.status is RequestStatus.PROPOSED
    assert {c.purpose for c in request.llm_calls} == {"parse", "category_map"}
    assert len(request.proposals) == 1 and len(request.proposals[0].legs) == 1
