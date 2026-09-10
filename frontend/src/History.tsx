import { useEffect, useState } from "react";
import { getRequest, listRequests, type RequestSummary } from "./api";

// The viewable audit log in the UI (G-2/F-2): browse past requests and drill into one.
export function History() {
  const [rows, setRows] = useState<RequestSummary[]>([]);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRequests().then(setRows).catch((e) => setError(String(e)));
  }, []);

  async function open(id: string) {
    try {
      setDetail(await getRequest(id));
    } catch (e) {
      setError(String(e));
    }
  }

  if (error) return <p className="warning">{error}</p>;

  return (
    <div className="history">
      <h2>History</h2>
      {rows.length === 0 && <p>No requests yet.</p>}
      <ul className="request-list">
        {rows.map((r) => (
          <li key={r.request_id}>
            <button className="link" onClick={() => open(r.request_id)}>
              <span className={`status-tag ${r.status}`}>{r.status}</span> {r.raw_text}
            </button>
          </li>
        ))}
      </ul>
      {detail && (
        <pre className="detail" aria-label="request detail">
          {JSON.stringify(detail, null, 2)}
        </pre>
      )}
    </div>
  );
}
