"""Full-stack e2e smoke (H-4/D31) — Playwright drives the real React UI against paper.

Opt-in and out of the fast tier (marked ``e2e``; excluded by pyproject ``addopts``). It
needs the whole stack live: the backend on :8000 (real paper Alpaca + Anthropic keys) and
the frontend served (``E2E_BASE_URL``, default the Vite dev server), plus a Playwright
browser. Run::

    cd frontend && npm run dev &                 # or: npm run build && npm run preview
    cd backend && uv run rebalancer &
    uv run --group e2e playwright install chromium
    RUN_E2E=1 uv run --group e2e pytest -m e2e

Paper-only (D25) — never a live account (H-4 non-goal). This is a smoke test of the loop,
not a substitute for the unit/integration suite.

NOTE: this scaffold has not been executed in the build environment (no live stack/keys
there); it encodes the known Playwright-Python pattern and the app's real selectors.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.e2e

_ENABLED = os.environ.get("RUN_E2E") == "1"
BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:5173")

# A request that resolves regardless of the paper account's exact holdings: a small buy of a
# broad category. Reproducible-state hooks (known positions) aren't safe to auto-apply
# against a shared paper account, so we lean on a request that works from any starting state.
SMOKE_REQUEST = "put 5% of my portfolio in bonds"


@pytest.mark.skipif(not _ENABLED, reason="set RUN_E2E=1 with the backend + frontend running")
def test_happy_path_loop(page):
    page.goto(BASE_URL)

    page.get_by_label("request").fill(SMOKE_REQUEST)
    page.get_by_role("button", name="Propose").click()

    # Parse + map + plan + validate round-trips through the real LLM and paper Alpaca.
    page.get_by_text("Proposed").wait_for(timeout=30_000)

    page.get_by_role("button", name="Confirm & place orders").click()

    # A result panel means we left the proposal and reached an end state of the loop —
    # completed, or a held/blocked state (e.g. market closed), both valid outcomes.
    page.locator(".panel.result").wait_for(timeout=30_000)
