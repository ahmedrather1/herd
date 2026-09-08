# BACKLOG.md — NL Portfolio Rebalancer

> **How to use this file across sessions.** Read `REQUIREMENTS.md` first, then this
> file. Each ticket is written to be picked up independently. Before starting a
> ticket, check its assumptions against the current `REQUIREMENTS.md` — if a later
> decision has made a ticket's acceptance criteria shaky or inconsistent, **flag it
> and re-question before coding**, don't assume an old ticket is still correct.
> Decision IDs (D1–D25) refer to `REQUIREMENTS.md`.

---

## Requirements summary (mirror of REQUIREMENTS.md as of 2026-09-02)

- **Core loop:** propose → human executes; no auto-execute (D1).
- **% basis:** resolved per phrasing; default "% of current source position" when ambiguous; chosen reading shown at confirm (D2).
- **Real money:** future goal, guardrails designed in now (D3); **v1 is hard paper-locked** (D25).
- **Bad/uncertain parse:** always confirm before acting (D4); unsatisfiable requests refuse + explain (D10).
- **Assets:** any Alpaca-tradable US equity/ETF; LLM maps category words → symbols, mapping shown at confirm (D5).
- **NL:** genuinely open-ended (D6). **Conversational** multi-turn follow-ups (D7). **Constraint-solving** in scope: cash floors, exclusions, only-new-deposits (D8). No extra size-threshold guard (D9).
- **Users:** single-user local, Alpaca keys in env (D11); others self-host / BYO-instance (D12); each user brings own LLM key (D13); provider = Anthropic/Claude (D14).
- **Partial failure:** sequential, stop on first failure; sells-first/buys-second so a stop lands in cash; report N of M (D15).
- **Success = orders accepted** by Alpaca, not filled (D16).
- **Market closed:** propose, warn, hold (D17). **Invalid orders:** reject with reason (D18). **Confirm-time re-validation** of positions/prices (D19).
- **Paper-lock scope:** guard covers the paper **trading** host only; read-only market-data host is separate and cannot place orders, so it doesn't weaken the lock; no config path to any URL (D44, implements D25).
- **Audit:** full trail incl. proposed + submitted orders + Alpaca responses + timestamps (D20); store LLM prompt+response (D21); viewable log in v1, undo deferred (D22); state persisted locally, e.g. SQLite (D23).
- **Interface:** minimal local web UI (D24).
- **Stack:** Python backend (D26), React SPA frontend (D27); libraries approved (D33–D40, D43, D50): FastAPI, SQLModel, pytest, alpaca-py (wrapped, paper-locked), hand-written fake Alpaca double, Playwright-Python, Vite, Vitest + React Testing Library, pydantic-settings, anthropic (Claude parser). New deps still need approval (D28).
- **Layout & tooling:** repo is `backend/` + `frontend/` (D41); Python env/deps managed by **uv** with `pyproject.toml` + `uv.lock`, all Python commands run via `uv run …` (D42). Config loading via **pydantic-settings** (D43, approved per D28).
- **Money = `Decimal`** everywhere, never float (D45). **Alpaca client boundary is synchronous**, FastAPI offloads to a threadpool (D46).
- **Testing:** parser tested via mocked-LLM CI tests + a separate semantic golden-set eval suite (D29); Alpaca mocked/recorded for integration, real paper sandbox for a small e2e suite (D30); e2e is full-stack via Playwright against paper (D31); tests are part of every ticket's acceptance criteria — not done until green (D32).

---

## Definition of Done (applies to EVERY ticket — D32)

A ticket is not complete until, in addition to its own acceptance criteria:
- **Unit tests** cover its pure logic with the LLM and Alpaca mocked, and pass.
- **Integration tests** cover any module seam it introduces (mocked Alpaca), and pass.
- If it touches parsing, the **eval golden set** (H-3) is extended with representative cases.
- If it touches the end-to-end loop, the **Playwright e2e** flow (H-4) is extended/kept green.
- No new dependency was added without recorded user approval (D28).

