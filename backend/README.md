# Backend — NL Portfolio Rebalancer

Python + FastAPI backend, managed with **uv** (D42). See the repo-root
[`README.md`](../README.md) for the product overview and
[`REQUIREMENTS.md`](../REQUIREMENTS.md) for the numbered decisions referenced below.

## Quick start

```bash
cp .env.example .env    # fill in paper Alpaca keys + Anthropic key (git-ignored)
uv sync                 # install locked deps into .venv
uv run rebalancer       # dev server at http://127.0.0.1:8000  (/health, /docs)
uv run pytest           # test suite
```

`uv run <cmd>` runs inside the project's environment — no manual venv activation.

## Configuration (A-1)

Three secrets are required and validated at startup by `rebalancer.config`
(via `pydantic-settings`, D43). Missing or blank values fail fast with an actionable
message; there are **no silent defaults for secrets**. Values come from `backend/.env`
or the real environment (env vars win, useful in CI).

The Alpaca **base URL is intentionally not configurable** — it is pinned in code to the
paper endpoint (A-2 paper-lock, D25). Only credentials live in `.env`.

## Paper-lock (A-2, D25) — invariant

v1 is **physically unable** to reach a live Alpaca trading endpoint, not merely defaulted
to paper. Enforced in `rebalancer/paperlock.py`:

- `PAPER_TRADING_BASE_URL` is the single pinned trading endpoint (`paper-api.alpaca.markets`).
  It is not read from config/env, so no configuration path reaches a live endpoint.
- `verify_paper_only(url)` refuses any non-paper host (esp. live `api.alpaca.markets`);
  the A-4 client must route trading calls through it.
- `assert_paper_lock()` runs at startup (app lifespan and `uv run rebalancer`) and **fails
  fast** if the pinned constant were ever changed to a non-paper endpoint.

There is **no paper/live toggle**. "Live mode" is a separate, deliberately-built future
feature with its own guardrails — it does not exist in v1. The read-only market-data host
(prices/quotes) is a distinct concern handled in A-4 and cannot place orders (D44).

## Layout

```
backend/
  src/rebalancer/
    __init__.py      # `main()` entrypoint (uv run rebalancer)
    config.py        # Settings + fail-fast loading (A-1)
    paperlock.py     # pinned paper endpoint + guard + startup check (A-2/D25)
    main.py          # FastAPI app + /health (feature routes land in D/E/F/G)
  tests/
    test_config.py   # config fail-fast contract
    test_paperlock.py# paper-lock invariant (accepts paper, refuses live)
    test_app.py      # app boots + serves /health
  pyproject.toml     # deps + pytest config
  .env.example       # template (copy to .env)
```
