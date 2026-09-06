"""Parser golden set (H-3, D29) — seed cases, grown by B-2/B-3.

Curated phrasings paired with **semantic** expectations, not exact-match: open-ended NL
(D6) makes ``parse(x) == y`` unreliable, so each case asserts the *reading* is right
(status, an operation's action/basis, a constraint) while tolerating wording differences.
This measures parse quality against the real model; it is not a commit gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from rebalancer.parsing import AmountBasis, ParsedIntent, ParseStatus


@dataclass(frozen=True)
class GoldenCase:
    id: str
    text: str
    check: Callable[[ParsedIntent], None]


def _op_targeting(parsed: ParsedIntent, needle: str):
    assert parsed.intent is not None, "expected an intent"
    matches = [op for op in parsed.intent.operations if needle.lower() in op.target.lower()]
    assert matches, f"no operation targeting {needle!r} in {[o.target for o in parsed.intent.operations]}"
    return matches[0]


def _constraint_of_kind(parsed: ParsedIntent, kind: str):
    assert parsed.intent is not None
    matches = [c for c in parsed.intent.constraints if c.kind == kind]
    assert matches, f"no {kind} constraint in {[c.kind for c in parsed.intent.constraints]}"
    return matches[0]


def _percent_portfolio_to_bonds(parsed: ParsedIntent) -> None:
    assert parsed.status is ParseStatus.PARSED
    op = _op_targeting(parsed, "bond")
    assert op.amount is not None and op.amount.basis is AmountBasis.PERCENT_PORTFOLIO
    assert op.amount.value == Decimal("10")


def _sell_half_tech(parsed: ParsedIntent) -> None:
    assert parsed.status is ParseStatus.PARSED
    op = _op_targeting(parsed, "tech")
    assert op.action == "sell"
    assert op.amount is not None and op.amount.basis is AmountBasis.PERCENT_SOURCE_POSITION


def _sixty_forty(parsed: ParsedIntent) -> None:
    # Either a confident set_allocation, or a request to clarify — both are acceptable.
    assert parsed.status in (ParseStatus.PARSED, ParseStatus.NEEDS_CLARIFICATION)


def _cash_floor(parsed: ParsedIntent) -> None:
    assert parsed.status is ParseStatus.PARSED
    c = _constraint_of_kind(parsed, "cash_floor")
    assert c.value == Decimal("5000")


def _crypto_unsupported(parsed: ParsedIntent) -> None:
    assert parsed.status is ParseStatus.UNSUPPORTED


def _exclude_aapl(parsed: ParsedIntent) -> None:
    assert parsed.status is ParseStatus.PARSED
    c = _constraint_of_kind(parsed, "exclude_asset")
    assert c.target is not None and "AAPL" in c.target.upper()


GOLDEN_CASES: list[GoldenCase] = [
    GoldenCase("pct_portfolio_bonds", "put 10% of my portfolio into bonds", _percent_portfolio_to_bonds),
    GoldenCase("sell_half_tech", "sell half of my tech holdings", _sell_half_tech),
    GoldenCase("sixty_forty", "make it 60/40 stocks and bonds", _sixty_forty),
    GoldenCase("cash_floor", "rebalance to equal weight but keep at least $5,000 in cash", _cash_floor),
    GoldenCase("crypto", "put half my cash into bitcoin", _crypto_unsupported),
    GoldenCase("exclude_aapl", "rebalance everything to equal weight but don't sell my AAPL", _exclude_aapl),
]
