import { useState } from "react";
import { Lock } from "lucide-react";
import { api, auth } from "../api.js";

export default function Login({ onSuccess }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!password || busy) return;

    setBusy(true);
    setError(null);

    try {
      const data = await api.login(password);
      auth.setToken(data.token);
      setPassword("");
      onSuccess();
    } catch (err) {
      const status = err.response?.status;
      if (status === 401) setError("Password ghalat hai.");
      else if (status === 429)
        setError("Bohat zyada ghalat koshishen. 15 minute baad try karein.");
      else if (status === 503)
        setError("Server par dashboard login configure nahi hai.");
      else setError("Backend tak pohanch nahi saka.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <form
        onSubmit={submit}
        className="card"
        style={{ width: "100%", maxWidth: 360, padding: 26 }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 6,
          }}
        >
          <Lock size={18} />
          <h2
            style={{
              margin: 0,
              fontFamily: "var(--font-display)",
              color: "var(--navy-deep)",
            }}
          >
            RH Front Desk
          </h2>
        </div>

        <p style={{ color: "var(--ink-soft)", marginTop: 0 }}>
          Dashboard dekhne ke liye password dalein.
        </p>

        <input
          type="password"
          autoFocus
          autoComplete="current-password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{
            width: "100%",
            padding: "9px 11px",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            fontSize: 14,
            marginBottom: 12,
          }}
        />

        {error && (
          <div
            style={{
              color: "var(--thread-red)",
              fontSize: 12.5,
              marginBottom: 12,
            }}
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          className="btn btn-primary"
          disabled={busy || !password}
          style={{ width: "100%", padding: "9px 0" }}
        >
          {busy ? "Checking…" : "Login"}
        </button>
      </form>
    </div>
  );
}