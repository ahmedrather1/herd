"""Unit tests for config loading (A-1).

Verifies the fail-fast contract: all three secrets required, blanks rejected,
no silent defaults. The .env file is bypassed here by pointing Settings at the
real environment only, so tests are hermetic regardless of any local .env.
"""

from __future__ import annotations

import pytest

from rebalancer.config import ConfigError, Settings, load_settings

REQUIRED = ("ALPACA_KEY", "ALPACA_SECRET", "ANTHROPIC_API_KEY")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Start each test from a known-empty config environment."""
    for key in REQUIRED:
        monkeypatch.delenv(key, raising=False)
    # Ensure Settings reads only the process env, not any developer's backend/.env.
    monkeypatch.setattr(Settings, "model_config", {**Settings.model_config, "env_file": None})


def _set_all(monkeypatch):
    monkeypatch.setenv("ALPACA_KEY", "pk-test")
    monkeypatch.setenv("ALPACA_SECRET", "secret-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")


def test_loads_when_all_present(monkeypatch):
    _set_all(monkeypatch)
    s = load_settings()
    assert s.alpaca_key == "pk-test"
    assert s.alpaca_secret == "secret-test"
    assert s.anthropic_api_key == "sk-ant-test"


@pytest.mark.parametrize("missing", REQUIRED)
def test_fails_fast_on_missing_key(monkeypatch, missing):
    _set_all(monkeypatch)
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert missing in str(exc.value)


@pytest.mark.parametrize("blank", REQUIRED)
def test_blank_secret_is_treated_as_missing(monkeypatch, blank):
    _set_all(monkeypatch)
    monkeypatch.setenv(blank, "   ")  # whitespace-only must not count as configured
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert blank in str(exc.value)


def test_values_are_stripped(monkeypatch):
    monkeypatch.setenv("ALPACA_KEY", "  pk-test  ")
    monkeypatch.setenv("ALPACA_SECRET", "secret-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    s = load_settings()
    assert s.alpaca_key == "pk-test"


def test_error_message_is_actionable(monkeypatch):
    # No keys set at all -> message should name all three and point to README.
    with pytest.raises(ConfigError) as exc:
        load_settings()
    msg = str(exc.value)
    for key in REQUIRED:
        assert key in msg
    assert ".env" in msg
