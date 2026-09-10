import { useState } from "react";
import { cancelOrders, confirm, propose, type ConfirmResponse, type ProposeResponse } from "./api";
import { Dashboard } from "./Dashboard";
import { ProposalView } from "./ProposalView";
import { ResultView } from "./ResultView";
import { History } from "./History";

// Minimal local UI (D24/G-1): type a request → propose → confirm → result, with a portfolio
// dashboard (allocation + balance) and "cancel that" for pending orders (D62). Follow-ups
// reuse the conversation id (B-4).
export default function App() {
  const [tab, setTab] = useState<"portfolio" | "history">("portfolio");
  const [text, setText] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<ProposeResponse | null>(null);
  const [result, setResult] = useState<ConfirmResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onPropose(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const resp = await propose(text, conversationId);
      setOutcome(resp);
      if (resp.conversation_id) setConversationId(resp.conversation_id);
      setText("");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onConfirm() {
    if (!outcome?.request_id) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await confirm(outcome.request_id));
      setOutcome(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onCancel() {
    if (!outcome?.request_id) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await cancelOrders(outcome.request_id));
      setOutcome(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app">
      <header>
        <h1>rebalancer</h1>
        <span className="paper-badge">paper</span>
        <nav>
          <button className={tab === "portfolio" ? "active" : ""} onClick={() => setTab("portfolio")}>
            Portfolio
          </button>
          <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>
            History
          </button>
        </nav>
      </header>

      {tab === "history" ? (
        <History />
      ) : (
        <>
          <form onSubmit={onPropose}>
            <textarea
              aria-label="request"
              placeholder="make it 60/40 stocks and bonds, but keep $5,000 in cash — or 'cancel that'"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={2}
            />
            <button type="submit" disabled={busy}>
              {busy ? "…" : outcome || result ? "Send" : "Propose"}
            </button>
          </form>

          {!outcome && !result && <Dashboard />}
          {error && (
            <p className="warning" role="alert">
              {error}
            </p>
          )}
          {outcome && <ProposalView outcome={outcome} onConfirm={onConfirm} onCancel={onCancel} busy={busy} />}
          {result && <ResultView result={result} />}
        </>
      )}
    </main>
  );
}
