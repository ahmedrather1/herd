"""Category→symbol mapping eval (B-3/H-3, D5) — real LLM, fake Alpaca; opt-in.

Uses the real model for mapping quality but the H-2 fake for the Alpaca boundary (any
symbol the model proposes validates as tradable), so no live Alpaca is needed. Marked
``eval``; run with ``RUN_EVAL=1 uv run pytest -m eval``. Quality measurement, not a gate.
"""

from __future__ import annotations

import os

import pytest

from fakes.fake_alpaca import FakeAlpacaClient

from rebalancer.parsing import Intent, Operation

pytestmark = pytest.mark.eval

_ENABLED = os.environ.get("RUN_EVAL") == "1"


@pytest.mark.skipif(not _ENABLED, reason="set RUN_EVAL=1 (and provide a real key) to run the eval")
def test_buy_bonds_maps_to_a_tradable_etf():
    from rebalancer.config import get_settings
    from rebalancer.parsing import SymbolResolver

    alpaca = FakeAlpacaClient()
    alpaca.set_unknown_asset("BONDS")  # force the category path
    resolver = SymbolResolver.from_settings(get_settings(), alpaca)

    result = resolver.resolve(Intent(operations=[Operation(action="buy", target="bonds")]))
    assert result.ok, f"expected a mapping, got refusal/error: {result.refusal or result.error}"
    (mapping,) = result.mappings
    assert mapping.source == "proposed"
    assert mapping.symbols  # at least one concrete symbol
    assert all(s.isupper() for s in mapping.symbols)
