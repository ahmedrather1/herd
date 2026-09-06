"""Parser-quality eval (H-3, D29) — hits the REAL model; opt-in.

Marked ``eval`` so it is excluded from the fast tier (see pyproject ``addopts``). Run on
demand with a funded Anthropic key present::

    RUN_EVAL=1 uv run pytest -m eval

It is a quality *measurement*, not a commit gate: a failure means a phrasing parsed wrong
and the prompt/schema (or this expectation) needs attention — not that the build is broken.
"""

from __future__ import annotations

import os

import pytest

from eval.golden import GOLDEN_CASES, GoldenCase

pytestmark = pytest.mark.eval

_ENABLED = os.environ.get("RUN_EVAL") == "1"


@pytest.mark.skipif(not _ENABLED, reason="set RUN_EVAL=1 (and provide a real key) to run the eval")
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.id)
def test_golden_case(case: GoldenCase):
    from rebalancer.config import get_settings
    from rebalancer.parsing import IntentParser

    parser = IntentParser.from_settings(get_settings())
    result = parser.parse(case.text)
    assert result.ok, f"parse failed for {case.text!r}: {result.error}"
    case.check(result.parsed)