Per-ticket acceptance criteria below call out the *specific* tests that matter for that
ticket; the blanket rules above always apply on top.

---

## Dependency & parallelization map

> Purpose: let a fresh session pick concurrent work without re-deriving the graph.
> Parallelism is real at the **ticket** level; some epics only partly parallelize
> (notably A, G, and H), so this is expressed per ticket. "Blocked by" = hard
> prerequisites. Once a ticket's blockers are done, it can run alongside anything else
> whose blockers are also done.

### Blocked-by table

| Ticket | Blocked by | Can start once… |
|--------|-----------|-----------------|
| A-1 skeleton/config | — | immediately (root) |
| A-2 paper-lock | A-1 | A-1 done |
| A-3 persistence | A-1 | A-1 done |
| A-4 Alpaca client (interface) | A-1, A-2 | A-2 done — publish the interface early |
| A-4 Alpaca client (impl) | A-4 interface | interface defined |
| A-5 Alpaca-unavailable | A-4 impl | A-4 impl done |
| B-1 NL → intent | A-1 | A-1 done (Anthropic key configured) |
| B-2 %-basis resolution | B-1 | B-1 done |
| B-3 category→symbol | B-1, A-4 interface | both done (validate against A-4) |
| B-4 conversational context | B-1, A-3 | both done |
| C-1 intent → orders | B-2, A-4 impl | both done |
| C-2 constraint-solving | C-1 | C-1 done |
| C-3 current-vs-target | A-4 impl | A-4 impl done (pairs with C-1) |
| D-1 restatement + proposal | C-1, B-2, B-3, C-3 | all done |
| D-2 order validation | C-1, A-4 impl | both done (can precede D-1) |
| D-3 market-closed | A-4 impl, D-1 | both done |
| D-4 confirm-time re-validation | D-1, D-2, A-4 impl | all done |
| E-1 sequential execution | D-4, A-4 impl | both done |
| E-2 result reporting | E-1 | E-1 done |
| F-1 audit record | A-3 | A-3 done (schema can precede data producers) |
| F-2 viewable audit log | F-1 | F-1 done |
| G-1 UI — scaffold | A-1 | A-1 done (build against a mocked API) |
| G-1 UI — integration | backend endpoints from D-1..D-4, E-1/E-2 | those endpoints exist |
| G-2 history view UI | F-2, G-1 integration | both done |
| H-1 test runner / CI | A-1 | A-1 done |
| H-2 fake Alpaca double | A-4 interface | interface defined |
| H-3 parser eval golden set | B-1 | B-1 done (grows with B-2/B-3) |
| H-4 Playwright e2e scaffold | G-1 integration, D/E loop | full loop works |

### Suggested waves (each wave's tickets run concurrently)

- **Wave 0 (serial):** A-1.
- **Wave 1 (parallel):** A-2, A-3, H-1, B-1, G-1(scaffold).
- **Wave 2 (parallel):** A-4 (interface→impl), H-2, B-2, B-3, B-4, F-1.
- **Wave 3 (parallel):** A-5, C-1, C-3, H-3.
- **Wave 4 (parallel):** C-2, D-2.
- **Wave 5 (parallel):** D-1, D-3, D-4.
- **Wave 6 (parallel):** E-1, E-2, G-1(integration), F-2.
- **Wave 7 (parallel):** G-2, H-4.

### Concurrent workstreams (big picture)

After the thin core (A-1, A-2, A-4 interface), these tracks run in parallel:
**Parser (B + H-3)** ∥ **Alpaca core (rest of A)** ∥ **Audit store (F)** ∥
**UI shell (G scaffold)** ∥ **Test infra (H-1/H-2)**.

They converge on the **critical path**: `B + A-4 → C → D → E`, which cannot be
parallelized with itself and therefore sets the schedule. Pull B and A-4 forward to
unblock it as early as possible. G's real integration and H-4 land only after D/E exist.

