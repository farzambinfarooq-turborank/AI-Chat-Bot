import { useCallback, useEffect, useState } from "react";
import { LogOut, Menu, RefreshCw } from "lucide-react";
import Sidebar from "./components/Sidebar.jsx";
import Overview from "./pages/Overview.jsx";
import Conversations from "./pages/Conversations.jsx";
import Orders from "./pages/Orders.jsx";
import Support from "./pages/Support.jsx";
import FollowUps from "./pages/FollowUps.jsx";
import Login from "./pages/Login.jsx";
import { api, auth } from "./api.js";
import { clock } from "./format.js";

const TITLES = {
  overview: "Overview",
  conversations: "Conversations",
  orders: "Orders",
  support: "Support",
  followups: "Follow-ups",
};

function Dashboard({ onLogout }) {
  const [tab, setTab] = useState("overview");
  const [analytics, setAnalytics] = useState(null);
  const [conversationList, setConversationList] = useState(null);
  const [convLoading, setConvLoading] = useState(true);
  const [lastLoaded, setLastLoaded] = useState(null);
  const [error, setError] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const refresh = useCallback(() => {
    setError(null);
    Promise.all([
      api.analytics().then(setAnalytics),
      api
        .conversations()
        .then((d) => setConversationList(d.conversations))
        .finally(() => setConvLoading(false)),
    ])
      .then(() => setLastLoaded(new Date().toISOString()))
      .catch(() => setError("Could not reach the backend at :8000."));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, [refresh]);

  // Close the mobile drawer automatically if the viewport grows
  // back to desktop size while it's open.
  useEffect(() => {
    function handleResize() {
      if (window.innerWidth > 980) setMenuOpen(false);
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const counts = analytics
    ? {
        escalations: analytics.support.active_escalations,
        followUps: analytics.follow_ups.awaiting_feedback,
      }
    : {};

  return (
    <div className="shell">
      <Sidebar
        active={tab}
        onChange={setTab}
        counts={counts}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />

      <main className="main">
        <div className="topbar">
          <div className="topbar-left">
            <button
              className="menu-toggle"
              aria-label="Open menu"
              onClick={() => setMenuOpen(true)}
            >
              <Menu size={18} />
            </button>
            <h1>{TITLES[tab]}</h1>
          </div>

          <div className="updated">
            {error ? (
              <span style={{ color: "var(--thread-red)" }}>{error}</span>
            ) : (
              <span className="updated-text">
                Last checked {lastLoaded ? clock(lastLoaded) : "…"}
              </span>
            )}
            <button onClick={refresh} title="Refresh">
              <RefreshCw size={12} style={{ verticalAlign: -1, marginRight: 5 }} />
              <span className="refresh-label">Refresh</span>
            </button>
            <button onClick={onLogout} title="Logout">
              <LogOut size={12} style={{ verticalAlign: -1, marginRight: 5 }} />
              <span className="refresh-label">Logout</span>
            </button>
          </div>
        </div>

        {tab === "overview" && (
          <Overview analytics={analytics} onGoTo={setTab} />
        )}
        {tab === "conversations" && (
          <Conversations
            list={conversationList}
            loading={convLoading}
            onRefresh={refresh}
          />
        )}
        {tab === "orders" && <Orders />}
        {tab === "support" && <Support />}
        {tab === "followups" && <FollowUps />}
      </main>
    </div>
  );
}

export default function App() {
  const [loggedIn, setLoggedIn] = useState(Boolean(auth.getToken()));

  // api.js fires this when the server answers 401 (token expired/invalid).
  useEffect(() => {
    const onExpired = () => setLoggedIn(false);
    window.addEventListener("rh-auth-expired", onExpired);
    return () => window.removeEventListener("rh-auth-expired", onExpired);
  }, []);

  if (!loggedIn) return <Login onSuccess={() => setLoggedIn(true)} />;

  return (
    <Dashboard
      onLogout={() => {
        auth.clear();
        setLoggedIn(false);
      }}
    />
  );
}