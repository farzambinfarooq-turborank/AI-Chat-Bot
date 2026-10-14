import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { api, FOLLOW_UP_STAGES, digitsOnly } from "../api.js";
import { STAGE_LABEL, timeAgo } from "../format.js";

export default function FollowUps() {
  const [rows, setRows] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [sendingKey, setSendingKey] = useState(null);
  const [query, setQuery] = useState("");

  function load() {
    setLoading(true);
    api
      .followUps()
      .then((data) => setRows(data.follow_ups))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function runDue() {
    setRunning(true);
    try {
      await api.runDueFollowUps();
      load();
    } finally {
      setRunning(false);
    }
  }

  async function sendStage(orderId, stage) {
    const key = orderId + stage;
    setSendingKey(key);
    try {
      await api.sendFollowUp(orderId, stage);
      load();
    } finally {
      setSendingKey(null);
    }
  }

  const filteredRows = useMemo(() => {
    if (!rows) return [];

    const trimmed = query.trim();
    if (!trimmed) return rows;

    const queryDigits = digitsOnly(trimmed);
    const lowerQuery = trimmed.toLowerCase();

    return rows.filter((r) => {
      if (queryDigits && digitsOnly(r.order_id || "").includes(queryDigits)) {
        return true;
      }
      return (r.order_id || "").toLowerCase().includes(lowerQuery);
    });
  }, [rows, query]);

  return (
    <div className="card">
      <div className="card-head">
        <h2>Follow-ups</h2>
        <button className="btn btn-primary" onClick={runDue} disabled={running}>
          {running ? "Sending due…" : "Send everything due"}
        </button>
      </div>

      <div style={{ padding: "10px 18px 0" }}>
        <div className="search-box">
          <Search size={14} />
          <input
            type="text"
            placeholder="Search by order ID"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="card-body" style={{ padding: "6px 0 10px" }}>
        {loading && <div className="loading-row">Reading the ledger…</div>}

        {!loading && rows && rows.length === 0 && (
          <div className="empty">No delivered orders to follow up on yet.</div>
        )}

        {!loading && rows && rows.length > 0 && filteredRows.length === 0 && (
          <div className="empty">No follow-up matches that search.</div>
        )}

        {!loading && filteredRows.length > 0 && (
          <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>Delivered</th>
                <th>Delivery msg</th>
                <th>Feedback</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((r) => (
                <tr key={r.order_id}>
                  <td className="num">{r.order_id}</td>
                  <td>{timeAgo(r.delivered_at)}</td>
                  {FOLLOW_UP_STAGES.map((stage) => {
                    const s = r.stages?.[stage];
                    const key = r.order_id + stage;
                    return (
                      <td key={stage}>
                        {s?.sent ? (
                          <span
                            className={
                              "pill " +
                              (s.rating != null
                                ? s.rating >= 4
                                  ? "pill-green"
                                  : s.rating <= 2
                                  ? "pill-red"
                                  : "pill-navy"
                                : "pill-navy")
                            }
                            title={s.response || ""}
                          >
                            sent {s.rating != null ? `· ${s.rating}★` : ""}
                          </span>
                        ) : (
                          <button
                            className="btn"
                            disabled={
                              !r.delivered_at || sendingKey === key
                            }
                            onClick={() => sendStage(r.order_id, stage)}
                          >
                            {sendingKey === key
                              ? "Sending…"
                              : `Send ${STAGE_LABEL[stage].toLowerCase()}`}
                          </button>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}