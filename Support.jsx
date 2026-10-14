import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Support() {
  const [escalations, setEscalations] = useState(null);
  const [loading, setLoading] = useState(true);
  const [resolvingId, setResolvingId] = useState(null);

  const [replyOpenId, setReplyOpenId] = useState(null);
  const [replyText, setReplyText] = useState("");
  const [sendingReply, setSendingReply] = useState(false);
  const [replyFeedback, setReplyFeedback] = useState(null);

  function load() {
    setLoading(true);
    api
      .escalations()
      .then((data) => setEscalations(data.escalations))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function resolve(sessionId) {
    setResolvingId(sessionId);
    try {
      await api.resolveSupport(sessionId);
      setEscalations((prev) => prev.filter((e) => e.session_id !== sessionId));
    } finally {
      setResolvingId(null);
    }
  }

  function toggleReply(sessionId) {
    if (replyOpenId === sessionId) {
      setReplyOpenId(null);
      setReplyText("");
      setReplyFeedback(null);
      return;
    }
    setReplyOpenId(sessionId);
    setReplyText("");
    setReplyFeedback(null);
  }

  async function sendReply(sessionId) {
    const message = replyText.trim();
    if (!message) return;

    setSendingReply(true);
    setReplyFeedback(null);

    try {
      const result = await api.sendHumanReply(sessionId, message);

      setReplyFeedback(
        result.sent_over_whatsapp
          ? "Sent over WhatsApp."
          : "Saved to conversation (not a WhatsApp session, so nothing was sent over WhatsApp)."
      );

      setReplyText("");
    } catch {
      setReplyFeedback("Could not send — please try again.");
    } finally {
      setSendingReply(false);
    }
  }

  return (
    <div className="card">
      <div className="card-head">
        <h2>Escalations</h2>
        <span className="hint">
          {escalations ? `${escalations.length} waiting on a person` : ""}
        </span>
      </div>
      <div className="card-body" style={{ padding: "6px 0 10px" }}>
        {loading && <div className="loading-row">Reading the ledger…</div>}

        {!loading && escalations && escalations.length === 0 && (
          <div className="empty">Nothing waiting on a person right now.</div>
        )}

        {!loading && escalations && escalations.length > 0 && (
          <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Session</th>
                <th>Issue</th>
                <th>Order ref</th>
                <th>Complaints</th>
                <th>Reason</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {escalations.map((e) => (
                <>
                  <tr key={e.session_id}>
                    <td className="num">{e.session_id.slice(0, 14)}</td>
                    <td style={{ textTransform: "capitalize" }}>
                      {e.issue_type || "unclear"}
                    </td>
                    <td className="num">{e.order_reference || "—"}</td>
                    <td className="num">{e.complaint_count}</td>
                    <td>
                      <span className="pill pill-red">
                        {(e.escalation_reason || "").replaceAll("_", " ") ||
                          "flagged"}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                        <button
                          className="btn"
                          onClick={() => toggleReply(e.session_id)}
                        >
                          {replyOpenId === e.session_id ? "Cancel" : "Reply"}
                        </button>
                        <button
                          className="btn btn-primary"
                          disabled={resolvingId === e.session_id}
                          onClick={() => resolve(e.session_id)}
                        >
                          {resolvingId === e.session_id
                            ? "Resolving…"
                            : "Resolve"}
                        </button>
                      </div>
                    </td>
                  </tr>

                  {replyOpenId === e.session_id && (
                    <tr key={e.session_id + "-reply"}>
                      <td colSpan={6} style={{ background: "var(--surface-sunk)" }}>
                        <div
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            gap: 8,
                            padding: "10px 4px",
                          }}
                        >
                          <textarea
                            value={replyText}
                            onChange={(ev) => setReplyText(ev.target.value)}
                            placeholder="Type your reply to the customer…"
                            rows={3}
                            style={{
                              width: "100%",
                              resize: "vertical",
                              border: "1px solid var(--border)",
                              borderRadius: "var(--radius-sm)",
                              padding: "8px 10px",
                              fontSize: 13,
                              fontFamily: "inherit",
                              background: "var(--surface)",
                              color: "var(--ink)",
                            }}
                          />

                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 10,
                            }}
                          >
                            <button
                              className="btn btn-primary"
                              disabled={sendingReply || !replyText.trim()}
                              onClick={() => sendReply(e.session_id)}
                            >
                              {sendingReply ? "Sending…" : "Send reply"}
                            </button>

                            {replyFeedback && (
                              <span
                                style={{
                                  fontSize: 12,
                                  color: "var(--ink-soft)",
                                }}
                              >
                                {replyFeedback}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}