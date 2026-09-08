# REQUIREMENTS.md — NL Portfolio Rebalancer

**Living source of truth.** Nothing is "decided" until it is written here. Every
locked decision is dated with a one-line rationale. When implementation surfaces a
new ambiguity, stop and interrogate it (batched questions, push back on vagueness,
make a concrete choice) and record the outcome here immediately — do not leave it
implicit in code or chat.

- Project: natural-language portfolio rebalancer on the Alpaca API.
- Read this file **and** `BACKLOG.md` at the start of every session before touching a ticket.
- Last updated: 2026-09-07 (C-1 planner landed — intent→ordered orders, whole-portfolio rebalance; D53. Prior: B-2/D52, B-3/D51, B-1/D50)

---

## 1. Product shape (locked 2026-09-02)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Core loop = propose → human executes.** Parse NL into a *proposed* set of trades, show them, human clicks confirm to execute. No auto-execute in v1. | Clean separation of parse vs. action; safest given real-money-eventually. |
| D2 | **Percentage basis is resolved per phrasing; default to "% of current source position" when ambiguous, and the chosen reading is shown at confirm.** | Open-ended NL (D6) makes a single fixed interpretation impossible; "make it 60/40", "10% of my portfolio", "sell half my tech" are all different bases. |
| D3 | **Real money is a future goal; guardrails are designed in now.** | Retrofitting confirmation/limits/audit onto a live-trading system is a rewrite. |
| D4 | **Uncertain/possibly-wrong parses: always confirm before acting.** Every request shows a plain-English restatement + the literal orders and requires explicit approval. | Confirm-always is what makes open-ended NL and dynamic symbol mapping safe. |
| D5 | **Asset universe = any Alpaca-tradable US equity/ETF.** Category words ("tech", "bonds") are mapped to symbols by the LLM dynamically; **the mapping is shown to the user at confirm time.** | Max flexibility; the confirm gate (D4) is what keeps dynamic mapping safe. |
| D6 | **NL interface is genuinely open-ended.** User can phrase requests freely; the LLM infers intent. | User choice, knowingly accepting a larger test/failure surface (see §6). |
| D7 | **Conversational: multi-turn follow-ups are supported** ("actually make it 70/30 instead") referencing the prior proposal. | User choice; requires session/context state (D18). |
| D8 | **Constraint-solving is in v1.** Requests may express cash floors, exclusions ("don't sell AAPL"), and "only using new deposits". | User choice, knowingly (see §6). This makes the planner a constraint-solver, not just a parser. |
| D9 | **No extra size-threshold guard.** The always-shown restatement + literal orders is the only confirmation gate, regardless of trade size. | User choice; confirm-always already gates every action. |
| D10 | **Unsatisfiable-but-parseable requests: refuse + explain.** Do not propose partial orders on constraint conflicts or unmappable intent; state what couldn't be satisfied and ask to rephrase/relax. | Consistent with confirm-always safety posture; avoids guessing. |

## 2. Users, auth, keys (locked 2026-09-02)

| # | Decision | Rationale |
|---|----------|-----------|
| D11 | **v1 is single-user local.** User's Alpaca keys in an env file. No accounts, no login. | Smallest surface; multi-user is a separate later project. |
| D12 | **Other people use it via bring-your-own-instance (self-host).** No hosted multi-tenant service; each user runs their own copy with their own keys. | You never custody anyone else's credentials or money. |
| D13 | **Each user brings their own LLM API key.** | No token cost or abuse exposure to the project owner. |
| D14 | **LLM provider = Anthropic (Claude).** Users supply an Anthropic API key. | Single provider keeps parsing/validation logic focused. |

## 3. Reliability & correctness (locked 2026-09-02)

