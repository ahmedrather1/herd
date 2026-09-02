"""Application configuration (A-1, D11).

Loads the three required secrets from a local ``.env`` file (or the real
environment) and validates them at startup. There are **no silent defaults for
secrets** — a missing or blank required key fails fast with a clear message
(A-1 acceptance criterion). Config loading uses ``pydantic-settings`` (D43).

Note on paper-lock (D25/A-2): the Alpaca *base URL* is deliberately NOT a
setting here. v1 must be physically unable to reach a live endpoint, so the
endpoint is pinned in code (A-2), not sourced from config. Only credentials
live in ``.env``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo layout (D41): this file is backend/src/rebalancer/config.py, so the
# backend package root is three parents up. The .env lives at the backend root
# so `uv run` from backend/ finds it by default.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Required runtime configuration for a single local user (D11).

    Fields have no defaults on purpose: if any secret is absent or blank,
    constructing ``Settings`` raises a ``ValidationError`` and the app refuses
    to start (fail-fast, A-1).
    """

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        # Accept ALPACA_KEY / alpaca_key interchangeably.
        case_sensitive=False,
    )

    alpaca_key: str = Field(..., description="Alpaca API key ID (paper account).")
    alpaca_secret: str = Field(..., description="Alpaca API secret key (paper account).")
    anthropic_api_key: str = Field(..., description="Anthropic API key for the Claude parser (D14).")

    @field_validator("alpaca_key", "alpaca_secret", "anthropic_api_key")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        """Treat whitespace-only secrets as missing (no silent defaults)."""
        if v is None or not v.strip():
            raise ValueError(f"{info.field_name} is required and must not be blank")
        return v.strip()


class ConfigError(RuntimeError):
    """Raised with a human-readable message when required config is missing/invalid."""


def load_settings() -> Settings:
    """Load and validate settings, converting pydantic errors into a clear message.

    Raises:
        ConfigError: with a concise, actionable message listing what is missing.
    """
    try:
        return Settings()  # type: ignore[call-arg]  # values come from env/.env
    except Exception as exc:  # pydantic ValidationError or file issues
        missing = _summarize_missing(exc)
        raise ConfigError(
            "Configuration error: could not load required settings.\n"
            f"{missing}\n"
            "Fix: copy .env.example to backend/.env and fill in your paper-account "
            "Alpaca keys and Anthropic API key. See README.md."
        ) from exc


def _summarize_missing(exc: Exception) -> str:
    """Best-effort extraction of which required fields are missing/blank."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        names = []
        for err in exc.errors():  # type: ignore[attr-defined]
            loc = err.get("loc", ())
            if loc:
                names.append(str(loc[0]).upper())
        if names:
            return "Missing or invalid: " + ", ".join(sorted(set(names)))
    return str(exc)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor used by the app and its dependencies."""
    return load_settings()
