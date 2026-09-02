"""App-boot integration test (A-1): the FastAPI app starts and serves /health."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rebalancer import config
from rebalancer.main import app


@pytest.fixture()
def client(monkeypatch):
    # Provide valid config; env vars take precedence over any backend/.env.
    monkeypatch.setenv("ALPACA_KEY", "pk-test")
    monkeypatch.setenv("ALPACA_SECRET", "secret-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    config.get_settings.cache_clear()
    with TestClient(app) as c:  # triggers lifespan (startup config validation)
        yield c
    config.get_settings.cache_clear()


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_startup_fails_without_config(monkeypatch):
    for key in ("ALPACA_KEY", "ALPACA_SECRET", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        config.Settings, "model_config", {**config.Settings.model_config, "env_file": None}
    )
    config.get_settings.cache_clear()
    # Lifespan startup validates config; missing secrets must abort startup.
    with pytest.raises(Exception):
        with TestClient(app):
            pass
    config.get_settings.cache_clear()