| # | Decision | Rationale |
|---|----------|-----------|
| D15 | **Partial-failure = sequential, stop on first failure.** Place one order at a time; order legs **sells-first, buys-second** so a stop leaves the account in **cash** rather than over-concentrated. Report "completed N of M, $X left in cash." No unwinding. | Cash is the safe failure state; true atomic unwind is impossible as prices move. |
| D16 | **Success = orders accepted by Alpaca.** Report acceptance, not fill. Final allocation may drift from target; that is acknowledged. | Fills are async and may never complete; accepting is the honest known state. |
| D17 | **Market closed → propose, warn, hold.** Show proposed orders with a market-closed warning; do not submit until the user confirms. No silently-queued trades. | No surprise unattended execution. |
| D18 | **Orders that violate Alpaca rules (buying power, fractional/qty) → reject with reason.** Propose nothing invalid; user adjusts the request. | Cleaner than letting Alpaca reject and dealing with messy partial states. |
| D19 | **Confirm-time re-validation.** On confirm, re-fetch positions/prices and re-check validity; if materially changed, re-show the proposal before submitting. | Prices/positions drift between propose and confirm. |

## 4. Data, logging, disputes (locked 2026-09-02)

| # | Decision | Rationale |
|---|----------|-----------|
| D20 | **Full audit trail per request:** raw request text, interpreted intent, proposed orders, submitted orders, Alpaca responses, timestamps. | Needed for debugging and dispute reconstruction. |
| D21 | **Store the LLM prompt + raw response** alongside each request. | Best debuggability for misparses; data-at-rest risk is bounded by BYO-instance (D12). |
| D22 | **Disputes: viewable audit log in v1; "undo last rebalance" deferred to later.** | Diagnosis first; automated reversal is non-trivial and imperfect — worth it only once real money lands. |
| D23 | **Session/context state is persisted locally** (e.g. SQLite) so it survives restarts and feeds the audit trail. | Supports conversational follow-ups (D7) and the audit trail (D20). |

## 5. Interface & guardrails (locked 2026-09-02)

| # | Decision | Rationale |
|---|----------|-----------|
| D24 | **v1 interface = minimal local web UI.** Type request → see restatement + proposed orders + current-vs-target → click confirm. | Matches the eventual frontend goal; usable on its own. |
| D25 | **Hard paper-lock in v1.** v1 targets Alpaca **paper endpoints only**; live trading is physically unreachable until a deliberately-built "live mode" with its own guardrails is added later. | "Real money eventually" must be impossible-by-accident now. |
| D44 | **Paper-lock is scoped to the trading endpoint** (A-2). The pinned constant + `verify_paper_only` guard (`rebalancer/paperlock.py`) enforce the single paper **trading** host (`paper-api.alpaca.markets`) and refuse the live host (`api.alpaca.markets`). The read-only **market-data** host (`data.alpaca.markets`, prices/quotes) is a separate concern handled in A-4 — it cannot place orders, so it does not weaken the lock; A-4 still routes it through pinned constants (no env/config URL). There is no paper/live toggle. | Precisely defines the invariant so A-4 doesn't treat read-only data as a lock violation, nor open a config path to a live endpoint. |

## 6. Tech stack (locked 2026-09-02)

| # | Decision | Rationale |
|---|----------|-----------|
| D26 | **Backend = Python.** | First-party Alpaca + Anthropic SDKs; strong fit for parsing/planning logic and pytest ecosystem. |
| D27 | **Frontend = React SPA** talking to the backend API. | Flexible path toward the eventual real frontend (D24). |
| D28 | **Stack governance: approve each major library.** Claude proposes any significant dependency and waits for the user's explicit yes before it is adopted; the approved choice is then recorded here. | User wants control over lock-in/architecture choices. |
| D41 | **Repo layout = `backend/` + `frontend/`.** Top-level `backend/` holds the FastAPI app, `pyproject.toml`, and Python tests; top-level `frontend/` holds the Vite React app. Each keeps its own tooling; no root-level mixing of Python and JS tooling. | Cleanest separation for the Python+React split (D26/D27); each side reproducible on its own. |
| D42 | **Python env/deps = uv** (`pyproject.toml` + `uv.lock`). All Python commands run via `uv` (`uv sync`, `uv run …`); the lockfile pins exact versions for reproducible CI (H-1) and safety-sensitive test runs (D32). | Real lockfile (vs. loose `requirements.txt`) matters for a real-money-eventually system; fast, standards-based, less venv-activate ceremony. Tooling choice surfaced for approval per D28 spirit. |

### Approved libraries (locked 2026-09-02 per D28)