---

## Epic A — Foundation, config & safety rails

### A-1 · Project skeleton & configuration
**Description.** Stand up the repo structure, dependency management, and configuration
loading (Alpaca key/secret, Anthropic key) from an env file for a single local user.
**Acceptance criteria.**
- App boots from a documented `.env` with `ALPACA_KEY`, `ALPACA_SECRET`, `ANTHROPIC_API_KEY`.
- Missing/invalid required config fails fast with a clear message; no silent defaults for secrets.
- README documents local setup and that this is single-user, self-hosted (D11, D12).
**Non-goals.** No accounts, login, multi-tenant config, or secret storage beyond the env file.

### A-2 · Hard paper-lock (D25)
**Description.** Guarantee v1 can only ever hit Alpaca **paper** endpoints. Live trading
must be physically unreachable, not merely a default.
**Acceptance criteria.**
- Alpaca base URL is pinned to the paper endpoint in a single place; no config path reaches a live endpoint.
- A startup assertion/test fails the build if a live endpoint is configured.
- Documented that "live mode" is a separate, deliberately-built future feature with its own guardrails.
**Non-goals.** No paper/live toggle. No live-trading code paths at all.

### A-3 · Local persistence layer (D23)
**Description.** Local datastore (e.g. SQLite) for conversation/session state and the audit trail.
**Acceptance criteria.**
- Schema supports: requests, interpreted intents, proposals, submitted orders, Alpaca responses, LLM prompt+response, timestamps, and session/conversation linkage.
- State survives process restart.
- A single documented file/location; creation is automatic on first run.
**Non-goals.** No remote DB, no migrations framework beyond what's needed for v1, no multi-user partitioning.
- **Landed** (2026-09-05, D49): `rebalancer/store/` — SQLModel + SQLite, fully normalized
  (`AppSession→Conversation→Request→{LlmCall, Intent, Proposal→ProposedOrder, OrderExecution}`),
  Decimal money stored as exact TEXT via `DecimalString` (D45), `AuditStore` write/read API.
  Single file at `backend/data/rebalancer.db` (git-ignored), auto-created in the app lifespan;
  engine factory takes a URL / `REBALANCER_DB_URL` env for tests. No migration framework —
  drop-and-recreate in dev (D49). `Intent`/`Proposal` are lean first-cuts, expanded by B-1/D-1;
  F-1 wires the full end-to-end record.

### A-4 · Alpaca paper client wrapper
**Description.** Thin client over the Alpaca paper API for the calls the app needs:
account/buying-power, positions, latest prices, clock/market-hours, submit order, order status.
**Acceptance criteria.**
- Read methods: account, positions, latest quote/price, market clock, **asset tradability** (`get_asset`, added at interface time to satisfy B-3 symbol validation + D-2 fractional/qty rules — 2026-09-02), order status.
- Write method: submit single order (used sequentially by execution).
- Network/API errors surface as typed errors the caller can branch on (used by A-5 and Epic E): `AlpacaUnavailableError`, `AlpacaRequestError`, `OrderRejectedError`.
- All calls go through the paper-locked base URL from A-2.
- **Interface published** (2026-09-02): `AlpacaClient` ABC + Pydantic domain models (Decimal, D45) + typed errors, synchronous (D46).
- **Impl landed** (2026-09-02, D47): `PaperAlpacaClient` (`alpaca/paper_client.py`) wraps alpaca-py; `paper=True` + construction-time `verify_paper_only` on the SDK base URL (paper-lock unreachable-by-construction); SDK↔domain mapping (Decimal), latest-trade prices on the read-only data host, and `APIError`/transport→typed-error translation. Tests inject SDK stubs at the wrapper boundary (D30); real-sandbox proof is the e2e suite (D31).
**Non-goals.** No order batching primitives, no websocket/streaming, no live endpoints.

