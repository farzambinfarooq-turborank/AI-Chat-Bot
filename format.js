export function timeAgo(iso) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diffMs = Date.now() - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function clock(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export const STATUS_LABEL = {
  confirmed: "Confirmed",
  processing: "Processing",
  shipped: "Shipped",
  out_for_delivery: "Out for delivery",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

export const STATUS_PILL_CLASS = {
  confirmed: "pill-navy",
  processing: "pill-amber",
  shipped: "pill-brass",
  out_for_delivery: "pill-brass",
  delivered: "pill-green",
  cancelled: "pill-red",
};

// Only 2 stages now — review_request removed (folded into the
// feedback thank-you message instead of being a separate stage).
export const STAGE_LABEL = {
  delivery_confirmation: "Delivery confirmation",
  feedback_request: "Feedback request",
};