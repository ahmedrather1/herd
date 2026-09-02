# CLAUDE.md — session guide for the NL Portfolio Rebalancer

This file is auto-loaded at the start of every session. Follow it before doing anything.

## Start-of-session ritual (do this first, every time)

1. **Read `REQUIREMENTS.md` in full.** It is the living source of truth. Decisions are
   numbered (D1, D2, …) and dated. Nothing is "decided" unless it is written there.
2. **Read `BACKLOG.md` in full.** Epics A–H, each with tickets that have acceptance
   criteria and non-goals. The top mirrors REQUIREMENTS.md — if the two ever disagree,
   REQUIREMENTS.md wins and you should fix the mirror.
3. **Check `git log --oneline` and `git status`** to see what already landed and whether
   the tree is clean.
4. **Before starting a ticket, re-validate its assumptions.** If a later decision
   (higher D-number) has made a ticket's acceptance criteria shaky, inconsistent, or
   stale, **stop and flag it — re-question before coding.** Do not assume an old ticket
   is still correct just because it is written down.

## Working rules (these are not optional)

- **Requirements-gathering is continuous.** When implementation surfaces a new ambiguity
  or a decision with hidden sub-decisions, STOP. Interrogate it the same way as upfront:
  batched questions, push back on vague answers, make the user choose concretely. Do not
  silently resolve it and keep coding.
- **Record every new decision in `REQUIREMENTS.md` immediately** — dated, numbered, with a
  one-line rationale — and update the mirror in `BACKLOG.md`. Not in code comments, not
  only in chat.
- **Definition of Done applies to every ticket** (see BACKLOG.md): required tests at the
  right levels must be green; parsing changes extend the eval golden set (H-3);
  end-to-end changes keep the Playwright flow (H-4) green.
- **Approve-each-library (D28):** never add a new dependency without proposing it and
  getting explicit user approval, then recording it in the approved-libraries table.
- **Paper-lock is an invariant (D25):** v1 code must be physically unable to reach a live
  Alpaca endpoint. Treat any change that could weaken this as a stop-and-flag event.

## Milestone workflow (commit/push cadence)

At each **completed milestone** (a ticket whose acceptance criteria + Definition of Done
are met and verified — e.g. A-1, A-2, …):

1. **Present a summary of the changes** — what was built, what was verified, which
   decisions were recorded, and any caveats. Not a raw file list; the same kind of
   readable summary used when reporting work.
2. **Wait for the user's explicit approval.** Do not commit or push before they say yes.
3. **On approval, commit + push to `main`.** Commit direct to `main` (no feature
   branches/PRs for this solo project), clear message with the `Co-Authored-By` trailer,
   then push to `origin` (private GitHub repo `herd`).

## Requirements audit (after finishing each epic)

Run the checklist at the bottom of `BACKLOG.md`: scan for tickets whose acceptance
criteria now conflict with later decisions, and surface conflicts to the user rather than
quietly picking one. Pay special attention to the known-large-scope items (D6/D7/D8) and
the paper-lock (D25).

## Fast orientation

- Stack: Python + FastAPI backend, React (Vite) SPA, SQLite via SQLModel, official
  alpaca-py SDK (wrapped + paper-locked). Tests: pytest, fake Alpaca wrapper double,
  Playwright-Python e2e, Vitest + React Testing Library. (See D26–D40.)
- Suggested first tickets: **A-2** (paper-lock) and **H-2** (fake Alpaca double), since
  nearly everything else depends on them.
