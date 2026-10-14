import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { api } from "../api.js";
import {
  STATUS_LABEL,
  STATUS_PILL_CLASS,
  timeAgo,
} from "../format.js";

const STATUS_ORDER = [
  "confirmed",
  "processing",
  "shipped",
  "out_for_delivery",
  "delivered",
  "cancelled",
];

const BAR_COLOR = {
  confirmed: "#232e4d",
  processing: "#93641f",
  shipped: "#a1782f",
  out_for_delivery: "#a1782f",
  delivered: "#3c6e50",
  cancelled: "#9a3d38",
};

function isoDate(d) {
  return d.toISOString().slice(0, 10);
}

function todayIso() {
  return isoDate(new Date());
}

function yesterdayIso() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return isoDate(d);
}

function prettyDate(iso) {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export default function Overview({ analytics, onGoTo }) {
  const [dailyDate, setDailyDate] = useState(todayIso());
  const [daily, setDaily] = useState(null);
  const [dailyLoading, setDailyLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setDailyLoading(true);
    api
      .daily(dailyDate)
      .then((data) => {
        if (!cancelled) setDaily(data);
      })
      .finally(() => {
        if (!cancelled) setDailyLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dailyDate]);

  if (!analytics) {
    return <div className="loading-row">Reading the ledger…</div>;
  }

  const { conversations, orders, support, feedback, recent_orders } =
    analytics;

  const barData = STATUS_ORDER.map((status) => ({
    status,
    label: STATUS_LABEL[status],
    count: orders[status] || 0,
  }));

  const ratingCounts = [1, 2, 3, 4, 5].map(
    (n) => (feedback.ratings || []).filter((r) => Math.round(r) === n).length
  );
  const maxRatingCount = Math.max(1, ...ratingCounts);

  return (
    <>
      <section className="card" style={{ marginBottom: 18 }}>
        <div className="card-head">
          <h2>Daily snapshot</h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              className={"btn" + (dailyDate === todayIso() ? " btn-primary" : "")}
              onClick={() => setDailyDate(todayIso())}
            >
              Today
            </button>
            <button
              className={
                "btn" + (dailyDate === yesterdayIso() ? " btn-primary" : "")
              }
              onClick={() => setDailyDate(yesterdayIso())}
            >
              Yesterday
            </button>
            <input
              type="date"
              className="status-select"
              value={dailyDate}
              max={todayIso()}
              onChange={(e) => setDailyDate(e.target.value)}
            />
          </div>
        </div>
        <div className="card-body">
          {dailyLoading ? (
            <div className="loading-row">Counting the day's ledger…</div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(2, 1fr)",
                gap: 14,
              }}
            >
              <div className="mini-stat">
                <div className="label">
                  Conversations — {prettyDate(dailyDate)}
                </div>
                <div className="value num">{daily?.conversations ?? 0}</div>
              </div>
              <div className="mini-stat">
                <div className="label">
                  Orders placed — {prettyDate(dailyDate)}
                </div>
                <div className="value num">{daily?.orders ?? 0}</div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="hero-row">
        <div className="hero-stat">
          <div>
            <div className="label">Conversations handled</div>
            <div className="value num">{conversations.total}</div>
          </div>
          <div className="sub">{conversations.active} active right now</div>
        </div>

        <div className="mini-stat">
          <div className="label">Orders placed</div>
          <div className="value num">{orders.total}</div>
        </div>

        <div className="mini-stat">
          <div className="label">Delivered</div>
          <div className="value num">{orders.delivered || 0}</div>
          <div className="sub">
            of {orders.total} order{orders.total === 1 ? "" : "s"}
          </div>
        </div>

        <div className="mini-stat">
          <div className="label">Open escalations</div>
          <div className="value num">{support.active_escalations}</div>
          <div className="sub">of {support.total_sessions} support threads</div>
        </div>

        <div className="mini-stat">
          <div className="label">Average rating</div>
          <div className="value num">
            {feedback.average_rating ? feedback.average_rating.toFixed(1) : "—"}
          </div>
          <div className="sub">from {feedback.total} reviews</div>
        </div>
      </section>

      <section className="split-row">
        <div className="card">
          <div className="card-head">
            <h2>Orders by status</h2>
            <span className="hint">{orders.total} total</span>
          </div>
          <div className="card-body">
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={barData}
                  margin={{ top: 4, right: 4, bottom: 4, left: -18 }}
                >
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11, fill: "#565c68" }}
                    axisLine={{ stroke: "#ddd8c8" }}
                    tickLine={false}
                    interval={0}
                    angle={-18}
                    textAnchor="end"
                    height={48}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11, fill: "#565c68" }}
                    axisLine={false}
                    tickLine={false}
                    width={28}
                  />
                  <Tooltip
                    cursor={{ fill: "rgba(35,46,77,0.06)" }}
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 6,
                      border: "1px solid #ddd8c8",
                    }}
                  />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                    {barData.map((d) => (
                      <Cell key={d.status} fill={BAR_COLOR[d.status]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h2>Customer sentiment</h2>
            <span className="hint">{feedback.total} responses</span>
          </div>
          <div className="card-body">
            {feedback.total > 0 ? (
              <div className="rating-block">
                <div className="rating-number num">
                  {feedback.average_rating.toFixed(1)}
                </div>
                <div className="rating-bars">
                  {[5, 4, 3, 2, 1].map((n) => (
                    <div className="rating-bar-row" key={n}>
                      <span style={{ width: 10 }}>{n}</span>
                      <div className="rating-bar-track">
                        <div
                          className="rating-bar-fill"
                          style={{
                            width: `${
                              (ratingCounts[n - 1] / maxRatingCount) * 100
                            }%`,
                          }}
                        />
                      </div>
                      <span className="num" style={{ width: 18, textAlign: "right" }}>
                        {ratingCounts[n - 1]}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="empty">No feedback collected yet.</div>
            )}
          </div>
        </div>
      </section>

      <section className="split-row">
        <div className="card">
          <div className="card-head">
            <h2>Recent orders</h2>
            <button className="btn" onClick={() => onGoTo("orders")}>
              View all
            </button>
          </div>
          <div className="card-body" style={{ padding: "6px 0 10px" }}>
            {recent_orders && recent_orders.length > 0 ? (
              <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Product</th>
                    <th>Status</th>
                    <th>Placed</th>
                  </tr>
                </thead>
                <tbody>
                  {recent_orders.slice(0, 6).map((o) => (
                    <tr key={o.order_id}>
                      <td className="num">{o.order_id}</td>
                      <td>{o.product || "—"}</td>
                      <td>
                        <span
                          className={
                            "pill " +
                            (STATUS_PILL_CLASS[o.status] || "pill-navy")
                          }
                        >
                          {STATUS_LABEL[o.status] || o.status}
                        </span>
                      </td>
                      <td>{timeAgo(o.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            ) : (
              <div className="empty">No orders placed yet.</div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h2>Needs a human</h2>
            <button className="btn" onClick={() => onGoTo("support")}>
              View all
            </button>
          </div>
          <div className="card-body" style={{ padding: "6px 0 10px" }}>
            {analytics.active_escalations &&
            analytics.active_escalations.length > 0 ? (
              <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Session</th>
                    <th>Issue</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.active_escalations.slice(0, 6).map((e) => (
                    <tr key={e.session_id}>
                      <td className="num">{e.session_id.slice(0, 10)}</td>
                      <td style={{ textTransform: "capitalize" }}>
                        {e.issue_type || "unclear"}
                      </td>
                      <td>
                        <span className="pill pill-red">
                          {(e.escalation_reason || "").replaceAll("_", " ") ||
                            "flagged"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            ) : (
              <div className="empty">Nothing waiting on a person right now.</div>
            )}
          </div>
        </div>
      </section>
    </>
  );
}