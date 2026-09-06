"""Mocked-LLM tests for the intent parser (B-1, D29).

These verify the plumbing deterministically: the parsed/clarify/unsupported outcomes map
through to the domain contract, amounts round-trip to exact ``Decimal`` (D45), every
failure mode (refusal, no output, malformed, LLM exception) becomes a non-executing parse
failure, the request is sent with the configured model/schema, and the raw prompt+response
are captured and persist to the audit trail (D21). Real parse *quality* is measured
separately by the golden-set eval (H-3), not here.
"""

from __future__ import annotations

from decimal import Decimal

from fakes.fake_anthropic import FakeAnthropic, make_response

from rebalancer.parsing import AmountBasis, IntentParser, ParseStatus
from rebalancer.parsing.parser import (
    WireAmount,
    WireConstraint,
    WireIntent,
    WireOperation,
    WireParsedIntent,
)


def _parser(*responses):
    return IntentParser(FakeAnthropic(*responses), model="claude-sonnet-5")


def _wire_parsed(operations=(), constraints=(), *, confidence=0.9, summary="ok"):
    return WireParsedIntent(
        status=ParseStatus.PARSED,
        confidence=confidence,
        summary=summary,
        intent=WireIntent(operations=list(operations), constraints=list(constraints)),
    )


# --- happy path: outcome + mapping -------------------------------------------


def test_parsed_maps_operations_amounts_constraints():
    wire = _wire_parsed(
        operations=[
            WireOperation(
                action="sell",
                target="tech",
                amount=WireAmount(value="50", basis=AmountBasis.PERCENT_SOURCE_POSITION, raw_phrase="half"),
            ),
            WireOperation(
                action="buy",
                target="bonds",
                amount=WireAmount(value="10", basis=AmountBasis.PERCENT_PORTFOLIO, raw_phrase="10%"),
            ),
        ],
        constraints=[WireConstraint(kind="exclude_asset", target="AAPL", raw_phrase="don't sell AAPL")],
    )
    result = _parser(make_response(wire)).parse("sell half my tech, 10% to bonds, keep AAPL")

    assert result.ok and result.parsed is not None
    intent = result.parsed.intent
    assert [op.action for op in intent.operations] == ["sell", "buy"]
    sell = intent.operations[0]
    assert sell.amount.value == Decimal("50")
    assert isinstance(sell.amount.value, Decimal)
    assert sell.amount.basis is AmountBasis.PERCENT_SOURCE_POSITION
    assert intent.constraints[0].kind == "exclude_asset"
    assert intent.constraints[0].target == "AAPL"


def test_amount_can_be_absent():
    wire = _wire_parsed(operations=[WireOperation(action="sell", target="everything")])
    result = _parser(make_response(wire)).parse("sell everything")
    assert result.ok
    assert result.parsed.intent.operations[0].amount is None


def test_needs_clarification_passthrough():
    wire = WireParsedIntent(
        status=ParseStatus.NEEDS_CLARIFICATION,
        confidence=0.4,
        summary="unclear what 60/40 refers to",
        clarification_question="Which assets should the 60/40 split apply to?",
    )
    result = _parser(make_response(wire)).parse("make it 60/40")
    assert result.ok
    assert result.parsed.status is ParseStatus.NEEDS_CLARIFICATION
    assert "60/40" in result.parsed.clarification_question or result.parsed.clarification_question


def test_unsupported_passthrough_with_explanation():
    wire = WireParsedIntent(
        status=ParseStatus.UNSUPPORTED,
        confidence=0.95,
        summary="request is for crypto",
        explanation="This tool only trades US-listed equities and ETFs, not crypto.",
    )
    result = _parser(make_response(wire)).parse("put half my cash in bitcoin")
    assert result.ok
    assert result.parsed.status is ParseStatus.UNSUPPORTED
    assert "crypto" in result.parsed.explanation.lower()


# --- failure modes: never execute (B-1/D4) -----------------------------------


def test_refusal_is_parse_failure():
    wire = _wire_parsed(operations=[WireOperation(action="buy", target="AAPL")])
    result = _parser(make_response(wire, stop_reason="refusal")).parse("...")
    assert result.ok is False
    assert result.parsed is None
    assert "declin" in result.error.lower()


def test_no_structured_output_is_parse_failure():
    result = _parser(make_response(None)).parse("gibberish")
    assert result.ok is False and result.parsed is None


def test_malformed_amount_is_parse_failure():
    # Wire value is a free string; a non-numeric one fails Decimal conversion in mapping.
    wire = _wire_parsed(
        operations=[
            WireOperation(action="buy", target="bonds", amount=WireAmount(value="lots", basis=AmountBasis.ABSOLUTE_CASH))
        ]
    )
    result = _parser(make_response(wire)).parse("buy lots of bonds")
    assert result.ok is False
    assert "malformed" in result.error.lower()


def test_llm_exception_is_parse_failure():
    result = _parser(RuntimeError("503 upstream")).parse("rebalance")
    assert result.ok is False
    assert "LLM call failed" in result.error


# --- request shape + audit capture -------------------------------------------


def test_sends_configured_model_and_schema():
    parser = _parser(make_response(_wire_parsed()))
    parser.parse("do a thing")
    call = parser._client.messages.calls[0]
    assert call["model"] == "claude-sonnet-5"
    assert call["output_format"] is WireParsedIntent
    assert call["system"]  # system prompt present
    assert call["messages"][0]["content"] == "do a thing"


def test_context_is_included_for_followups():
    parser = _parser(make_response(_wire_parsed()))
    parser.parse("actually make it 70/30", context="Proposed: 60% VTI / 40% BND")
    sent = parser._client.messages.calls[0]["messages"][0]["content"]
    assert "70/30" in sent and "60% VTI" in sent


def test_raw_prompt_and_response_captured():
    result = _parser(make_response(_wire_parsed(summary="got it"))).parse("buy bonds")
    assert "buy bonds" in result.raw_prompt
    assert result.raw_response is not None and "got it" in result.raw_response
    assert result.model == "claude-sonnet-5"


def test_result_persists_to_audit_trail(tmp_path):
    from rebalancer.store import AuditStore, create_db_and_tables, make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    create_db_and_tables(engine)
    store = AuditStore(engine)
    session_id = store.create_session()
    conversation_id = store.start_conversation(session_id)
    request_id = store.record_request(conversation_id, "buy bonds")

    result = _parser(make_response(_wire_parsed())).parse("buy bonds")
    store.record_llm_call(
        request_id,
        purpose="parse",
        model=result.model,
        prompt=result.raw_prompt,
        response=result.raw_response or "",
    )

    reread = store.get_request(request_id)
    assert len(reread.llm_calls) == 1
    assert reread.llm_calls[0].purpose == "parse"
    assert reread.llm_calls[0].model == "claude-sonnet-5"
