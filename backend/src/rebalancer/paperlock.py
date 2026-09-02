"""Hard paper-lock (A-2, D25).

v1 must be *physically unable* to reach a live Alpaca trading endpoint — not merely
default to paper. This module is the single source of truth for the Alpaca trading
base URL and the guard that enforces paper-only access.

Design:
- ``PAPER_TRADING_BASE_URL`` is the one pinned trading endpoint. It is NOT sourced from
  config or env (``config.Settings`` deliberately omits any base-URL field), so there is
  no configuration path that can point the app at a live endpoint.
- ``verify_paper_only(url)`` raises ``PaperLockError`` for anything that is not the paper
  trading host — in particular the live host ``api.alpaca.markets``. The A-4 client
  wrapper must route every trading call through this guard.
- ``assert_paper_lock()`` is a startup self-check (run in the app lifespan) that fails
  fast if the pinned constant were ever changed to a non-paper endpoint.

"Live mode" is intentionally NOT implemented here. It is a separate, deliberately-built
future feature with its own guardrails (D25); there is no paper/live toggle in v1.
"""

from __future__ import annotations

from urllib.parse import urlparse

# The single pinned Alpaca PAPER trading endpoint. Everything that talks to Alpaca for
# trading must use this and only this. Changing it to a live host is caught by
# assert_paper_lock() at startup and by the test suite.
PAPER_TRADING_HOST = "paper-api.alpaca.markets"
PAPER_TRADING_BASE_URL = f"https://{PAPER_TRADING_HOST}"

# Known Alpaca LIVE trading host — explicitly forbidden in v1. Listed so the guard can
# give a precise error and so tests can assert it is unreachable.
LIVE_TRADING_HOST = "api.alpaca.markets"


class PaperLockError(RuntimeError):
    """Raised when code attempts to use a non-paper (e.g. live) Alpaca endpoint."""


def verify_paper_only(url: str) -> str:
    """Return ``url`` unchanged iff it points at the paper trading host; else raise.

    The check is host-based (scheme/port/path-insensitive) so it cannot be fooled by a
    trailing path or an ``http`` vs ``https`` scheme. Any host other than
    ``paper-api.alpaca.markets`` — most importantly the live host — is rejected.

    Raises:
        PaperLockError: if ``url`` is empty, unparseable, or not the paper host.
    """
    host = urlparse(url).hostname if url else None
    if host is None:
        raise PaperLockError(f"Refusing Alpaca endpoint with no host: {url!r}")
    host = host.lower()
    if host == LIVE_TRADING_HOST:
        raise PaperLockError(
            f"Paper-lock (D25): refusing LIVE Alpaca endpoint {url!r}. "
            "v1 is paper-only; live mode is a separate future feature."
        )
    if host != PAPER_TRADING_HOST:
        raise PaperLockError(
            f"Paper-lock (D25): {url!r} is not the pinned paper endpoint "
            f"({PAPER_TRADING_BASE_URL}); refusing."
        )
    return url


def assert_paper_lock() -> None:
    """Startup self-check: the pinned base URL must be the paper endpoint.

    Run in the app lifespan so a build/deploy in which the pinned constant was changed to
    a non-paper endpoint fails fast instead of quietly trading live.

    Raises:
        PaperLockError: if the pinned constant is not the paper trading endpoint.
    """
    verify_paper_only(PAPER_TRADING_BASE_URL)
    if urlparse(PAPER_TRADING_BASE_URL).hostname != PAPER_TRADING_HOST:
        raise PaperLockError(
            "Paper-lock invariant violated: PAPER_TRADING_BASE_URL is not the paper host."
        )
