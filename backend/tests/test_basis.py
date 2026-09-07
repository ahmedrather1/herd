"""Tests for deterministic basis resolution (B-2, D2/D52).

Pure logic — no LLM, no Alpaca. Covers the three ticket behaviors: the correct basis is
preserved when explicit; a bare/ambiguous percentage defaults to % of source position and
is recorded (never silent); and incoherent readings (out-of-range %, target weights over
100%) route to clarify instead of resolving.
"""

from __future__ import annotations

from decimal import Decimal

from rebalancer.parsing import (
    Amount,
    AmountBasis,
    Intent,
    Operation,
    resolve_basis,
)


def _op(action, target, *, value=None, basis=AmountBasis.PERCENT_SOURCE_POSITION, explicit=True, phrase=""):
    amount = None
    if value is not None or phrase:
        amount = Amount(
            value=Decimal(value) if value is not None else None,
            basis=basis,
            raw_phrase=phrase,
            basis_explicit=explicit,
        )
    return Operation(action=action, target=target, amount=amount)


def _intent(*ops):
    return Intent(operations=list(ops))


# --- explicit bases are preserved --------------------------------------------


def test_explicit_portfolio_percent_preserved():
    result = resolve_basis(_intent(_op("buy", "bonds", value="10", basis=AmountBasis.PERCENT_PORTFOLIO, explicit=True, phrase="10% of my portfolio")))
    assert result.ok
    amt = result.intent.operations[0].amount
    assert amt.basis is AmountBasis.PERCENT_PORTFOLIO
    assert amt.basis_defaulted is False
    assert result.notes == ()


def test_target_weight_preserved():
    result = resolve_basis(
        _intent(
            _op("set_allocation", "stocks", value="60", basis=AmountBasis.TARGET_WEIGHT),
            _op("set_allocation", "bonds", value="40", basis=AmountBasis.TARGET_WEIGHT),
        )
    )
    assert result.ok and result.needs_clarification is None


def test_explicit_source_percent_not_flagged_defaulted():
    result = resolve_basis(
        _intent(_op("sell", "tech", value="50", basis=AmountBasis.PERCENT_SOURCE_POSITION, explicit=True, phrase="half"))
    )
    assert result.ok
    assert result.intent.operations[0].amount.basis_defaulted is False


# --- ambiguity default (D2) --------------------------------------------------


def test_ambiguous_percent_defaults_to_source_and_records_note():
    # A bare "10%" that the parser marked non-explicit, classified as portfolio-ish.
    result = resolve_basis(
        _intent(_op("buy", "tech", value="10", basis=AmountBasis.PERCENT_PORTFOLIO, explicit=False, phrase="10%"))
    )
    assert result.ok
    amt = result.intent.operations[0].amount
    assert amt.basis is AmountBasis.PERCENT_SOURCE_POSITION  # defaulted
    assert amt.basis_defaulted is True
    assert result.notes and "assumed" in result.notes[0]


def test_ambiguous_but_already_source_still_records_assumption():
    result = resolve_basis(
        _intent(_op("sell", "tech", value="25", basis=AmountBasis.PERCENT_SOURCE_POSITION, explicit=False, phrase="a quarter"))
    )
    assert result.ok
    amt = result.intent.operations[0].amount
    assert amt.basis is AmountBasis.PERCENT_SOURCE_POSITION
    assert amt.basis_defaulted is True  # recorded even though basis didn't change


def test_absolute_cash_never_defaulted():
    result = resolve_basis(
        _intent(_op("buy", "VTI", value="5000", basis=AmountBasis.ABSOLUTE_CASH, explicit=False, phrase="$5,000"))
    )
    assert result.ok
    assert result.intent.operations[0].amount.basis is AmountBasis.ABSOLUTE_CASH
    assert result.intent.operations[0].amount.basis_defaulted is False


# --- coherence → clarify -----------------------------------------------------


def test_percent_over_100_routes_to_clarify():
    result = resolve_basis(
        _intent(_op("buy", "bonds", value="150", basis=AmountBasis.PERCENT_PORTFOLIO))
    )
    assert result.ok is False
    assert "out of range" in result.needs_clarification


def test_zero_percent_routes_to_clarify():
    result = resolve_basis(
        _intent(_op("sell", "tech", value="0", basis=AmountBasis.PERCENT_SOURCE_POSITION))
    )
    assert result.ok is False


def test_target_weights_over_100_routes_to_clarify():
    result = resolve_basis(
        _intent(
            _op("set_allocation", "stocks", value="70", basis=AmountBasis.TARGET_WEIGHT),
            _op("set_allocation", "bonds", value="40", basis=AmountBasis.TARGET_WEIGHT),
        )
    )
    assert result.ok is False
    assert "over 100" in result.needs_clarification


def test_target_weights_summing_to_100_ok():
    result = resolve_basis(
        _intent(
            _op("set_allocation", "stocks", value="60", basis=AmountBasis.TARGET_WEIGHT),
            _op("set_allocation", "bonds", value="40", basis=AmountBasis.TARGET_WEIGHT),
        )
    )
    assert result.ok


# --- amount-less operations --------------------------------------------------


def test_operation_without_amount_passes_through():
    result = resolve_basis(_intent(Operation(action="sell", target="everything")))
    assert result.ok
    assert result.intent.operations[0].amount is None
