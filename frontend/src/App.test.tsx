import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const ok = (data: unknown) => ({ ok: true, status: 200, json: async () => data });

const PORTFOLIO = {
  equity: "10000",
  cash: "1000",
  holdings: [
    { symbol: "AAPL", value: "9000", pct: "90.00" },
    { symbol: "CASH", value: "1000", pct: "10.00" },
  ],
  balance: [
    { date: "2026-09-01", equity: "9800" },
    { date: "2026-09-08", equity: "10000" },
  ],
};

const PROPOSAL = {
  status: "proposal",
  request_id: "r1",
  conversation_id: "c1",
  message: null,
  problems: [],
  restatement: "Put 10% into bonds.\nSymbols: bonds → BND",
  orders: [{ symbol: "BND", side: "buy", qty: null, notional: "1000.00", reason: "buy to reach target" }],
  open_orders: [],
  allocation: { equity: "10000", rows: [{ symbol: "BND", current_value: "0", current_pct: "0.00", target_value: "1000.00", target_pct: "10.00", delta_value: "1000.00" }] },
  applied_constraints: [],
  market_open: true,
  market_warning: null,
};

const CONFIRMED = {
  status: "completed",
  message: "Done — all 1 orders were accepted.",
  completed: 1,
  total: 1,
  failure: null,
  cash_remaining: "9000",
  submitted: [{ symbol: "BND", side: "buy", status: "accepted", order_id: "o1", reason: null }],
  revalidation_problems: [],
};

// URL-dispatched fetch mock — the dashboard fetches /api/portfolio on mount.
function mockApi(routes: Record<string, unknown>) {
  const fn = vi.fn((url: string) => {
    const data = routes[String(url)] ?? {};
    return Promise.resolve(ok(data));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("App", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows the allocation dashboard on load", async () => {
    mockApi({ "/api/portfolio": PORTFOLIO });
    render(<App />);
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("Allocation")).toBeInTheDocument();
  });

  it("proposes, shows the proposal, then confirms and shows the result", async () => {
    const fetchMock = mockApi({ "/api/portfolio": PORTFOLIO, "/api/propose": PROPOSAL, "/api/confirm": CONFIRMED });
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("request"), "put 10% in bonds");
    await user.click(screen.getByRole("button", { name: /^propose$/i }));

    expect(await screen.findByText("Proposed")).toBeInTheDocument();
    expect(screen.getByText("$1000.00")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirm & place/i }));
    expect(await screen.findByText("Done")).toBeInTheDocument();
    expect(screen.getByText(/Completed 1 of 1/)).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith("/api/propose", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenCalledWith("/api/confirm", expect.objectContaining({ method: "POST" }));
  });

  it("cancels pending orders via the same box", async () => {
    const CANCEL = {
      status: "cancel",
      request_id: "rc",
      conversation_id: "c1",
      message: "Cancel these open orders?",
      problems: [],
      restatement: null,
      orders: [],
      open_orders: [{ symbol: "VTI", side: "buy", qty: null, notional: "500.00", reason: "ord-1" }],
      allocation: null,
      applied_constraints: [],
      market_open: null,
      market_warning: null,
    };
    const CANCELED = { status: "canceled", message: "Canceled 1 of 1 open orders.", completed: 1, total: 1, failure: null, cash_remaining: null, submitted: [{ symbol: "VTI", side: "buy", status: "canceled", order_id: "ord-1", reason: null }], revalidation_problems: [] };
    mockApi({ "/api/portfolio": PORTFOLIO, "/api/propose": CANCEL, "/api/cancel": CANCELED });
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("request"), "cancel that");
    await user.click(screen.getByRole("button", { name: /^propose$/i }));

    expect(await screen.findByText("Cancel pending orders?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /cancel these orders/i }));
    expect(await screen.findByText("Canceled")).toBeInTheDocument();
  });
});
