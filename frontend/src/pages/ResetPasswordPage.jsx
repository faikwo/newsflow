import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import api from "../api";

const PASSWORD_RULES = [
  { id: "length",  label: "At least 12 characters",         test: p => p.length >= 12 },
  { id: "upper",   label: "One uppercase letter (A–Z)",      test: p => /[A-Z]/.test(p) },
  { id: "lower",   label: "One lowercase letter (a–z)",      test: p => /[a-z]/.test(p) },
  { id: "digit",   label: "One number (0–9)",                test: p => /\d/.test(p) },
  { id: "special", label: "One special character (!@#$%…)",  test: p => /[!@#$%^&*(),.?":{}|<>\[\]\\/\-_+=]/.test(p) },
];

function PasswordStrength({ password }) {
  if (!password) return null;
  const passed = PASSWORD_RULES.filter(r => r.test(password)).length;
  const pct = (passed / PASSWORD_RULES.length) * 100;
  const color = pct <= 40 ? "#e74c3c" : pct <= 79 ? "#f39c12" : "#2ecc71";
  const label = pct <= 40 ? "Weak" : pct <= 79 ? "Almost there" : "Strong";
  return (
    <div style={{ marginTop: 6, marginBottom: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <div style={{ flex: 1, height: 4, borderRadius: 4, background: "var(--border, #e0e0e0)" }}>
          <div style={{ height: "100%", borderRadius: 4, background: color,
            width: `${pct}%`, transition: "width 0.3s, background 0.3s" }} />
        </div>
        <span style={{ fontSize: 11, color, fontWeight: 600, minWidth: 72, textAlign: "right" }}>{label}</span>
      </div>
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

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    // Client-side checks first
    const failing = PASSWORD_RULES.filter(r => !r.test(password));
    if (failing.length) {
      setError(failing.map(r => r.label).join(", "));
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await api.post("/api/auth/reset-password", { token, password });
      setDone(true);
      toast.success("Password updated! You can now sign in.");
      setTimeout(() => navigate("/login"), 2500);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map(d => d.msg).join(" · "));
      } else {
        setError(detail || "Reset failed. The link may have expired.");
      }
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="auth-page">
        <div className="auth-bg" />
        <div className="auth-card">
          <div className="auth-logo">
            <div className="logo-mark">📰</div>
            <h1>NewsFlow</h1>
          </div>
          <p style={{ textAlign: "center", color: "var(--text3)", marginTop: 16 }}>
            Invalid reset link. Please request a new one from the login page.
          </p>
          <button className="btn btn-primary"
            style={{ width: "100%", justifyContent: "center", marginTop: 16 }}
            onClick={() => navigate("/login")}>
            Back to Sign In
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-bg" />
      <div className="auth-card">
        <div className="auth-logo">
          <div className="logo-mark">📰</div>
          <h1>NewsFlow</h1>
          <p>Choose a new password</p>
        </div>

        {done ? (
          <p style={{ textAlign: "center", color: "#2ecc71", marginTop: 16, fontWeight: 600 }}>
            ✓ Password updated! Redirecting to sign in…
          </p>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">New Password</label>
              <input
                className="form-input"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={e => { setPassword(e.target.value); setError(""); }}
                required
                autoFocus
                style={error ? { borderColor: "#e74c3c" } : {}}
              />
              <PasswordStrength password={password} />
            </div>

            <div className="form-group">
              <label className="form-label">Confirm Password</label>
              <input
                className="form-input"
                type="password"
                placeholder="••••••••"
                value={confirm}
                onChange={e => { setConfirm(e.target.value); setError(""); }}
                required
              />
            </div>

            {error && (
              <div style={{
                background: "#fdf0f0", border: "1px solid #f5c6cb", borderRadius: 8,
                padding: "10px 14px", marginBottom: 12, fontSize: 13,
                color: "#c0392b", lineHeight: 1.5
              }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: "100%", justifyContent: "center", padding: "12px" }}
              disabled={loading}
            >
              {loading ? "Updating..." : "Set New Password"}
            </button>
            <button type="button" className="btn btn-ghost"
              style={{ width: "100%", justifyContent: "center", marginTop: 8 }}
              onClick={() => navigate("/login")}>
              Back to Sign In
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