| # | Choice | Role | Notes |
|---|--------|------|-------|
| D33 | **FastAPI** (+ Uvicorn) | Backend web/API framework | Async, typed, Pydantic validation; serves the React SPA over JSON. |
| D34 | **SQLModel** | SQLite data-access (D23) | SQLAlchemy + Pydantic; models double as API schemas. |
| D35 | **pytest** (+ `pytest-asyncio`) | Python test runner | Unit + integration; async support for FastAPI. |
| D36 | **alpaca-py** (official SDK) | Alpaca client (A-4) | Wrapped thinly; **paper-lock (D25) enforced in the wrapper**. Tests mock at the wrapper boundary, not HTTP. |
| D37 | **Hand-written fake wrapper double** | Alpaca mocking (H-2) | No extra dependency. Scriptable positions/prices/clock/buying-power + per-order accept/reject/fail for stop-on-failure (D15) and Alpaca-down (A-5). Supersedes the earlier respx/vcrpy idea. |
| D38 | **Playwright (Python)** | Full-stack e2e (D31, H-4) | Drives the real React UI against the paper account, in the Python test suite. |
| D39 | **Vite** | React build tool / dev server | Frontend-only; no backend overlap with FastAPI (Next.js was rejected for running a second server). |
| D40 | **Vitest + React Testing Library** | React component/unit tests | Vite-native runner; user-centric component tests for UI paths e2e doesn't cover. |
| D43 | **pydantic-settings** | Env/config loading (A-1) | Official Pydantic companion; reads `.env` + real env vars, validates required secrets, fails fast (no silent defaults per A-1). Approved 2026-09-02 per D28. |
| D53 | **C-1 planner (`planning/planner.py`) = resolved intent + B-3 mappings + live state → ordered order set.** (Chosen 2026-09-07.) **Order sizing:** dollar-denominated buys and target adjustments use **notional**; position-relative sells (`percent_source_position`, whole-position, share counts) use **qty** taken exactly from holdings (no price/rounding drift). **Whole-portfolio rebalance:** `set_allocation` `target_weight` ops that sum to ~100% liquidate unmentioned holdings (sell full qty) and adjust target symbols to `weight%×equity`; a partial set ("set bonds to 10%") adjusts only that category. **Semantics by (action, basis):** TARGET_WEIGHT/PERCENT_PORTFOLIO → target (delta to `pct×equity`, split across the op's symbols); PERCENT_SOURCE_POSITION → delta vs current position (sell qty = `pct×held_qty` per symbol); ABSOLUTE_CASH → notional delta (buys split equally, sells proportional to holdings); SHARES → qty; no amount + sell → liquidate the mapped holdings. Orders are **sells-first, buys-second** (D15). Money/qty rounded **down** (never oversell/overspend); sub-cent deltas skipped. **C-1 does not validate** (buying-power / fractional / minimums are D-2) **or apply constraints** (C-2). Needs only `get_account` (equity) + `get_positions` from A-4 — notional avoids a price fetch. Alpaca-unavailable propagates (A-5). Deterministic → integration-tested against the H-2 fake, no LLM. | Q1/Q2 chosen 2026-09-07: notional/qty split gives best precision; whole-portfolio rebalance is what "60/40" actually means (confirm gate + C-2 exclusions keep it safe). Keeps sizing separate from validation (D-2) and constraints (C-2). |
| D52 | **B-2 = deterministic basis-normalization / guardrail layer** (`parsing/basis.py`), pure logic over the parsed intent — no LLM, no account state, no dollar math. (Chosen 2026-09-06.) Re-validation found B-1's LLM already classifies the basis, and D19 wants dollar/share math on *live* state (C-1), so B-2's remaining value is a deterministic guardrail: (a) **ambiguity default (D2)** — a percentage the user didn't state the basis of (`basis_explicit=False`) resolves to `PERCENT_SOURCE_POSITION`, flagged `basis_defaulted` and noted so it's never silent; (b) **coherence validation** — percentages in (0,100], `set_allocation` target weights not summing over 100% — incoherent readings route to clarify; (c) records resolved basis + human-readable notes for confirm (D4). **Dollar/share resolution stays in C-1** on fresh state (D19). Required a small B-1 schema extension: `basis_explicit` on `Amount`. Pure unit tests, no mocks (D29 not needed — deterministic). | Avoids duplicating B-1's classification and C-1's account math; adds a deterministic safety net over non-deterministic LLM output, which is exactly where a real-money system wants determinism. |
| D51 | **B-3 category→symbol mapping = `SymbolResolver`** (LLM + A-4 `get_asset`). (Chosen 2026-09-06.) Per operation target: a literal tradable ticker maps to itself; a **category word** is resolved by one `messages.parse` call and every proposed symbol is validated tradable via `get_asset`. **Sell/reduce categories are holdings-aware** — resolved only to the user's current positions that fit the category (you can only sell what you hold; nothing held → refuse). **Buy/allocation categories lean to a single representative US-listed ETF** (the LLM proposes; shown at confirm, D4/D5). Any unmappable or untradable term **refuses the whole request with an explanation (D10 — no partial mapping)**. Alpaca-unavailable propagates (A-5), not a refusal. Mapping + raw prompt/response captured for confirm/audit (D5/D20/D21); LLM injected → mocked in tests (D29), quality measured in H-3. | Holdings-aware sells are a correctness requirement, not UX; representative-ETF buys keep the mapping predictable and easy to confirm; refuse-whole matches D10's no-partial posture. |
| D50 | **anthropic** (official SDK) | Claude parser (B-1, D14) | Approved 2026-09-06 per D28. NL→intent via `client.messages.parse(output_format=<Pydantic>)` → validated `parsed_output`; malformed/refused output surfaces as a parse failure (B-1). **Default model `claude-sonnet-5`, configurable via env `ANTHROPIC_MODEL`** (user brings own key, D13 — their token cost; bump to Opus per-request if a phrasing misparses). Parser takes an injected client so unit/integration tests **mock the LLM** (D29); the semantic golden-set eval (H-3) hits the real model on demand. |
| D45 | **Money & quantities are `Decimal`, never `float`.** All cash, prices, share quantities, notional amounts across the Alpaca boundary, planner, and audit trail use `Decimal`. | Binary floats can't represent decimal cash/share values exactly; unacceptable on a real-money-eventually system. Cross-cutting through A-4/C/D/E. |
| D46 | **Alpaca client boundary is synchronous;** FastAPI offloads calls to a threadpool. The `AlpacaClient` interface (A-4) exposes sync methods. | alpaca-py SDK is synchronous; a sync wrapper keeps the fake double (H-2) and tests simple, with no async coloring through the planner. |
| D49 | **A-3 persistence = SQLModel + SQLite (D23/D34), fully normalized, no migration framework in v1.** (Chosen 2026-09-05.) The audit/session graph is modeled with real typed columns — `AppSession → Conversation → Request → {LlmCall, Intent, Proposal → ProposedOrder, OrderExecution}` — no JSON-blob dodge for structured data. Genuinely-freeform *external* payloads are TEXT columns: LLM prompt/response (D21) and raw Alpaca responses (D20). **Money/quantities are stored as TEXT via a `DecimalString` SQLAlchemy type** so models expose `Decimal` while the DB keeps exact strings (preserves D45 — SQLite has no decimal type; never float). **No Alembic/migrations in v1** (upholds the D23 non-goal): there is no precious data during early dev and the intent/proposal shapes churn through B/D, so dev schema changes are **drop-and-recreate**; adopt Alembic deliberately later, when data becomes worth preserving. The DB is a single SQLite file auto-created on first run at `backend/data/rebalancer.db`; the engine factory accepts a URL so tests use a temp/in-memory DB. **Scope split with F-1:** A-3 delivers the engine + `DecimalString` + normalized tables + an `AuditStore` write/read API; F-1 populates the full record end-to-end as features land. `Intent`/`Proposal` are lean first-cuts here, expanded by B-1/D-1 (which define those shapes) via recreate. | User pushed back on JSON blobs (2026-09-05): model it properly; skip migration ceremony while data is worthless and shapes churn; recreate now, migrate later. |
| D48 | **A-5 (Alpaca-unavailable handling) is not a standalone ticket built now; its behavior is realized inside the epics that own each surface.** Re-validation (2026-09-03) found all three A-5 criteria depend on surfaces that don't exist yet: the propose/validate "can't reach Alpaca, try again" state lands with Epic D; mid-execution stop-on-failure (D15) lands with Epic E (E-1); audit-trail recording lands with A-3/F-1. The building blocks already exist (`AlpacaUnavailableError` from A-4; the fake's `set_unavailable`/`fail_after` from H-2), but there is no caller to wire them into. A-5 stays as a tracking/acceptance checklist verified as D/E/F land, not a block of speculative code written ahead of its callers. | Avoids speculative code with no caller; keeps the unavailable-behavior contract honest by testing it where it actually runs. |
| D47 | **A-4 impl = `PaperAlpacaClient` (`alpaca/paper_client.py`) wrapping alpaca-py.** Specifics: (a) trading client is always built `paper=True` and, belt-and-suspenders, its resolved SDK base URL is run through `verify_paper_only` at construction — construction fails fast if it isn't the pinned paper host (strengthens D25/D44). (b) Read-only prices use the **latest trade** (`get_stock_latest_trade`) on the separate data host; a requested symbol absent from the response raises `AlpacaRequestError`. (c) **Error mapping:** SDK `APIError` with status ≥ 500 or no status, and any transport (`requests`) error → `AlpacaUnavailableError`; 4xx → `AlpacaRequestError` (`OrderRejectedError` w/ symbol for order submit). (d) Amounts handed to the SDK are passed as **decimal strings** so we never construct a float (D45); the SDK's internal float is its own boundary. (e) `get_alpaca_client()` is a cached process-wide provider (SDK construction does no network I/O). | Makes the client real for C/D/E while keeping the paper-lock unreachable-by-construction and the app free of SDK shapes. |

No further libraries are approved. Any new dependency must be proposed and approved (D28)
before adoption and added to this table.

## 7. Testing strategy (locked 2026-09-02)

| # | Decision | Rationale |
|---|----------|-----------|
| D29 | **Parser (non-deterministic) is tested two ways:** (a) unit/integration tests **mock the LLM** to verify plumbing deterministically in CI; (b) a **separate golden-set eval suite** uses **semantic checks, not exact-match**, to measure real parse quality, run on demand (not every commit). | `parse(x) == y` is unreliable for open-ended NL (D6); plumbing correctness and model quality are different questions. |
| D30 | **Alpaca in tests:** integration tests use a **hand-written fake wrapper double** (D37) around the A-4 boundary (fast, deterministic); a **small e2e suite hits the real Alpaca paper sandbox** to prove the wiring. | Balances speed/determinism against proving the real integration works. Paper-locked (D25). |
| D31 | **E2E = full stack via browser.** Playwright drives the React UI through request → proposal → confirm → result against the paper account. | Highest confidence on the whole confirm/execute loop, the riskiest surface. |
| D32 | **Testing is enforced in each ticket's acceptance criteria.** A ticket is not "done" until its required tests (at the appropriate levels) are green. Testing is inline, never deferred to later tickets. | Prevents tests from lagging behind features on a safety-sensitive, real-money-eventually system. |

**Test-level guidance derived from the above:**
- *Unit:* pure logic — %-basis resolution (D2/B-2), order construction & sells-first/buys-second ordering (D15/C-1), constraint-solving (D8/C-2), validation rules (D18/D-2). LLM and Alpaca mocked.
- *Integration:* module seams — parser→planner→proposal→validation, and execution against a **mocked** Alpaca client, incl. stop-on-failure/land-in-cash (D15) and confirm-time re-validation (D19).
- *Eval (parser quality):* golden set of phrasings → expected structured intent, graded semantically; covers %-basis variants (D2), category→symbol mapping (D5), constraints (D8), and refuse+explain cases (D10).
- *E2E:* Playwright, full loop against the paper sandbox, incl. market-closed warn-and-hold (D17) and reject-with-reason (D18) paths where reproducible.

## 8. Known-large scope, accepted knowingly (2026-09-02)

The user was pushed back on and **knowingly accepted** a large v1: open-ended NL (D6)
+ conversational state (D7) + constraint-solving (D8), on top of any-tradable-asset
(D5). These are the four hardest dimensions at once. The confirm-always gate (D4)
keeps this *safe* but not *small*. Expect the parser + planner to be the bulk of the
engineering. This note exists so a future session does not "simplify" these away
without an explicit decision recorded here.

## 9. Open questions / to interrogate when they surface

- None currently blocking. Add here (dated) whenever implementation reveals a case
  the spec didn't cover, then interrogate before coding past it.
