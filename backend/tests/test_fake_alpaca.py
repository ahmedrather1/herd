"""Tests for the fake Alpaca double itself (H-2).

The double is test infrastructure, so it gets its own coverage: state scripting, the
market clock, per-order accept/reject, mid-sequence failure (stop-on-failure, D15), and
the global Alpaca-down switch (A-5). It also confirms it honors the A-4 contract.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fakes.fake_alpaca import ACCEPT, FakeAlpacaClient, Fail, Reject
from rebalancer.alpaca import (
    AlpacaUnavailableError,
    AlpacaClient,
    OrderRejectedError,
    OrderRequest,
    OrderSide,
)
from rebalancer.alpaca.errors import AlpacaRequestError


def _buy(symbol="AAPL", qty="1"):
    return OrderRequest(symbol=symbol, side=OrderSide.BUY, qty=Decimal(qty))


def test_is_an_alpaca_client():
    assert isinstance(FakeAlpacaClient(), AlpacaClient)


def test_scripts_account_positions_prices_clock():
    c = FakeAlpacaClient(cash="1000", buying_power="1000", equity="2500", is_open=False)
    c.set_position("AAPL", qty="10", price="150")
    c.set_price("BND", "72.50")

    assert c.get_account().cash == Decimal("1000")
    pos = c.get_positions()
    assert pos[0].symbol == "AAPL" and pos[0].market_value == Decimal("1500")
    prices = c.get_latest_prices(["AAPL", "BND"])
    assert prices["BND"].price == Decimal("72.50")
    assert c.get_clock().is_open is False


def test_missing_price_raises():
    c = FakeAlpacaClient()
    with pytest.raises(AlpacaRequestError):
        c.get_latest_prices(["NOPE"])


def test_asset_tradability_and_unknown():
    c = FakeAlpacaClient()
    assert c.get_asset("AAPL").tradable is True  # default tradable
    c.set_asset("PINK", tradable=False, fractionable=False)
    assert c.get_asset("PINK").tradable is False
    c.set_unknown_asset("ZZZZ")
    with pytest.raises(AlpacaRequestError):
        c.get_asset("ZZZZ")


def test_orders_accepted_by_default_and_recorded():
    c = FakeAlpacaClient()
    out = c.submit_order(_buy())
    assert out.status == "accepted" and out.id == "fake-1"
    assert len(c.submitted) == 1
    assert c.get_order("fake-1").symbol == "AAPL"


def test_scripted_reject_raises_with_reason():
    c = FakeAlpacaClient()
    c.queue_outcomes(Reject("insufficient buying power", symbol="AAPL"))
    with pytest.raises(OrderRejectedError) as exc:
        c.submit_order(_buy())
    assert exc.value.symbol == "AAPL"
    assert "buying power" in str(exc.value)
    assert c.submitted == []  # rejected order not recorded as submitted
    assert len(c.attempts) == 1  # but the attempt is observed


def test_mid_sequence_failure_stops_after_n_accepts():
    # sells-first/buys-second sequence; the 3rd submission fails (D15).
    c = FakeAlpacaClient()
    c.fail_after(2, reason="Alpaca 503")

    orders = [_buy(symbol=s) for s in ("SELL1", "SELL2", "BUY1", "BUY2")]
    accepted = []
    with pytest.raises(AlpacaUnavailableError):
        for o in orders:
            accepted.append(c.submit_order(o))

    # First two accepted; the third halted the sequence; nothing after ran.
    assert [s.symbol for s in accepted] == ["SELL1", "SELL2"]
    assert [s.symbol for s in c.submitted] == ["SELL1", "SELL2"]
    assert len(c.attempts) == 3  # 4th order never attempted


def test_explicit_outcome_sequence():
    c = FakeAlpacaClient()
    c.queue_outcomes(ACCEPT, Reject("bad qty"), ACCEPT)
    assert c.submit_order(_buy()).status == "accepted"
    with pytest.raises(OrderRejectedError):
        c.submit_order(_buy())
    assert c.submit_order(_buy()).status == "accepted"
    assert len(c.submitted) == 2


def test_alpaca_down_switch_affects_all_calls():
    c = FakeAlpacaClient(cash="100")
    c.set_unavailable(True)
    for call in (c.get_account, c.get_positions, c.get_clock):
        with pytest.raises(AlpacaUnavailableError):
            call()
    with pytest.raises(AlpacaUnavailableError):
        c.submit_order(_buy())
    # Recovers when the switch is cleared.
    c.set_unavailable(False)
    assert c.get_account().cash == Decimal("100")
