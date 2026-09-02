"""Tests for the hard paper-lock (A-2, D25).

These prove the invariant: the pinned endpoint is paper, the live endpoint is refused,
and the startup self-check fails if the pinned constant is ever changed to a live host.
"""

from __future__ import annotations

import pytest

from rebalancer import paperlock
from rebalancer.paperlock import (
    LIVE_TRADING_HOST,
    PAPER_TRADING_BASE_URL,
    PAPER_TRADING_HOST,
    PaperLockError,
    assert_paper_lock,
    verify_paper_only,
)


def test_pinned_url_is_paper():
    assert PAPER_TRADING_BASE_URL == "https://paper-api.alpaca.markets"
    assert PAPER_TRADING_HOST == "paper-api.alpaca.markets"


def test_verify_accepts_paper_endpoint():
    assert verify_paper_only(PAPER_TRADING_BASE_URL) == PAPER_TRADING_BASE_URL
    # Trailing path / order route must still pass (host-based check).
    assert verify_paper_only(f"{PAPER_TRADING_BASE_URL}/v2/orders")


def test_verify_rejects_live_endpoint():
    with pytest.raises(PaperLockError) as exc:
        verify_paper_only(f"https://{LIVE_TRADING_HOST}")
    assert "LIVE" in str(exc.value)


def test_verify_rejects_live_even_with_http_scheme_or_path():
    # Scheme/path tricks must not slip a live host past the guard.
    for url in (
        f"http://{LIVE_TRADING_HOST}",
        f"https://{LIVE_TRADING_HOST}/v2/orders",
        f"https://{LIVE_TRADING_HOST.upper()}",  # case-insensitive host
    ):
        with pytest.raises(PaperLockError):
            verify_paper_only(url)


@pytest.mark.parametrize("bad", ["", "not a url", "https://evil.example.com", "ftp://x"])
def test_verify_rejects_other_or_malformed(bad):
    with pytest.raises(PaperLockError):
        verify_paper_only(bad)


def test_startup_self_check_passes_with_pinned_paper():
    # Should not raise under normal (paper) configuration.
    assert_paper_lock() is None


def test_startup_self_check_fails_if_constant_becomes_live(monkeypatch):
    # Simulate someone repointing the pinned constant at the live host: startup must fail.
    monkeypatch.setattr(paperlock, "PAPER_TRADING_BASE_URL", f"https://{LIVE_TRADING_HOST}")
    with pytest.raises(PaperLockError):
        assert_paper_lock()


def test_no_base_url_field_in_settings():
    """There must be no config path to an endpoint (A-2: not merely a default)."""
    from rebalancer.config import Settings

    field_names = set(Settings.model_fields)
    assert not any("url" in f.lower() or "endpoint" in f.lower() for f in field_names)
