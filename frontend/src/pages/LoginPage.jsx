import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import api from "../api";

// Password rules — must match backend validators in auth.py
const PASSWORD_RULES = [
  { id: "length",    label: "At least 12 characters",          test: p => p.length >= 12 },
  { id: "upper",     label: "One uppercase letter (A–Z)",       test: p => /[A-Z]/.test(p) },
  { id: "lower",     label: "One lowercase letter (a–z)",       test: p => /[a-z]/.test(p) },
  { id: "digit",     label: "One number (0–9)",                 test: p => /\d/.test(p) },
  { id: "special",   label: "One special character (!@#$%…)",   test: p => /[!@#$%^&*(),.?":{}|<>\[\]\\/\-_+=]/.test(p) },
];

function PasswordStrength({ password }) {
  if (!password) return null;
  const passed = PASSWORD_RULES.filter(r => r.test(password)).length;
  const pct = (passed / PASSWORD_RULES.length) * 100;
  const color = pct <= 40 ? "#e74c3c" : pct <= 79 ? "#f39c12" : "#2ecc71";
  const label = pct <= 40 ? "Weak" : pct <= 79 ? "Almost there" : "Strong";

  return (
    <div style={{ marginTop: 6, marginBottom: 10 }}>
      {/* Bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <div style={{ flex: 1, height: 4, borderRadius: 4, background: "var(--border, #e0e0e0)" }}>
          <div style={{
            height: "100%", borderRadius: 4, background: color,
            width: `${pct}%`, transition: "width 0.3s, background 0.3s"
          }} />
        </div>
        <span style={{ fontSize: 11, color, fontWeight: 600, minWidth: 72, textAlign: "right" }}>{label}</span>
      </div>
      {/* Checklist */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "3px 12px" }}>
        {PASSWORD_RULES.map(rule => {
          const ok = rule.test(password);
          return (
            <div key={rule.id} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12,
              color: ok ? "#2ecc71" : "var(--text3, #999)", transition: "color 0.2s" }}>
              <span style={{ fontSize: 11, fontWeight: 700 }}>{ok ? "✓" : "○"}</span>
              {rule.label}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function LoginPage() {
  const [tab, setTab] = useState("login"); // "login" | "register" | "forgot"
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotSent, setForgotSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [regError, setRegError] = useState("");
  const [signupsEnabled, setSignupsEnabled] = useState(null);
  const { login, register } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/api/auth/signup-enabled")
      .then(({ data }) => setSignupsEnabled(data.enabled))
      .catch(() => setSignupsEnabled(true));
  }, []);

  useEffect(() => {
    if (signupsEnabled === false && tab === "register") setTab("login");
  }, [signupsEnabled]);

  // Clear error whenever the user edits the form
  useEffect(() => { setRegError(""); }, [form]);

  const handleAuth = async (e) => {
    e.preventDefault();
    setRegError("");

    // Client-side password check before hitting the server
    if (tab === "register") {
      const failing = PASSWORD_RULES.filter(r => !r.test(form.password));
      if (failing.length) {
        setRegError(failing.map(r => r.label).join(", "));
        return;
      }
    }

    setLoading(true);
    try {
      if (tab === "login") {
        await login(form.username, form.password);
      } else {
        await register(form.username, form.email, form.password);
      }
      navigate("/");
    } catch (err) {
      const detail = err.response?.data?.detail;
      // FastAPI validation errors come back as an array
      if (Array.isArray(detail)) {
        setRegError(detail.map(d => d.msg).join(" · "));
      } else {
        const msg = detail || "Authentication failed";
        if (tab === "register") {
          setRegError(msg);
        } else {
          toast.error(msg);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const handleForgot = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post("/api/auth/forgot-password", { email: forgotEmail });
    } catch (_) {
      // Swallow — always show success to avoid email enumeration
    } finally {
      setForgotSent(true);
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-bg" />
      <div className="auth-card">
        <div className="auth-logo">
          <div className="logo-mark">📰</div>
          <h1>NewsFlow</h1>
          <p>AI-powered news, personalized for you</p>
        </div>

        {/* ── Forgot password view ── */}
        {tab === "forgot" && (
          <>
            {forgotSent ? (
              <div style={{ textAlign: "center", padding: "8px 0 16px" }}>
                <div style={{ fontSize: 40, marginBottom: 12 }}>📬</div>
                <p style={{ color: "var(--text2)", fontSize: 15, lineHeight: 1.6 }}>
                  If that email is registered, a reset link is on its way.
                  Check your inbox (and spam folder).
                </p>
                <button
                  className="btn btn-primary"
                  style={{ width: "100%", justifyContent: "center", marginTop: 20, padding: "12px" }}
                  onClick={() => { setTab("login"); setForgotSent(false); setForgotEmail(""); }}
                >
                  Back to Sign In
                </button>
              </div>
            ) : (
              <>
                <p style={{ color: "var(--text3)", fontSize: 14, marginBottom: 16, lineHeight: 1.5 }}>
                  Enter your account email and we will send you a reset link.
                </p>
                <form onSubmit={handleForgot}>
                  <div className="form-group">
                    <label className="form-label">Email Address</label>
                    <input
                      className="form-input"
                      type="email"
                      placeholder="you@example.com"
                      value={forgotEmail}
                      onChange={e => setForgotEmail(e.target.value)}
                      required
                      autoFocus
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    style={{ width: "100%", justifyContent: "center", marginTop: 8, padding: "12px" }}
                    disabled={loading}
                  >
                    {loading ? "Sending..." : "Send Reset Link"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    style={{ width: "100%", justifyContent: "center", marginTop: 8 }}
                    onClick={() => setTab("login")}
                  >
                    Back to Sign In
                  </button>
                </form>
              </>
            )}
          </>
        )}

        {/* ── Login / Register view ── */}
        {tab !== "forgot" && (
          <>
            {signupsEnabled && (
              <div className="auth-tabs">
                <button
                  className={`auth-tab ${tab === "login" ? "active" : ""}`}
                  onClick={() => { setTab("login"); setRegError(""); }}
                >Sign In</button>
                <button
                  className={`auth-tab ${tab === "register" ? "active" : ""}`}
                  onClick={() => { setTab("register"); setRegError(""); }}
                >Create Account</button>
              </div>
            )}

            <form onSubmit={handleAuth}>
              <div className="form-group">
                <label className="form-label">Username</label>
                <input
                  className="form-input"
                  placeholder="your_username"
                  value={form.username}
                  onChange={e => setForm({ ...form, username: e.target.value })}
                  required
                  autoFocus
                />
              </div>

              {tab === "register" && (
                <div className="form-group">
                  <label className="form-label">Email</label>
                  <input
                    className="form-input"
                    type="email"
                    placeholder="you@example.com"
                    value={form.email}
                    onChange={e => setForm({ ...form, email: e.target.value })}
                    required
                  />
                </div>
              )}

              <div className="form-group">
                <label className="form-label">Password</label>
                <input
                  className="form-input"
                  type="password"
                  placeholder="••••••••"
                  value={form.password}
                  onChange={e => setForm({ ...form, password: e.target.value })}
                  required
                  style={regError ? { borderColor: "#e74c3c" } : {}}
                />
                {/* Live strength + checklist — only on register */}
                {tab === "register" && (
                  <PasswordStrength password={form.password} />
                )}
              </div>

              {/* Inline error banner */}
              {regError && (
                <div style={{
                  background: "#fdf0f0", border: "1px solid #f5c6cb", borderRadius: 8,
                  padding: "10px 14px", marginBottom: 12, fontSize: 13,
                  color: "#c0392b", lineHeight: 1.5
                }}>
                  {regError}
                </div>
              )}

              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: "100%", justifyContent: "center", marginTop: 4, padding: "12px" }}
                disabled={loading}
              >
                {loading ? "Please wait..." : tab === "login" ? "Sign In" : "Create Account"}
              </button>
            </form>

            {tab === "login" && (
              <div style={{ textAlign: "center", marginTop: 14 }}>
                <button
                  style={{ fontSize: 13, color: "var(--text3)", background: "none", border: "none",
                           cursor: "pointer", padding: "4px 0", textDecoration: "underline" }}
                  onClick={() => setTab("forgot")}
                >
                  Forgot your password?
                </button>
              </div>
            )}

            {tab === "register" && (
              <p style={{ fontSize: 12, color: "var(--text3)", textAlign: "center", marginTop: 12 }}>
                First registered user becomes admin
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
