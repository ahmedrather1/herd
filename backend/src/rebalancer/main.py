"""FastAPI application entrypoint (A-1).

Boots the app and validates configuration on startup (fail-fast, A-1). Feature
endpoints (propose/confirm/execute, audit log) land in later epics (D/E/F/G);
for now this exposes a health check and proves the app + config wiring works.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import router as api_router
from .config import get_settings
from .paperlock import assert_paper_lock
from .store import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast at startup on two invariants:
    #  - paper-lock (A-2/D25): the pinned Alpaca endpoint must be paper, never live;
    #  - config (A-1): required secrets must be present.
    assert_paper_lock()
    get_settings()
    # Local datastore (A-3/D49): create the SQLite file + tables on first run.
    get_engine()
    yield


app = FastAPI(
    title="NL Portfolio Rebalancer",
    version="0.1.0",
    summary="Single-user, paper-locked natural-language portfolio rebalancer (v1).",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe; also confirms config loaded (get_settings would have raised)."""
    get_settings()
    return {"status": "ok"}
