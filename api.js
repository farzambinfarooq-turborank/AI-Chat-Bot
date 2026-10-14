import axios from "axios";

export const API_BASE =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const client = axios.create({ baseURL: API_BASE, timeout: 15000 });

// Login token sirf sessionStorage mein rehta hai (tab band = logout).
const TOKEN_KEY = "rh_dashboard_token";

export const auth = {
  getToken: () => sessionStorage.getItem(TOKEN_KEY),
  setToken: (token) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

client.interceptors.request.use((config) => {
  const token = auth.getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      auth.clear();
      window.dispatchEvent(new Event("rh-auth-expired"));
    }
    return Promise.reject(error);
  }
);

export const api = {
  login: (password) =>
    axios.post(`${API_BASE}/auth/login`, { password }).then((r) => r.data),
  analytics: () => client.get("/dashboard/analytics").then((r) => r.data),
  summary: () => client.get("/dashboard/summary").then((r) => r.data),
  daily: (date) =>
    client
      .get("/dashboard/daily", { params: date ? { date } : {} })
      .then((r) => r.data),

  conversations: () =>
    client.get("/dashboard/conversations").then((r) => r.data),
  conversationDetail: (sessionId) =>
    client
      .get(`/dashboard/conversations/${encodeURIComponent(sessionId)}`)
      .then((r) => r.data),
  deleteConversation: (sessionId) =>
    client
      .delete(`/session/${encodeURIComponent(sessionId)}`)
      .then((r) => r.data),

  orders: (status) =>
    client
      .get("/dashboard/orders", { params: status ? { status } : {} })
      .then((r) => r.data),
  updateOrderStatus: (orderId, status) =>
    client
      .post(`/order/${encodeURIComponent(orderId)}/status`, { status })
      .then((r) => r.data),
  deleteOrder: (orderId) =>
    client
      .delete(`/order/${encodeURIComponent(orderId)}`)
      .then((r) => r.data),

  escalations: () => client.get("/dashboard/escalations").then((r) => r.data),
  resolveSupport: (sessionId) =>
    client
      .post(`/session/${encodeURIComponent(sessionId)}/support/resolve`)
      .then((r) => r.data),
  sendHumanReply: (sessionId, message) =>
    client
      .post(`/session/${encodeURIComponent(sessionId)}/reply`, { message })
      .then((r) => r.data),

  followUps: () => client.get("/dashboard/follow-ups").then((r) => r.data),
  runDueFollowUps: () =>
    client.post("/follow-ups/run-due").then((r) => r.data),
  sendFollowUp: (orderId, stage) =>
    client
      .post(
        `/follow-ups/${encodeURIComponent(orderId)}/send/${encodeURIComponent(
          stage
        )}`
      )
      .then((r) => r.data),
};

export const ORDER_STATUSES = [
  "confirmed",
  "processing",
  "shipped",
  "out_for_delivery",
  "delivered",
  "cancelled",
];

// Only 2 stages now — the review ask lives inside the
// feedback_request thank-you reply, not a separate stage.
export const FOLLOW_UP_STAGES = [
  "delivery_confirmation",
  "feedback_request",
];

// Strips everything except digits, so phone-number search can match
// regardless of spaces, "+", or the "whatsapp:" session prefix.
export function digitsOnly(value) {
  return (value || "").replace(/\D/g, "");
}