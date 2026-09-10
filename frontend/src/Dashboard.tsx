import { useEffect, useState } from "react";
import { getPortfolio, type BalancePoint, type Portfolio } from "./api";

const COLORS = ["#34d399", "#2b9c74", "#d6b34a", "#4ade80", "#2dd4bf", "#a3e635", "#7dd3fc"];
const CASH = "#33413a";

function money(s: string): string {
  return "$" + Number(s).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

// Portfolio dashboard (D24/G): allocation donut + equity trendline, from GET /api/portfolio.
export function Dashboard() {
  const [pf, setPf] = useState<Portfolio | null>(null);
  const [error, setError] = useState(false);
  const [hi, setHi] = useState<number | null>(null);

  useEffect(() => {
    getPortfolio()
      .then(setPf)
      .catch(() => setError(true));
  }, []);

  if (error)
    return (
      <div className="dashboard">
        <div className="dash-card">
          <h2>Allocation</h2>
          <div className="dash-empty">Couldn't load portfolio.</div>
        </div>
      </div>
    );
  if (!pf) return null;

  const holdings = pf.holdings.map((h, i) => ({
    ...h,
    color: h.symbol === "CASH" ? CASH : COLORS[i % COLORS.length],
  }));

  let acc = 0;
  const stops: string[] = [];
  for (const h of holdings) {
    const p = Number(h.pct);
    stops.push(`${h.color} ${acc}% ${acc + p}%`);
    acc += p;
  }
  const gradient = `conic-gradient(${stops.join(", ")})`;
  const center =
    hi == null
      ? { big: money(pf.equity), label: "equity" }
      : { big: `${Math.round(Number(holdings[hi].pct))}%`, label: holdings[hi].symbol };

  return (
    <div className="dashboard">
      <div className="dash-card">
        <h2>Allocation</h2>
        <div className="dash-sub">current holdings, % of equity</div>
        {holdings.length === 0 ? (
          <div className="dash-empty">No holdings yet.</div>
        ) : (
          <div className="alloc">
            <div className="donut" style={{ background: gradient }}>
              <div className="donut-mid">
                <b>{center.big}</b>
                <span>{center.label}</span>
              </div>
            </div>
            <div className="legend">
              {holdings.map((h, i) => (
                <div className="legrow" key={h.symbol} onMouseEnter={() => setHi(i)} onMouseLeave={() => setHi(null)}>
                  <span className="dot" style={{ background: h.color }} />
                  <span className="sym">{h.symbol}</span>
                  <span className="pct">{Math.round(Number(h.pct))}%</span>
                  <span className="val">{money(h.value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="dash-card trend">
        <h2>Balance</h2>
        <div className="dash-sub">equity, recent history</div>
        <Trend balance={pf.balance} equity={pf.equity} />
      </div>
    </div>
  );
}

function Trend({ balance, equity }: { balance: BalancePoint[]; equity: string }) {
  if (balance.length < 2) return <div className="dash-empty">Not enough history yet.</div>;

  const vals = balance.map((b) => Number(b.equity));
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const W = 320;
  const H = 96;
  const pad = 6;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * W;
    const y = H - pad - ((v - min) / span) * (H - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const line = pts.map((p, i) => (i === 0 ? "M" : "L") + p).join(" ");
  const area = `${line} L${W},${H} L0,${H} Z`;
  const base = vals[0] || 1;
  const chg = ((vals[vals.length - 1] - vals[0]) / base) * 100;
  const up = chg >= 0;

  return (
    <>
      <div className="trend-head">
        <span className="trend-big">{money(equity)}</span>
        <span className={`trend-chg ${up ? "up" : "down"}`}>
          {up ? "+" : ""}
          {chg.toFixed(1)}%
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#34d399" stopOpacity="0.13" />
            <stop offset="1" stopColor="#34d399" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#tg)" />
        <path className="line" d={line} fill="none" stroke="#34d399" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
      </svg>
    </>
  );
}
