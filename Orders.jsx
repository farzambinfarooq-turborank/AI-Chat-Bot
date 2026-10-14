import { useEffect, useMemo, useState } from "react";
import { Search, Trash2 } from "lucide-react";
import { api, ORDER_STATUSES, digitsOnly } from "../api.js";
import { STATUS_LABEL, timeAgo } from "../format.js";

export default function Orders() {
  const [filter, setFilter] = useState("");
  const [orders, setOrders] = useState(null);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [query, setQuery] = useState("");

  function load(status) {
    setLoading(true);
    api
      .orders(status || undefined)
      .then((data) => setOrders(data.orders))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load(filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  async function changeStatus(orderId, status) {
    setSavingId(orderId);
    try {
      await api.updateOrderStatus(orderId, status);
      setOrders((prev) =>
        prev.map((o) => (o.order_id === orderId ? { ...o, status } : o))
      );
    } finally {
      setSavingId(null);
    }
  }

  async function handleDelete(orderId) {
    if (!window.confirm(`Order ${orderId} permanently delete kar dein?`)) {
      return;
    }

    setDeletingId(orderId);
    try {
      await api.deleteOrder(orderId);
      setOrders((prev) => prev.filter((o) => o.order_id !== orderId));
    } finally {
      setDeletingId(null);
    }
  }

  const filteredOrders = useMemo(() => {
    if (!orders) return [];

    const trimmed = query.trim();
    if (!trimmed) return orders;

    const queryDigits = digitsOnly(trimmed);
    const lowerQuery = trimmed.toLowerCase();

    return orders.filter((o) => {
      if (queryDigits && digitsOnly(o.phone || "").includes(queryDigits)) {
        return true;
      }
      return [o.order_id, o.name, o.product, o.city, o.address]
        .filter(Boolean)
        .some((field) => field.toLowerCase().includes(lowerQuery));
    });
  }, [orders, query]);

  return (
    <div className="card">
      <div className="card-head">
        <h2>Orders</h2>
        <select
          className="status-select"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          {ORDER_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </div>

      <div style={{ padding: "10px 18px 0" }}>
        <div className="search-box">
          <Search size={14} />
          <input
            type="text"
            placeholder="Search by order ID, name, phone, product, or city"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="card-body" style={{ padding: "6px 0 10px" }}>
        {loading && <div className="loading-row">Reading the ledger…</div>}

        {!loading && (!orders || orders.length === 0) && (
          <div className="empty">No orders match this filter.</div>
        )}

        {!loading && orders && orders.length > 0 && filteredOrders.length === 0 && (
          <div className="empty">No orders match that search.</div>
        )}

        {!loading && filteredOrders.length > 0 && (
          <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>Customer</th>
                <th>Product</th>
                <th>Address</th>
                <th>City</th>
                <th>Placed</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filteredOrders.map((o) => (
                <tr key={o.order_id}>
                  <td className="num">{o.order_id}</td>
                  <td>
                    {o.name || "—"}
                    <div style={{ fontSize: 11.5, color: "var(--ink-soft)" }}>
                      {o.phone || ""}
                    </div>
                  </td>
                  <td>
                    {o.product || "—"}
                    <div style={{ fontSize: 11.5, color: "var(--ink-soft)" }}>
                      {[o.size, o.color, o.quantity && `x${o.quantity}`]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                  </td>
                  <td
                    style={{
                      maxWidth: 220,
                      cursor: o.address ? "pointer" : "default",
                    }}
                    title={o.address ? "Click to copy" : ""}
                    onClick={() => {
                      if (o.address) navigator.clipboard?.writeText(o.address);
                    }}
                  >
                    {o.address || "—"}
                  </td>
                  <td>{o.city || "—"}</td>
                  <td>{timeAgo(o.created_at)}</td>
                  <td>
                    <select
                      className="status-select"
                      value={o.status}
                      disabled={savingId === o.order_id}
                      onChange={(e) => changeStatus(o.order_id, e.target.value)}
                    >
                      {ORDER_STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {STATUS_LABEL[s]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <button
                      className="icon-btn"
                      title="Delete order"
                      disabled={deletingId === o.order_id}
                      onClick={() => handleDelete(o.order_id)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
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