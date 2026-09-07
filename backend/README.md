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

## Persistence (A-3, D49)

Local SQLite datastore (SQLModel) for session/conversation state and the audit trail
(D20/D21). A single file at `backend/data/rebalancer.db` (git-ignored) is **auto-created on
first run** (app lifespan). Set `REBALANCER_DB_URL` to override the location (tests point it
at a temp DB). Money and quantities are stored as **exact TEXT** via `DecimalString` — never
float (D45). The schema is fully normalized; there is **no migration framework** in v1 —
during dev the schema evolves by drop-and-recreate (no precious data yet), and Alembic is
adopted deliberately later. `Intent`/`Proposal` tables are lean first-cuts, expanded by
B-1/D-1; F-1 wires the full end-to-end record.

## Parser (B-1, D50)

Free-form requests become a validated structured **intent** via Claude
(`rebalancer/parsing`). `IntentParser` calls `anthropic` `messages.parse(output_format=…)`;
the result is a discriminated `ParseResult` — `parsed` / `needs_clarification` /
`unsupported`, or `ok=False` for a refusal, empty, malformed, or errored response, which
**never executes** and routes to clarify/retry (D4/D10). Amounts travel as strings on the
wire and become exact `Decimal` in the domain contract (never float, D45). Default model is
`claude-sonnet-5` (override with `ANTHROPIC_MODEL`; the user brings their own key, D13). The
Anthropic client is injected, so unit/integration tests mock the LLM (D29); the semantic
golden-set eval (H-3, `tests/eval/`) hits the real model on demand.

**Basis guardrail (B-2, D52).** `resolve_basis` is deterministic logic (no LLM, no account
state) that makes the parsed reading safe: a percentage the user didn't state the basis of
defaults to *% of source position* (D2), flagged and noted so it's never silent; incoherent
readings (a % over 100, target weights summing past 100%) route to clarify. The dollar/share
math stays in the planner (C-1) on live state (D19).

**Category → symbol (B-3, D51).** `SymbolResolver` turns an intent's raw targets ("tech",
"bonds") into validated tradable symbols: literal tickers pass through; sells are
holdings-aware (only what you currently hold); buys lean to a representative US-listed ETF;
every symbol is checked tradable via the A-4 `get_asset`. An unmappable/untradable term
refuses the whole request (D10). Runs against the real model in the eval:

```bash
RUN_EVAL=1 uv run pytest -m eval      # opt-in; excluded from the fast tier
```

## Layout

```
backend/
  src/rebalancer/
    __init__.py      # `main()` entrypoint (uv run rebalancer)
    config.py        # Settings + fail-fast loading (A-1)
    paperlock.py     # pinned paper endpoint + guard + startup check (A-2/D25)
    store/           # local persistence: SQLite via SQLModel (A-3/D49)
      db.py          #   engine + DecimalString type (Decimal as exact TEXT, D45)
      models.py      #   normalized audit/session tables
      audit.py       #   AuditStore write/read API
    alpaca/          # Alpaca client boundary (A-4)
      client.py      #   AlpacaClient ABC (interface)
      paper_client.py#   PaperAlpacaClient — alpaca-py wrapper, paper-locked (A-4 impl, D47)
      models.py      #   domain types (Decimal money, D45)
      errors.py      #   typed error hierarchy
    parsing/         # NL understanding (Epic B)
      parser.py      #   B-1: IntentParser + wire schema for messages.parse (D50)
      basis.py       #   B-2: resolve_basis — deterministic default/coherence guardrail (D52)
      mapping.py     #   B-3: SymbolResolver — category→symbol, holdings-aware (D51)
      models.py      #   contract (Intent/Operation/Constraint, ParseResult, MappingResult)
    main.py          # FastAPI app + /health (feature routes land in D/E/F/G)
  tests/
    fakes/
      fake_alpaca.py # hand-written scriptable AlpacaClient double (H-2/D37)
    test_config.py   # config fail-fast contract
    test_paperlock.py# paper-lock invariant (accepts paper, refuses live)
    test_alpaca_interface.py  # A-4 interface: implementable, models/errors valid
    test_paper_client.py      # A-4 impl: paper-lock, SDK↔domain mapping, error translation
    test_store.py             # A-3 persistence: graph round-trip, Decimal-as-text, restart
    test_parser.py            # B-1 parser: outcomes, mapping, failure modes (mocked LLM)
    test_basis.py             # B-2 basis guardrail: defaulting + coherence (pure logic)
    test_mapping.py           # B-3 resolver: literals, holdings-aware sells, refuse (mocked LLM)
    eval/                     # H-3 golden set (parser + mapping); marked `eval`, opt-in
    test_fake_alpaca.py       # the fake double's own coverage
    test_app.py      # app boots + serves /health
  pyproject.toml     # deps + pytest config
  .env.example       # template (copy to .env)
```
