# Open questions for review

Decisions I made a **default** call on while building overnight (2026-09-08+), each flagged
for you to confirm or change. Nothing here is load-bearing in a way that's hard to reverse —
they're recorded as numbered decisions in `REQUIREMENTS.md` and can be revisited. Answer
inline or in chat; I'll adjust and re-commit.

## ⚠️ Already flagged

- **D54 — buying-power settlement.** D-2 counts expected **sell proceeds** toward buying
  power (correct, since execution is sells-first, D15). I did **not** model settlement
  (cash-account T+1) or margin — the fake doesn't either. On the real paper sandbox,
  unsettled proceeds could still be rejected at execution. **OK to leave as-is for v1?**

## C-2 — constraint-solving (defaults chosen; see D55)

- **Cash floor** ("keep $5k in cash"): I treat it as reducing the **investable** base —
  targets are computed on `equity − floor`, so a rebalance leaves exactly the floor in cash.
  *Alternative:* refuse if the request would breach the floor. **Reduce-investable OK?**
- **Exclusion** ("don't sell AAPL"): the excluded holding is **set aside** — never sold, and
  its value is removed from the investable base (so the rest rebalances around it). *This
  assumes the exclusion target is a **symbol**;* a category exclusion ("don't sell my tech")
  isn't mapped to symbols yet and won't match. **Set-aside semantics OK? Do you want category
  exclusions supported?**
- **"Only new deposits"**: we don't track deposits anywhere, so v1 **refuses + explains**
  ("phrase it as a dollar amount to invest instead"). **OK to leave unsupported in v1?**

## D-1 — proposal assembly (defaults chosen; see D56)

- **Restatement source.** The plain-English restatement is built **deterministically** from
  the parser's `summary` + basis notes + the symbol mapping + applied constraints — **no extra
  LLM call**. Cheaper and deterministic, and it still surfaces the basis (D2) and mapping (D5).
  *Alternative:* a second LLM call to phrase a nicer restatement. **Keep it deterministic?**
- **Proposal persistence depth.** D-1 records the request, the parse + mapping LLM calls, and
  the proposal (summary + order legs) via the lean A-3 tables. The *rich* intent (operations/
  constraints), allocation, and validation aren't persisted yet — that's **F-1**. **OK to leave
  the full record to F-1?**

## D-4 / E — confirm re-validation & execution (defaults chosen; see D57)

- **Material-change definition (D-4/D19).** At confirm I re-validate against fresh state and
  block (`REVALIDATE`, re-show) only when validity **flips to invalid**. I do **not** re-plan
  on price drift (recompute 60/40 targets against the new equity). *Alternative:* re-plan at
  confirm and re-show if orders drift beyond a tolerance. **Is validity-flip enough for v1?**
- **Cash-remaining figure (E-2).** Reported as `account.cash` right after submitting. Because
  fills are async (D16), this is **pre-settlement** and approximate. **OK to report it with a
  "pre-settlement" caveat, or omit the dollar figure and just say N of M?**

## HTTP API (defaults chosen; see D58)

- **Wire contract.** `POST /api/propose` {request_text} → the proposal outcome; `POST /api/confirm`
  {request_id} → the execution report. Money is serialized as **strings** (exact Decimal, D45).
  This is what the frontend (G) will code against. **Happy with this shape?** (Full schemas in
  `api/schemas.py`.)
- **Confirm is stateless** — it reconstructs the plan from the **persisted proposal** by
  `request_id` rather than keeping server-side session state. Simple for a single-user local
  app, but the proposal must have been persisted (store required). **OK?**

## What's left (these genuinely want your input)

The backend is **complete end-to-end** (Epics A–E, HTTP API, F-2 read API, H-1 CI, all
green — 160 fast tests). What remains needs a real decision from you:

- **Epic G — frontend (React/Vite SPA).** ✅ Scaffolded + first-pass UI built (D61):
  `frontend/` with the propose→confirm flow, all outcome states, and a history tab. Functional
  styling only (per the ticket). **This is a first pass to react to** — run `npm run dev` (with
  the backend up) and tell me what to change: layout, wording, the confirm screen, the history
  detail view (currently raw JSON), visual polish, etc. That's the natural next "together" step.
- ~~**F-1 — full audit record.**~~ ✅ Done (D60) — you chose full normalized tables. Intent
  operations + constraints, mapping, allocation snapshot, and validation reasons are now
  persisted and exposed at `GET /api/requests/{id}`.
- **H-4 — Playwright e2e** — ✅ Scaffolded (`backend/tests/e2e/test_smoke.py`), opt-in tier.
  ⚠️ **Not run in the build environment** (needs the live stack + paper/Anthropic keys). Please
  run it once locally to confirm: `RUN_E2E=1 uv run --group e2e pytest -m e2e` with backend +
  frontend up.

## Status: every backlog ticket is now built

Epics A–H are all implemented; the fast suite is 160 green (+7 eval, +1 e2e opt-in). What's
left for you: (1) review the flagged defaults above, (2) react to the first-pass UI, (3) run
the e2e once against your paper account. Nothing is blocked on me.
