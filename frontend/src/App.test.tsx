import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const ok = (data: unknown) => ({ ok: true, status: 200, json: async () => data });

const PROPOSAL = {
  status: "proposal",
  request_id: "r1",
  conversation_id: "c1",
  message: null,
  problems: [],
  restatement: "Put 10% into bonds.\nSymbols: bonds → BND",
  orders: [{ symbol: "BND", side: "buy", qty: null, notional: "1000.00", reason: "buy to reach target" }],
  allocation: {
    equity: "10000",
    rows: [{ symbol: "BND", current_value: "0", current_pct: "0.00", target_value: "1000.00", target_pct: "10.00", delta_value: "1000.00" }],
  },
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

describe("App", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("proposes, shows the proposal, then confirms and shows the result", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(ok(PROPOSAL)).mockResolvedValueOnce(ok(CONFIRMED));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("request"), "put 10% in bonds");
    await user.click(screen.getByRole("button", { name: /^propose$/i }));

    expect(await screen.findByText("Proposed")).toBeInTheDocument();
    expect(screen.getAllByText("BND").length).toBeGreaterThan(0); // appears in orders + allocation
    expect(screen.getByText("$1000.00")).toBeInTheDocument();
    expect(screen.getByText(/Symbols: bonds/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirm/i }));

    expect(await screen.findByText("Done")).toBeInTheDocument();
    expect(screen.getByText(/Completed 1 of 1/)).toBeInTheDocument();

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/propose", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/confirm", expect.objectContaining({ method: "POST" }));
  });

  it("shows a clarify outcome without a confirm button", async () => {
    const clarify = { ...PROPOSAL, status: "clarify", message: "Which assets?", restatement: null, orders: [], allocation: null };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(clarify)));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("request"), "make it 60/40");
    await user.click(screen.getByRole("button", { name: /^propose$/i }));

    expect(await screen.findByText("Which assets?")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /confirm/i })).not.toBeInTheDocument();
  });
});
