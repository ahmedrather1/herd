"""HTTP API layer (D24): propose/confirm routes wiring the services to FastAPI."""

from __future__ import annotations

from .routes import router

__all__ = ["router"]
