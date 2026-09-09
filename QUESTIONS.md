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

- **Epic G — frontend (React/Vite SPA).** The whole UI is a design surface: the type-a-request
  box, the **confirm screen** (how the restatement + orders + current-vs-target + warnings are
  laid out), the result view, and the audit-log view (F-2). This is the big "let's design it
  together" piece — the API it codes against is done (`/api/propose`, `/api/confirm`,
  `/api/requests`). **Want me to scaffold G-1 (Vite skeleton) and propose a UI, or design it
  with you first?**
- **F-1 — full audit record.** Right now I persist request / LLM prompt+response / proposal
  (summary + legs) / executions. The **rich interpreted intent** (operations + constraints),
  **resolved basis**, **mapping details**, and **validation results** aren't persisted yet.
  You had strong views on schema design (D49 — normalize, no JSON blobs), so I didn't guess:
  **how much of this do you want as new normalized tables vs. left at the lean level?**
- **H-4 — Playwright e2e** — needs the frontend first (drives the real UI through
  request → proposal → confirm → result against the paper account).

Everything above the line was built with a flagged default; everything here I'm leaving for
you on purpose.
