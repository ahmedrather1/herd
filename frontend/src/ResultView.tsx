import type { ConfirmResponse } from "./api";

// Renders the execution report (E-2) or a confirm-time block (re-validate / market-closed).
export function ResultView({ result }: { result: ConfirmResponse }) {
  const ok = result.status === "completed";
  const canceled = result.status === "canceled";
  const blocked = result.status === "revalidate" || result.status === "market_closed" || result.status === "nothing";
  const cls = ok || canceled ? "ok" : blocked ? "blocked" : "partial";
  const heading = ok ? "Done" : canceled ? "Canceled" : blocked ? "Held — not placed" : "Stopped";

  return (
    <section className={`panel result ${cls}`} role="status">
      <h2>{heading}</h2>
      <p>{result.message}</p>

      {result.total > 0 && (
        <p>
          Completed {result.completed} of {result.total}.
          {result.cash_remaining !== null && (
            <> ~${result.cash_remaining} in cash (pre-settlement).</>
          )}
        </p>
      )}

      {result.failure && <p className="warning">Failure: {result.failure}</p>}

      {result.revalidation_problems.length > 0 && (
        <ul>
          {result.revalidation_problems.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
      )}

      {result.submitted.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>Status</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {result.submitted.map((s, i) => (
              <tr key={i} className={s.status}>
                <td>{s.symbol}</td>
                <td>{s.side}</td>
                <td>{s.status}</td>
                <td>{s.order_id ?? s.reason ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
