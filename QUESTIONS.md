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

<!-- New questions get appended below as I build E, etc. -->
