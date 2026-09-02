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

## Layout

```
backend/
  src/rebalancer/
    __init__.py      # `main()` entrypoint (uv run rebalancer)
    config.py        # Settings + fail-fast loading (A-1)
    main.py          # FastAPI app + /health (feature routes land in D/E/F/G)
  tests/
    test_config.py   # config fail-fast contract
    test_app.py      # app boots + serves /health
  pyproject.toml     # deps + pytest config
  .env.example       # template (copy to .env)
```
