# NL Portfolio Rebalancer

Natural-language portfolio rebalancer on the Alpaca API. You type a request in plain
English ("make it 60/40 stocks/bonds", "sell half my tech"); the app parses it with
Claude, proposes concrete trades, and executes them **only after you confirm**.

> **v1 is single-user, self-hosted, and hard paper-locked.** You run your own copy with
> your own keys (D11, D12). v1 can only ever reach Alpaca's **paper** endpoints — live
> trading is a separate, deliberately-built future feature (D25). This is not a hosted
> service and never custodies anyone else's credentials or money.

See [`REQUIREMENTS.md`](REQUIREMENTS.md) (numbered, dated source of truth) and
[`BACKLOG.md`](BACKLOG.md) (epics/tickets) for the full design.

## Repository layout (D41)

```
herd/
  backend/     # Python + FastAPI app, managed with uv (D42, D33)
  frontend/    # React (Vite) SPA — added in Epic G
  REQUIREMENTS.md
  BACKLOG.md
```

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** for Python env/deps (D42): `brew install uv`
- **Node 20+** (only once the frontend lands in Epic G)
- An **Alpaca paper** account (key + secret) and an **Anthropic API key** — each user
  brings their own (D13).

## Setup (backend)

```bash
cd backend
cp .env.example .env          # then edit .env with your real keys (never committed)
uv sync                       # create the venv and install locked deps
uv run rebalancer             # start the dev server at http://127.0.0.1:8000
```

If any required secret is missing or blank, the app **refuses to start** with a clear
message — there are no silent defaults for secrets (A-1). Health check once running:

```bash
curl http://127.0.0.1:8000/health   # -> {"status":"ok"}
```

Required `.env` keys (paper credentials only — see [`backend/.env.example`](backend/.env.example)):

| Key | Purpose |
|-----|---------|
| `ALPACA_KEY` | Alpaca **paper** API key ID |
| `ALPACA_SECRET` | Alpaca **paper** API secret |
| `ANTHROPIC_API_KEY` | Anthropic API key for the Claude parser (D14) |

## Setup (frontend, Epic G)

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api → the backend on :8000)
```

Run the backend too, then open the dev URL: type a request → **Propose** → review the
proposal → **Confirm & place orders**. See [`frontend/README.md`](frontend/README.md).

## Tests

```bash
cd backend
uv run pytest        # unit + integration (mocked externals) — the fast tier
```

Eval (parser quality, real Claude) and e2e (Playwright against paper) run in their own
tiers and land in later tickets (H-3, H-4).
