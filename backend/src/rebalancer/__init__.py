"""NL Portfolio Rebalancer backend package."""

from __future__ import annotations


def main() -> None:
    """Run the development server (``uv run rebalancer``).

    Validates config before serving so misconfiguration fails fast with a clear
    message instead of a stack trace on the first request (A-1).
    """
    import uvicorn

    from .config import ConfigError, load_settings

    try:
        load_settings()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    uvicorn.run("rebalancer.main:app", host="127.0.0.1", port=8000, reload=True)
