import { useEffect, useMemo, useState } from "react";
import { Search, Trash2 } from "lucide-react";
import { api, digitsOnly } from "../api.js";
import { STATUS_LABEL, STATUS_PILL_CLASS } from "../format.js";

// A conversation counts as "recent" (dark highlight) if its last
// message was within this many hours — matches the "1 din baad
// normal" requirement (24 hours).
const RECENT_HOURS = 24;

function isRecent(isoTimestamp) {
  if (!isoTimestamp) return false;
  const then = new Date(isoTimestamp).getTime();
  if (Number.isNaN(then)) return false;
  const hours = (Date.now() - then) / (1000 * 60 * 60);
  return hours >= 0 && hours < RECENT_HOURS;
}

export default function Conversations({ list, loading, onRefresh }) {
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => {
    if (!selected && list && list.length > 0) {
      setSelected(list[0].session_id);
    }
  }, [list, selected]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setDetailLoading(true);
    api
      .conversationDetail(selected)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const filteredList = useMemo(() => {
    if (!list) return [];

    const trimmed = query.trim();
    if (!trimmed) return list;

    const queryDigits = digitsOnly(trimmed);
    const lowerQuery = trimmed.toLowerCase();

    return list.filter((c) => {
      // Phone-number style search (e.g. "+92 314 3050110") — ignores
      // spaces, "+", and the "whatsapp:" prefix entirely.
      if (queryDigits && digitsOnly(c.session_id).includes(queryDigits)) {
        return true;
      }
      // Fallback: plain text match against the session id or last
      // message, in case the owner searches by something else.
      return (
        c.session_id.toLowerCase().includes(lowerQuery) ||
        (c.last_message || "").toLowerCase().includes(lowerQuery)
      );
    });
  }, [list, query]);

  async function handleDelete(sessionId, event) {
    event.stopPropagation();

    if (!window.confirm("Yeh conversation permanently delete kar dein?")) {
      return;
    }

    setDeletingId(sessionId);
    try {
      await api.deleteConversation(sessionId);

      if (selected === sessionId) {
        setSelected(null);
        setDetail(null);
      }

      onRefresh?.();
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) return <div className="loading-row">Reading the ledger…</div>;

  if (!list || list.length === 0) {
    return (
      <div className="card">
        <div className="card-body">
          <div className="empty">No conversations have come in yet.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="convo-layout">
      <div className="card">
        <div className="card-head">
          <h2>Sessions</h2>
          <span className="hint">
            {filteredList.length}
            {filteredList.length !== list.length ? ` / ${list.length}` : ""}
          </span>
        </div>

        <div style={{ padding: "0 14px 10px" }}>
          <div className="search-box">
            <Search size={14} />
            <input
              type="text"
              placeholder="Search by phone number, e.g. +92 314 3050110"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>

        <div style={{ maxHeight: 580, overflowY: "auto" }}>
          {filteredList.length === 0 && (
            <div className="empty">No conversation matches that number.</div>
          )}

          {filteredList.map((c) => (
            <div
              key={c.session_id}
              className={
                "convo-list-item" +
                (c.session_id === selected ? " active" : "") +
                (isRecent(c.last_message_at) ? " recent" : "")
              }
              onClick={() => setSelected(c.session_id)}
            >
              <div className="top-line">
                <span className="num">{c.session_id.slice(0, 12)}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {c.message_count} msgs
                  <button
                    className="icon-btn"
                    title="Delete conversation"
                    disabled={deletingId === c.session_id}
                    onClick={(e) => handleDelete(c.session_id, e)}
                  >
                    <Trash2 size={13} />
                  </button>
                </span>
              </div>
              <div className="snippet">{c.last_message || "—"}</div>
              <div style={{ marginTop: 6, display: "flex", gap: 6 }}>
                {c.order_id && (
                  <span
                    className={
                      "pill " + (STATUS_PILL_CLASS[c.order_status] || "pill-navy")
                    }
                  >
                    {STATUS_LABEL[c.order_status] || c.order_status}
                  </span>
                )}
                {c.escalated && <span className="pill pill-red">escalated</span>}
                {!c.order_id && c.buying_intent && (
                  <span className="pill pill-brass">buying intent</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>{selected ? selected.slice(0, 16) : "Thread"}</h2>
        </div>
        <div className="card-body">
          {!selected && (
            <div className="empty">Select a conversation to view it.</div>
          )}

          {selected && detailLoading && (
            <div className="loading-row">Loading thread…</div>
          )}

          {selected && !detailLoading && detail && detail.found && (
            <>
              <div className="thread-meta">
                {detail.order_state?.product && (
                  <span className="pill pill-navy">
                    {detail.order_state.product}
                  </span>
                )}
                {detail.order_state?.order_id && (
                  <span
                    className={
                      "pill " +
                      (STATUS_PILL_CLASS[detail.order_state.status] ||
                        "pill-navy")
                    }
                  >
                    {STATUS_LABEL[detail.order_state.status] ||
                      detail.order_state.status}
                  </span>
                )}
                {detail.support_state?.issue_type && (
                  <span className="pill pill-amber">
                    {detail.support_state.issue_type}
                  </span>
                )}
                {detail.support_state?.escalated && (
                  <span className="pill pill-red">escalated</span>
                )}
              </div>

              <div className="thread">
                {detail.messages.map((m, i) => (
                  <div
                    key={i}
                    className={
                      "bubble " + (m.role === "user" ? "user" : "assistant")
                    }
                  >
                    {m.content}
                  </div>
                ))}
              </div>
            </>
          )}

          {selected && !detailLoading && detail && !detail.found && (
            <div className="empty">Conversation not found.</div>
          )}
        </div>
      </div>
    </div>
  );
}