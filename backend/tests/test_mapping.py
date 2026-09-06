"""Mocked-LLM tests for category→symbol resolution (B-3, D29/D51).

The LLM is mocked (FakeAnthropic) and the Alpaca boundary is the H-2 fake (FakeAlpacaClient)
— so these assert the resolution *logic*: literals pass through, sells are holdings-aware,
buys validate tradability, unmappable/untradable terms refuse the whole request (D10), LLM
failure is an error (not a refusal), and Alpaca-unavailable propagates (A-5). Mapping
*quality* is measured by the H-3 eval, not here.
"""

from __future__ import annotations

import pytest

from fakes.fake_alpaca import FakeAlpacaClient
from fakes.fake_anthropic import FakeAnthropic, make_response

from rebalancer.alpaca import AlpacaUnavailableError
from rebalancer.parsing import Intent, Operation, SymbolResolver
from rebalancer.parsing.mapping import WireMappedTarget, WireMapping


def _resolver(alpaca, *responses):
    return SymbolResolver(FakeAnthropic(*responses), alpaca, model="claude-sonnet-5")


def _intent(*operations):
    return Intent(operations=list(operations))


def _mapping(**target_to_symbols):
    return make_response(
        WireMapping(
            mappings=[
                WireMappedTarget(target=t, symbols=list(s), note=f"{t} note")
                for t, s in target_to_symbols.items()
            ]
        )
    )


# --- literals (no LLM call) --------------------------------------------------


def test_literal_symbol_maps_to_itself_without_llm():
    alpaca = FakeAlpacaClient()  # get_asset defaults to tradable
    resolver = _resolver(alpaca)  # no responses queued → LLM must not be called
    result = resolver.resolve(_intent(Operation(action="buy", target="AAPL")))
    assert result.ok
    (m,) = result.mappings
    assert m.symbols == ("AAPL",) and m.source == "literal"
    assert resolver._client.messages.calls == []  # no LLM call for a plain ticker


def test_untradable_literal_refuses():
    alpaca = FakeAlpacaClient()
    alpaca.set_asset("PINK", tradable=False)
    result = _resolver(alpaca).resolve(_intent(Operation(action="buy", target="PINK")))
    assert result.ok is False
    assert "not tradable" in result.refusal


# --- buy/allocation categories → representative symbol -----------------------


def test_buy_category_maps_to_proposed_etf():
    alpaca = FakeAlpacaClient()
    alpaca.set_unknown_asset("TECH")  # "tech" is not a ticker → category
    result = _resolver(alpaca, _mapping(tech=["XLK"])).resolve(
        _intent(Operation(action="buy", target="tech"))
    )
    assert result.ok
    (m,) = result.mappings
    assert m.symbols == ("XLK",) and m.source == "proposed"
    assert m.note == "tech note"


def test_buy_category_unmappable_refuses():
    alpaca = FakeAlpacaClient()
    alpaca.set_unknown_asset("WIDGETS")
    result = _resolver(alpaca, _mapping(widgets=[])).resolve(
        _intent(Operation(action="buy", target="widgets"))
    )
    assert result.ok is False
    assert "couldn't map" in result.refusal.lower()


def test_buy_category_drops_untradable_proposals():
    alpaca = FakeAlpacaClient()
    alpaca.set_unknown_asset("TECH")
    alpaca.set_asset("BADETF", tradable=False)  # model proposed a non-tradable symbol
    result = _resolver(alpaca, _mapping(tech=["BADETF", "XLK"])).resolve(
        _intent(Operation(action="buy", target="tech"))
    )
    assert result.ok
    assert result.mappings[0].symbols == ("XLK",)  # BADETF filtered out


# --- sell/reduce categories → holdings-aware ---------------------------------


def test_sell_category_resolves_to_held_symbols():
    alpaca = FakeAlpacaClient()
    alpaca.set_unknown_asset("TECH")
    for sym in ("AAPL", "MSFT", "KO"):
        alpaca.set_position(sym, qty="10", price="100")
    # Model classifies which holdings are "tech".
    result = _resolver(alpaca, _mapping(tech=["AAPL", "MSFT"])).resolve(
        _intent(Operation(action="sell", target="tech"))
    )
    assert result.ok
    (m,) = result.mappings
    assert set(m.symbols) == {"AAPL", "MSFT"} and m.source == "holdings"


def test_sell_category_ignores_symbols_not_held():
    alpaca = FakeAlpacaClient()
    alpaca.set_unknown_asset("TECH")
    alpaca.set_position("KO", qty="5", price="60")  # only a non-tech holding
    # Even if the model names AAPL, the user doesn't hold it → not sellable → refuse.
    result = _resolver(alpaca, _mapping(tech=["AAPL"])).resolve(
        _intent(Operation(action="sell", target="tech"))
    )
    assert result.ok is False
    assert "don't hold" in result.refusal


# --- failure modes -----------------------------------------------------------


def test_llm_failure_is_error_not_refusal():
    alpaca = FakeAlpacaClient()
    alpaca.set_unknown_asset("TECH")
    result = _resolver(alpaca, RuntimeError("503")).resolve(
        _intent(Operation(action="buy", target="tech"))
    )
    assert result.ok is False
    assert result.refusal is None
    assert "failed" in result.error


def test_alpaca_unavailable_propagates():
    alpaca = FakeAlpacaClient()
    alpaca.set_unavailable(True)
    with pytest.raises(AlpacaUnavailableError):
        _resolver(alpaca).resolve(_intent(Operation(action="buy", target="AAPL")))


# --- mixed + audit capture ---------------------------------------------------


def test_mixed_literal_and_category_single_llm_call():
    alpaca = FakeAlpacaClient()
    alpaca.set_unknown_asset("BONDS")
    resolver = _resolver(alpaca, _mapping(bonds=["BND"]))
    result = resolver.resolve(
        _intent(
            Operation(action="buy", target="VTI"),  # literal
            Operation(action="buy", target="bonds"),  # category
        )
    )
    assert result.ok
    assert {m.target for m in result.mappings} == {"VTI", "bonds"}
    assert len(resolver._client.messages.calls) == 1  # one call for all categories


def test_result_persists_to_audit_trail(tmp_path):
    from rebalancer.store import AuditStore, create_db_and_tables, make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    create_db_and_tables(engine)
    store = AuditStore(engine)
    request_id = store.record_request(
        store.start_conversation(store.create_session()), "buy some bonds"
    )

    alpaca = FakeAlpacaClient()
    alpaca.set_unknown_asset("BONDS")
    result = _resolver(alpaca, _mapping(bonds=["BND"])).resolve(
        _intent(Operation(action="buy", target="bonds"))
    )
    assert result.raw_prompt and result.raw_response
    store.record_llm_call(
        request_id, purpose="category_map", model=result.model,
        prompt=result.raw_prompt, response=result.raw_response,
    )
    assert store.get_request(request_id).llm_calls[0].purpose == "category_map"
