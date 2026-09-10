import { useState } from "react";
import { confirm, propose, type ConfirmResponse, type ProposeResponse } from "./api";
import { ProposalView } from "./ProposalView";
import { ResultView } from "./ResultView";
import { History } from "./History";

// Minimal local UI (D24/G-1): type a request → see the proposal → confirm → result.
// Follow-ups reuse the conversation id (B-4). No auth/styling beyond functional (G-1 non-goals).
export default function App() {
  const [tab, setTab] = useState<"chat" | "history">("chat");
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

  return (
    <main className="app">
      <header>
        <h1>NL Portfolio Rebalancer</h1>
        <span className="paper-badge">paper only</span>
        <nav>
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
            Rebalance
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
              placeholder="e.g. make it 60/40 stocks and bonds, but keep $5,000 in cash"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={3}
            />
            <button type="submit" disabled={busy}>
              {busy ? "Thinking…" : outcome || result ? "Send follow-up" : "Propose"}
            </button>
          </form>

          {error && <p className="warning" role="alert">{error}</p>}
          {outcome && <ProposalView outcome={outcome} onConfirm={onConfirm} busy={busy} />}
          {result && <ResultView result={result} />}
        </>
      )}
    </main>
  );
}
