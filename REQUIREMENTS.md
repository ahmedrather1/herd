# REQUIREMENTS.md — NL Portfolio Rebalancer

**Living source of truth.** Nothing is "decided" until it is written here. Every
locked decision is dated with a one-line rationale. When implementation surfaces a
new ambiguity, stop and interrogate it (batched questions, push back on vagueness,
make a concrete choice) and record the outcome here immediately — do not leave it
implicit in code or chat.

- Project: natural-language portfolio rebalancer on the Alpaca API.
- Read this file **and** `BACKLOG.md` at the start of every session before touching a ticket.
- Last updated: 2026-09-02 (added tech stack §6 + testing strategy §7; locked libraries D33–D40)

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

## 6. Tech stack (locked 2026-09-02)

| # | Decision | Rationale |
|---|----------|-----------|
| D26 | **Backend = Python.** | First-party Alpaca + Anthropic SDKs; strong fit for parsing/planning logic and pytest ecosystem. |
| D27 | **Frontend = React SPA** talking to the backend API. | Flexible path toward the eventual real frontend (D24). |
| D28 | **Stack governance: approve each major library.** Claude proposes any significant dependency and waits for the user's explicit yes before it is adopted; the approved choice is then recorded here. | User wants control over lock-in/architecture choices. |

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