### A-5 · Alpaca-unavailable handling (referenced by D17/D19/E)
> **Re-validated 2026-09-03 (D48): not built standalone.** All three criteria depend on
> surfaces that don't exist yet — propose/validate (Epic D), mid-execution (Epic E), audit
> trail (A-3/F-1). Realized *inside* those epics as they land; the blocks (A-4
> `AlpacaUnavailableError`, H-2 `set_unavailable`/`fail_after`) already exist. This ticket
> is a tracking checklist verified as D/E/F land, not code written ahead of its callers.

**Description.** Define and implement behavior when Alpaca is unreachable or errors mid-flow.
**Acceptance criteria.**
- If Alpaca is down during propose/validate: no orders submitted; user sees a clear "can't reach Alpaca, try again" state.
- If Alpaca fails mid-execution: falls under the sequential stop-on-failure rule (D15) — stop, report completed N of M and remaining cash.
- Errors are recorded in the audit trail (D20).
**Non-goals.** No automatic retry queues or background re-attempts in v1.

---

## Epic B — NL understanding (open-ended parser)

### B-1 · Open-ended request → structured intent (D6, D4)
**Description.** Use Claude to turn a free-form request into a structured intent object
(actions, source/target categories or symbols, amounts + basis, constraints, confidence).
**Acceptance criteria.**
- Output is a validated structured object; malformed model output is caught and treated as a parse failure, not executed.
- Intent captures: action type(s), operands, amount + amount-basis, any constraints (links to B-3, C-*).
- The raw prompt and raw response are persisted (D21).
- Low-confidence or unparseable input routes to confirm/clarify, never to silent action (D4).
**Non-goals.** No order generation here (that's Epic C). No provider abstraction — Claude only (D14).
- **Landed** (2026-09-06, D50): `rebalancer/parsing/` — `IntentParser` calls `anthropic`
  `messages.parse(output_format=WireParsedIntent)`; result is a discriminated `ParseResult`
  (parsed / needs_clarification / unsupported, or `ok=False` for refusal / no-output /
  malformed / API error — never executes). Domain contract in `parsing/models.py`
  (`Intent`→`Operation`+`Constraint`, `AmountBasis`, Decimal money via string-on-wire, D45).
  Default model `claude-sonnet-5` (env `ANTHROPIC_MODEL`). Raw prompt+response captured for
  the audit trail (D21). LLM injected → mocked in unit tests (D29). B-2 (basis math) and B-3
  (category→symbol) refine downstream; this captures the raw reading only.

### B-2 · Percentage-basis resolution (D2)
**Description.** Resolve what a percentage/amount means for each request: target weights,
% of total portfolio, or % of source position; default to **% of current source position**
when genuinely ambiguous.
**Acceptance criteria.**
- Given "make it 60/40", "put 10% of my portfolio in bonds", "sell half my tech", each resolves to the correct basis.
- Ambiguous phrasing defaults to % of source position **and** the chosen basis is recorded so it can be shown at confirm (D4).
- The resolved basis is part of the structured intent (B-1).
**Non-goals.** No silent guessing without recording the chosen reading.
- **Landed** (2026-09-06, D52): `parsing/basis.py` `resolve_basis()` — a deterministic
  guardrail over B-1's parse (no LLM, no account state). Applies the D2 ambiguity default
  (bare/unstated % → `percent_source_position`, flagged `basis_defaulted`, noted for
  confirm); validates coherence (% in (0,100], `set_allocation` weights ≤ 100 → else
  clarify). Dollar/share math stays in C-1 on live state (D19). Added `basis_explicit` to
  the parse schema (`Amount`). Pure unit tests (deterministic — no mocks).

### B-3 · Category → symbol mapping (D5)
**Description.** Map category words ("tech", "bonds") to concrete Alpaca-tradable symbols
dynamically via the LLM, constrained to tradable US equities/ETFs.
**Acceptance criteria.**
- Category terms resolve to a concrete symbol set; unmappable terms route to refuse+explain (D10).
- The resulting mapping is captured so it can be shown to the user at confirm (D5, D4).
- Symbols are validated as Alpaca-tradable before use.
**Non-goals.** No fixed/curated category dictionary as the primary mechanism; no non-US or non-equity/ETF assets.
- **Landed** (2026-09-06, D51): `parsing/mapping.py` — `SymbolResolver` resolves each intent
  operation target. Literal tradable tickers pass through; category words go through one
  `messages.parse` call and every proposed symbol is validated via A-4 `get_asset`.
  **Sells are holdings-aware** (resolved only to matching current positions; none → refuse);
  **buys lean to a representative US-listed ETF**. Unmappable/untradable term → refuse the
  whole request (D10, no partial). Alpaca-unavailable propagates (A-5). `MappingResult`
  distinguishes refusal (D10) from LLM error. Validated against A-4 via the H-2 fake; LLM
  mocked (D29); H-3 gains a mapping eval case. Mapping + raw prompt/response captured (D5/D21).

### B-4 · Conversational context (D7)
**Description.** Support multi-turn follow-ups that reference the prior proposal
("actually make it 70/30 instead").
**Acceptance criteria.**
- A follow-up can modify the most recent proposal within a session using stored context (A-3).
- Each turn produces a fresh proposal that still passes the full confirm + re-validation flow (Epic D).
- Session context is persisted (D23) and linked in the audit trail (D20).
**Non-goals.** No cross-session long-term memory of preferences; no auto-applying a follow-up without re-confirmation.

---

## Epic C — Rebalance planning & constraint-solving

### C-1 · Intent → concrete order set
**Description.** Turn a resolved intent (B-1/B-2/B-3) plus current account state into a
concrete ordered list of buy/sell orders.
**Acceptance criteria.**
- Produces explicit per-symbol orders with quantities/notional derived from the resolved basis.
- Orders are ordered **sells-first, buys-second** (D15).
- Uses live positions/buying power from A-4.
**Non-goals.** No submission (Epic E). No handling of invalid orders here beyond producing them for validation (D-2).
- **Landed** (2026-09-07, D53): `planning/planner.py` `Planner.plan(intent, mappings)` →
  ordered `Plan`. Notional for $ targets/buys, qty for position-relative sells; `set_allocation`
  weights summing ~100% = whole-portfolio rebalance (liquidate the rest); semantics per
  (action, basis); sells-first/buys-second (D15); amounts rounded down (never oversell/
  overspend). No validation (D-2) or constraints (C-2). Reads `get_account`+`get_positions`
  from A-4; Alpaca-unavailable propagates (A-5). Deterministic — 12 integration tests vs. the
  H-2 fake, no LLM.

### C-2 · Constraint-solving (D8, D10)
**Description.** Honor request constraints: cash floors ("keep $5k cash"), exclusions
("don't sell AAPL"), and source restrictions ("only using new deposits").
**Acceptance criteria.**
- Each supported constraint measurably changes the produced order set.
- Conflicting/unsatisfiable constraint sets produce **no partial orders** — they route to refuse+explain stating what couldn't be satisfied (D10).
- Constraints applied are captured for display at confirm.
**Non-goals.** No optimization objective beyond satisfying stated constraints; no constraint types not listed here in v1.
- **Landed** (2026-09-08, D55 ⚠️): `planning/constraints.py` `ConstraintSolver.solve(intent, mappings)`
  → `PlanResult` (ok+plan+applied, or refuse). cash_floor → reduce investable base; exclusion
  → set-aside (protected, value out of base); only_new_deposits + unsatisfiable numerics →
  refuse (D10). Applied constraints returned for confirm. Integrated via planner
  `plan_from_state(investable_equity, protected)`. ⚠️ Default readings flagged (QUESTIONS.md).
  7 deterministic tests vs. the H-2 fake.

### C-3 · Current-vs-target computation (supports D24)
**Description.** Compute and expose current allocation vs. the target allocation implied
by the proposal, for display.
**Acceptance criteria.**
- Returns per-category/per-symbol current % and target %, plus the deltas the orders will attempt.
- Numbers reconcile with the concrete order set from C-1.
**Non-goals.** No post-execution reconciliation guarantee (success = accepted, D16).
- **Landed** (2026-09-08): `planning/allocation.py` `compute_allocation(plan, alpaca)` →
  `AllocationReport` of per-symbol current % / target % / delta. Target is derived from the
  plan (current value + each order's signed value effect), so it reconciles with the C-1
  order set by construction. Values qty orders at holdings price (fetches for unheld symbols,
  read-only D44); display-only (D24). Per-**category** grouping deferred (can layer on B-3
  mappings later — flagged, low-risk display choice). 6 deterministic tests vs. the H-2 fake.

---

## Epic D — Proposal & confirmation loop

### D-1 · Plain-English restatement + proposal (D4, D2, D5)
**Description.** Present a proposal: plain-English restatement of the understood request,
the resolved % basis, the category→symbol mapping, the literal orders, and current-vs-target.
**Acceptance criteria.**
- Nothing executes without this proposal being shown and explicitly confirmed (D1, D4).
- Restatement surfaces the chosen amount-basis (D2) and symbol mapping (D5) so a wrong interpretation is visible before acting.
- Proposal is persisted (D20).
**Non-goals.** No size-based extra confirmation step (D9). No auto-confirm.
- **Landed** (2026-09-08, D56): `proposal/service.py` `ProposalService.propose(text)` →
  `ProposalOutcome` (PROPOSAL / CLARIFY / REFUSE / UNAVAILABLE / ERROR) assembling the whole
  read-side pipeline. Restatement = parser summary + basis notes + mapping + constraints (no
  extra LLM call — flagged). Persists request/LLM-calls/proposal via AuditStore (D20). Also
  realizes **D-3** (closed market → proposal + warning) and **A-5** propose-side (Alpaca-down
  → UNAVAILABLE). 9 pipeline tests (mocked LLM + H-2 fake + store).

### D-2 · Order validation & reject-with-reason (D18)
**Description.** Validate the proposed orders against Alpaca rules (buying power,
fractional/qty limits) before showing/executing.
**Acceptance criteria.**
- Invalid orders are rejected with a specific human-readable reason; the proposal contains no invalid orders (D18).
- User is told what to adjust; nothing is auto-adjusted.
**Non-goals.** No "adjust and warn" auto-correction. No submitting-and-letting-Alpaca-reject.
- **Landed** (2026-09-08, D54 ⚠️): `planning/validation.py` `OrderValidator.validate(plan)` →
  `ValidationResult` (ok + per-order/plan-level `OrderProblem`s, no auto-adjust, no partial).
  Rules: tradable/known, notional requires fractionable, no fractional qty on non-fractionable,
  no overselling (sell qty ≤ held), notional ≥ $1, and **buying power counts expected sell
  proceeds** (sells-first, D15). ⚠️ Settlement (T+1) / margin not modeled — flagged for review
  (D54). 12 deterministic tests vs. the H-2 fake.

### D-3 · Market-closed handling (D17)
**Description.** When the market is closed, show the proposal with a clear warning and hold.
**Acceptance criteria.**
- Market-closed state is detected (A-4 clock) and shown on the proposal.
- Orders are not submitted while closed until the user confirms; no silent queuing.
**Non-goals.** No scheduling/queuing orders for next open.
- **Landed** (2026-09-08, with D-1/D56): market-closed state (A-4 clock) surfaces as a
  `PROPOSAL` carrying a warning; no submission while closed until confirm. Tested in
  `test_proposal.py::test_market_closed_proposal_carries_warning`.

### D-4 · Confirm-time re-validation (D19)
**Description.** On confirm, re-fetch positions/prices, re-run validation, and if the
situation materially changed, re-show the proposal before submitting.
**Acceptance criteria.**
- Positions/prices/buying-power are re-fetched at confirm.
- A material change (definition documented in-code, e.g. validity flips or notional drift beyond a set tolerance) re-shows the proposal instead of submitting.
- Only an unchanged (or user-re-confirmed) proposal proceeds to execution.
**Non-goals.** No continuous live re-pricing; a single re-check at confirm is sufficient.

---

## Epic E — Execution & reporting

### E-1 · Sequential execution, stop-on-failure (D15, D16)
**Description.** Submit the confirmed orders one at a time in the sells-first/buys-second
order; stop on the first failure.
**Acceptance criteria.**
- Orders submitted sequentially; a failure halts remaining submissions.
- On stop, the account is left with the safe cash residue (sells done, failed/blocked buys not forced).
- "Success" is reported at **order-accepted** granularity (D16).
- Every submission + Alpaca response recorded (D20).
**Non-goals.** No unwinding of completed legs. No fill-tracking/allocation-reconciliation as a success gate.
- **Landed** (2026-09-08, D57): `execution/ExecutionService.confirm_and_execute(plan, request_id)`.
  Re-validates (D-4), holds if market closed (D17), else submits sells-first one at a time and
  stops on the first reject/outage (D15), leaving the rest in cash. Records each execution +
  status (D20). 8 tests via the H-2 accept/reject/fail scripting.

### E-2 · Result reporting
**Description.** Report the outcome: completed N of M, which orders were accepted, any
failure and its reason, and cash left over.
**Acceptance criteria.**
- User sees a clear "completed N of M, $X left in cash" style summary consistent with D15.
- Failures show Alpaca's reason.
- Report is persisted in the audit trail (D20).
**Non-goals.** No claims about fills or final realized allocation.
- **Landed** (2026-09-08, with E-1/D57): `ExecutionReport` — status, completed N of M, accepted
  orders, failure reason, best-effort cash remaining (⚠️ pre-settlement). Persisted via the
  execution rows + request status (D20).

---

## Epic F — Audit trail & history

### F-1 · Full audit record (D20, D21)
**Description.** Persist a complete per-request record end to end.
**Acceptance criteria.**
- For each request: raw text, LLM prompt+response, interpreted intent, resolved basis + mapping, proposal, validation results, submitted orders, Alpaca responses, timestamps.
- Records are linked into their conversation/session (B-4, A-3).
**Non-goals.** No redaction/retention tooling in v1 (bounded by self-host, D12).

> **Read-API landed** (2026-09-08): `GET /api/requests` (recent, newest-first) and
> `GET /api/requests/{id}` (full record: raw text, LLM prompt+response, proposal legs,
> executions, timestamps) back the viewable log (`AuditStore.list_requests` + `get_request`).
> The *view* itself is part of the frontend (G).

### F-2 · Viewable audit log (D22)
**Description.** Let the user browse the history of requests, proposals, and executions.
**Acceptance criteria.**
- User can view past requests and drill into what was requested, proposed, and executed.
- Enough detail to reconstruct/diagnose a disputed rebalance.
**Non-goals.** **No "undo last rebalance"** in v1 — explicitly deferred (D22).

---

## Epic G — Minimal web UI (D24)

### G-1 · Request → proposal → confirm UI
**Description.** Minimal local web app tying the loop together: enter request, see the
proposal (restatement + basis + mapping + orders + current-vs-target), confirm to execute.
**Acceptance criteria.**
- Full flow works in-browser locally: type → propose → confirm → result.
- Confirmation is an explicit user action (D1, D4); market-closed and re-validation states are shown (D3/D-3, D-4).
- Conversational follow-ups can be issued in the same session (B-4).
**Non-goals.** No auth, multi-user, hosting, or styling beyond functional. No mobile.

### G-2 · History view in UI
**Description.** Surface the viewable audit log (F-2) in the web UI.
**Acceptance criteria.**
- User can browse past requests/proposals/executions from the UI.
**Non-goals.** No undo controls (D22). No export tooling in v1.

---

## Epic H — Testing infrastructure (foundational; land alongside Epic A)

> This epic exists because the two hardest-to-test surfaces (non-deterministic parser,
> external Alpaca API) need harnesses in place *before* feature tickets can satisfy the
> Definition of Done. H-1..H-2 should be built early; H-3/H-4 grow as features land.

### H-1 · Test runner & CI wiring (D28, D32)
**Description.** Stand up the Python test runner and a CI pipeline that runs unit +
integration tests (mocked externals) on every commit; the eval and paper-e2e suites are
opt-in / scheduled, not on every commit.
**Acceptance criteria.**
- `pytest` (+ `pytest-asyncio`, approved D35) runs unit + integration locally and in CI.
- CI is green on an empty/placeholder suite; fast tier excludes live LLM and live Alpaca.
- Separate marked tiers exist for `eval` (H-3) and `e2e` (H-4) so they don't run in the fast tier.
**Non-goals.** No coverage-percentage gate (D32 chose per-ticket AC over a numeric threshold).

### H-2 · Mock/record Alpaca client (D30)
**Description.** A test double for the Alpaca client (A-4) usable by unit/integration tests:
deterministic account/positions/prices/clock and order submission, plus failure injection.
**Acceptance criteria.**
- Integration tests can script positions, buying power, market open/closed, and per-order accept/reject.
- Can simulate mid-sequence failure to exercise stop-on-failure/land-in-cash (D15) and Alpaca-down (A-5).
- Implemented as a **hand-written fake double** of the A-4 wrapper interface (D37) — no HTTP-mock dependency.
**Non-goals.** Not the real paper client (that's A-4, exercised only by H-4). No live calls here. No recorded-cassette / respx-vcrpy layer (rejected in favor of the fake double, D37).

### H-3 · Parser eval golden set (D29)
**Description.** A semantic evaluation suite: curated phrasings → expected structured intent,
graded by meaning rather than exact match. Grows with every parsing-related ticket.
**Acceptance criteria.**
- Cases cover %-basis variants (D2), category→symbol mapping (D5), constraints (D8), and refuse+explain (D10).
- Grading is semantic (field-level/assertion-based), tolerant of surface variation.
- Runs on demand against real Claude; reports pass rate; not in the fast CI tier.
**Non-goals.** Not a pass/fail commit gate; it's a quality measurement (D29). No mocked-LLM cases here (those live with the feature).
- **Seeded** (2026-09-06, with B-1): `tests/eval/` — `golden.py` (6 cases: %-basis variants,
  constraints, crypto-refuse, exclusion) + `test_parser_eval.py`, marked `eval` and excluded
  from the fast tier (pyproject `addopts`). Opt-in: `RUN_EVAL=1 uv run pytest -m eval`. Grows
  with B-2/B-3. (The fast-tier marker split satisfies H-1's third criterion early.)

### H-4 · Playwright full-stack e2e scaffold (D31)
**Description.** Playwright-Python (approved D38) driving the React UI through the full
loop — request → proposal → confirm → result — against the Alpaca **paper** sandbox.
**Acceptance criteria.**
- A smoke e2e completes the happy-path loop end to end against paper.
- Hooks/fixtures exist to reach reproducible states (e.g. known starting positions) where feasible.
- Runs in its own tier (not fast CI); documented how to run locally with paper creds.
**Non-goals.** No live-account (non-paper) testing ever (D25). Not a substitute for unit/integration coverage.

---

## Requirements-audit checklist (run after finishing each epic)

- Re-read `REQUIREMENTS.md`; confirm no later decision (higher D-number) contradicts a
  ticket's acceptance criteria in a completed or upcoming epic.
- Specifically re-check the known-large-scope items (D6/D7/D8) haven't been quietly narrowed.
- Confirm the paper-lock (D25) still holds across any new Alpaca code paths.
- Surface any conflict to the user rather than silently picking one.
