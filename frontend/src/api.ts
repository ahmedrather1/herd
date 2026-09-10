// Typed client for the backend API (D24, D58). Money fields are strings (exact Decimal, D45).

export interface Order {
  symbol: string;
  side: string;
  qty: string | null;
  notional: string | null;
  reason: string;
}

export interface AllocationRow {
  symbol: string;
  current_value: string;
  current_pct: string;
  target_value: string;
  target_pct: string;
  delta_value: string;
}

export interface Allocation {
  equity: string;
  rows: AllocationRow[];
}

export interface ProposeResponse {
  status: "proposal" | "clarify" | "refuse" | "unavailable" | "error" | "cancel";
  request_id: string | null;
  conversation_id: string | null;
  message: string | null;
  problems: string[];
  restatement: string | null;
  orders: Order[];
  open_orders: Order[];
  allocation: Allocation | null;
  applied_constraints: string[];
  market_open: boolean | null;
  market_warning: string | null;
}

export interface Holding {
  symbol: string;
  value: string;
  pct: string;
  qty: string | null;
  price: string | null;
}

export interface BalancePoint {
  date: string;
  equity: string;
}

export interface Portfolio {
  equity: string;
  cash: string;
  holdings: Holding[];
  balance: BalancePoint[];
}

export interface Submitted {
  symbol: string;
  side: string;
  status: string;
  order_id: string | null;
  reason: string | null;
}

export interface ConfirmResponse {
  status: "completed" | "partial" | "revalidate" | "market_closed" | "unavailable" | "nothing" | "canceled";
  message: string;
  completed: number;
  total: number;
  failure: string | null;
  cash_remaining: string | null;
  submitted: Submitted[];
  revalidation_problems: string[];
}

export interface RequestSummary {
  request_id: string;
  raw_text: string;
  status: string;
  created_at: string;
}

async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json() as Promise<T>;
}

export function propose(requestText: string, conversationId: string | null) {
  return postJSON<ProposeResponse>("/api/propose", {
    request_text: requestText,
    conversation_id: conversationId,
  });
}

export function confirm(requestId: string) {
  return postJSON<ConfirmResponse>("/api/confirm", { request_id: requestId });
}

export function cancelOrders(requestId: string) {
  return postJSON<ConfirmResponse>("/api/cancel", { request_id: requestId });
}

export async function getPortfolio(): Promise<Portfolio> {
  const res = await fetch("/api/portfolio");
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

export async function listRequests(): Promise<RequestSummary[]> {
  const res = await fetch("/api/requests");
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

export async function getRequest(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`/api/requests/${id}`);
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}
