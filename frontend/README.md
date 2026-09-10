# Frontend — NL Portfolio Rebalancer (SPA)

Minimal React + Vite + TypeScript UI (D24/D27/D39/G-1/G-2). Functional styling only —
no auth, hosting, or polish (G-1 non-goals). First-pass design, open to iteration.

## Quick start

```bash
npm install
npm run dev      # http://localhost:5173  (proxies /api → http://127.0.0.1:8000)
npm test         # Vitest + React Testing Library (D40)
npm run build    # type-check + production bundle
```

Run the backend separately (`cd ../backend && uv run rebalancer`) so `/api` resolves.

## What it does

- **Rebalance tab (G-1):** type a request → **Propose** (`POST /api/propose`) → see the
  restatement, orders, and current-vs-target → **Confirm & place orders**
  (`POST /api/confirm`) → result. Confirmation is an explicit click (D1/D4). Clarify,
  refuse, market-closed, re-validation, and Alpaca-unavailable states are all shown.
  Follow-ups in the same session reuse the `conversation_id` (B-4).
- **History tab (G-2):** browse past requests (`GET /api/requests`) and open the full
  audit record (`GET /api/requests/{id}`), i.e. the viewable log (F-2).

## Layout

```
frontend/
  src/
    App.tsx          # state + flow (propose → confirm; tabs)
    api.ts           # typed client (money as strings, D45)
    ProposalView.tsx # proposal / clarify / refuse rendering
    ResultView.tsx   # execution report (E-2)
    History.tsx      # audit log (G-2/F-2)
    App.test.tsx     # Vitest + RTL flow tests
  vite.config.ts     # react plugin, /api dev proxy, vitest (jsdom)
```
