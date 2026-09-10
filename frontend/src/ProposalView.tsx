import type { ProposeResponse } from "./api";

// Renders a propose outcome. A "proposal" shows the restatement + orders + current-vs-target
// with an explicit Confirm action (D1/D4); other outcomes explain themselves (D10/D-3).
export function ProposalView({
  outcome,
  onConfirm,
  onCancel,
  busy,
}: {
  outcome: ProposeResponse;
  onConfirm: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  if (outcome.status === "cancel") {
    const orders = outcome.open_orders;
    if (orders.length === 0) {
      return (
        <section className="panel" role="status">
          <h2>Nothing to cancel</h2>
          <p>{outcome.message}</p>
        </section>
      );
    }
    return (
      <section className="panel cancel" role="status">
        <h2>Cancel pending orders?</h2>
        <p>{outcome.message}</p>
        <table>
          <thead>
            <tr>
              <th>Side</th>
              <th>Symbol</th>
              <th>Amount</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o, i) => (
              <tr key={i} className={o.side}>
                <td>{o.side}</td>
                <td>{o.symbol}</td>
                <td>{o.notional !== null ? `$${o.notional}` : `${o.qty} sh`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="confirm">
          <button className="confirm-cancel" onClick={onCancel} disabled={busy}>
            {busy ? <span className="spinner on-danger" /> : "Cancel these orders"}
          </button>
        </div>
      </section>
    );
  }

  if (outcome.status === "clarify") {
    return (
      <section className="panel clarify" role="status">
        <h2>One question first</h2>
        <p>{outcome.message}</p>
      </section>
    );
  }

  if (outcome.status === "refuse" || outcome.status === "error" || outcome.status === "unavailable") {
    return (
      <section className="panel refuse" role="alert">
        <h2>{outcome.status === "unavailable" ? "Can't reach Alpaca" : "Can't do that"}</h2>
        <p>{outcome.message}</p>
        {outcome.problems.length > 0 && (
          <ul>
            {outcome.problems.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        )}
      </section>
    );
  }

  // status === "proposal"
  return (
    <section className="panel proposal">
      <h2>Proposed</h2>
      {outcome.restatement && <pre className="restatement">{outcome.restatement}</pre>}

      {outcome.market_warning && (
        <p className="warning" role="alert">
          ⚠️ {outcome.market_warning}
        </p>
      )}

      <h3>Orders ({outcome.orders.length})</h3>
      <table>
        <thead>
          <tr>
            <th>Side</th>
            <th>Symbol</th>
            <th>Amount</th>
            <th>Why</th>
          </tr>
        </thead>
        <tbody>
          {outcome.orders.map((o, i) => (
            <tr key={i} className={o.side}>
              <td>{o.side}</td>
              <td>{o.symbol}</td>
              <td>{o.notional !== null ? `$${o.notional}` : `${o.qty} sh`}</td>
              <td>{o.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {outcome.allocation && (
        <>
          <h3>Current vs. target (equity ${outcome.allocation.equity})</h3>
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Now</th>
                <th>Target</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              {outcome.allocation.rows.map((r) => (
                <tr key={r.symbol}>
                  <td>{r.symbol}</td>
                  <td>{r.current_pct}%</td>
                  <td>{r.target_pct}%</td>
                  <td>{Number(r.delta_value) >= 0 ? "+" : ""}${r.delta_value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {outcome.applied_constraints.length > 0 && (
        <p className="constraints">Constraints: {outcome.applied_constraints.join("; ")}</p>
      )}

      <button className="confirm" onClick={onConfirm} disabled={busy}>
        {busy ? <span className="spinner on-solid" /> : "Confirm & place orders"}
      </button>
    </section>
  );
}
