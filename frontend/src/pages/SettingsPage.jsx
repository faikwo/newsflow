import { useState, useEffect } from "react";
import api from "../api";
import toast from "react-hot-toast";
import { Save, RefreshCw, Mail, Rss, Brain, CheckCircle, XCircle, ChevronDown, Globe, Users, Trash2, Shield, Key } from "lucide-react";
import { useAuth } from "../context/AuthContext";

// Full timezone list grouped by region
const TIMEZONES = [
  { group: "UTC", zones: ["UTC"] },
  { group: "Australia", zones: [
    "Australia/Sydney", "Australia/Melbourne", "Australia/Brisbane",
    "Australia/Adelaide", "Australia/Perth", "Australia/Darwin",
    "Australia/Hobart", "Australia/Lord_Howe",
  ]},
  { group: "New Zealand", zones: ["Pacific/Auckland", "Pacific/Chatham"] },
  { group: "Pacific", zones: [
    "Pacific/Honolulu", "Pacific/Tahiti", "Pacific/Fiji",
    "Pacific/Guam", "Pacific/Port_Moresby", "Pacific/Noumea",
  ]},
  { group: "Asia - East", zones: [
    "Asia/Tokyo", "Asia/Seoul", "Asia/Shanghai", "Asia/Hong_Kong",
    "Asia/Taipei", "Asia/Singapore", "Asia/Manila", "Asia/Kuala_Lumpur",
  ]},
  { group: "Asia - South/SE", zones: [
    "Asia/Bangkok", "Asia/Jakarta", "Asia/Ho_Chi_Minh", "Asia/Kolkata",
    "Asia/Colombo", "Asia/Dhaka", "Asia/Karachi", "Asia/Kathmandu",
  ]},
  { group: "Asia - West", zones: [
    "Asia/Dubai", "Asia/Riyadh", "Asia/Qatar", "Asia/Kuwait",
    "Asia/Baghdad", "Asia/Tehran", "Asia/Baku", "Asia/Tbilisi",
    "Asia/Yerevan", "Asia/Tashkent", "Asia/Almaty",
  ]},
  { group: "Europe - West", zones: [
    "Europe/London", "Europe/Dublin", "Europe/Lisbon", "Atlantic/Reykjavik",
  ]},
  { group: "Europe - Central", zones: [
    "Europe/Paris", "Europe/Berlin", "Europe/Amsterdam", "Europe/Brussels",
    "Europe/Madrid", "Europe/Rome", "Europe/Vienna", "Europe/Zurich",
    "Europe/Stockholm", "Europe/Oslo", "Europe/Copenhagen", "Europe/Warsaw",
    "Europe/Prague", "Europe/Budapest", "Europe/Zagreb", "Europe/Belgrade",
  ]},
  { group: "Europe - East", zones: [
    "Europe/Athens", "Europe/Helsinki", "Europe/Tallinn", "Europe/Riga",
    "Europe/Vilnius", "Europe/Bucharest", "Europe/Sofia", "Europe/Kiev",
    "Europe/Moscow", "Europe/Istanbul",
  ]},
  { group: "Africa", zones: [
    "Africa/Cairo", "Africa/Johannesburg", "Africa/Lagos", "Africa/Nairobi",
    "Africa/Accra", "Africa/Casablanca", "Africa/Tunis", "Africa/Algiers",
    "Africa/Addis_Ababa", "Africa/Dar_es_Salaam", "Africa/Khartoum",
  ]},
  { group: "Americas - North", zones: [
    "America/New_York", "America/Chicago", "America/Denver", "America/Phoenix",
    "America/Los_Angeles", "America/Anchorage", "America/Adak",
    "America/Toronto", "America/Vancouver", "America/Edmonton",
    "America/Winnipeg", "America/Halifax", "America/St_Johns",
  ]},
  { group: "Americas - Central", zones: [
    "America/Mexico_City", "America/Cancun", "America/Bogota",
    "America/Lima", "America/Caracas", "America/Panama",
    "America/Costa_Rica", "America/Guatemala",
  ]},
  { group: "Americas - South", zones: [
    "America/Sao_Paulo", "America/Buenos_Aires", "America/Santiago",
    "America/Montevideo", "America/La_Paz", "America/Asuncion",
    "America/Guayaquil",
  ]},
];

const COUNTRIES = [
  { code: "", label: "Global (no preference)" },
  { code: "AU", label: "🦘 Australia" },
  { code: "NZ", label: "🥝 New Zealand" },
  { code: "US", label: "🇺🇸 United States" },
  { code: "GB", label: "🇬🇧 United Kingdom" },
  { code: "CA", label: "🍁 Canada" },
  { code: "IE", label: "🇮🇪 Ireland" },
  { code: "IN", label: "🇮🇳 India" },
  { code: "SG", label: "🇸🇬 Singapore" },
  { code: "JP", label: "🇯🇵 Japan" },
  { code: "KR", label: "🇰🇷 South Korea" },
  { code: "DE", label: "🇩🇪 Germany" },
  { code: "FR", label: "🇫🇷 France" },
  { code: "NL", label: "🇳🇱 Netherlands" },
  { code: "SE", label: "🇸🇪 Sweden" },
  { code: "NO", label: "🇳🇴 Norway" },
  { code: "ZA", label: "🇿🇦 South Africa" },
  { code: "BR", label: "🇧🇷 Brazil" },
];

function Toggle({ checked, onChange }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} />
      <span className="toggle-slider" />
    </label>
  );
}

function ModelPicker({ models, value, onChange }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <button type="button" onClick={() => setOpen(!open)} style={{
        width: "100%", padding: "10px 14px", background: "var(--bg3)",
        border: "1px solid var(--accent)", borderRadius: 10,
        color: value ? "var(--text)" : "var(--text3)", fontSize: 14,
        fontFamily: "inherit", textAlign: "left", cursor: "pointer",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span>{value || "— Select a model —"}</span>
        <ChevronDown size={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
      </button>
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
          background: "var(--bg2)", border: "1px solid var(--accent)", borderRadius: 10,
          zIndex: 200, maxHeight: 280, overflowY: "auto",
          boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
        }}>
          {models.map(m => (
            <button key={m} type="button" onClick={() => { onChange(m); setOpen(false); }} style={{
              display: "block", width: "100%", padding: "10px 16px",
              background: m === value ? "var(--accent-glow)" : "transparent",
              border: "none", borderBottom: "1px solid var(--border)",
              color: m === value ? "var(--accent)" : "var(--text)",
              fontSize: 13, fontFamily: "inherit", textAlign: "left", cursor: "pointer",
            }}>
              {m === value && <CheckCircle size={12} style={{ marginRight: 8, display: "inline" }} />}
              {m}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const [settings, setSettings] = useState({});
  const [userPrefs, setUserPrefs] = useState({ timezone: "UTC", country: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [ollamaStatus, setOllamaStatus] = useState(null);
  const [ollamaError, setOllamaError] = useState("");
  const [availableModels, setAvailableModels] = useState([]);

  // User management (admin only)
  const [allUsers, setAllUsers] = useState([]);
  const [editingUser, setEditingUser] = useState(null); // {id, username, email, is_admin}
  const [editForm, setEditForm] = useState({ username: "", email: "", password: "", is_admin: false });
  const [deletingUser, setDeletingUser] = useState(null);

  // Delete own account
  const [showDeleteSelf, setShowDeleteSelf] = useState(false);
  const [deleteSelfConfirm, setDeleteSelfConfirm] = useState("");

  useEffect(() => {
    if (!user?.is_admin) { setLoading(false); return; }
    Promise.all([
      api.get("/api/settings/app"),
      api.get("/api/settings/user"),
      api.get("/api/auth/users"),
    ]).then(([appRes, userRes, usersRes]) => {
      setSettings(appRes.data);
      setUserPrefs(prev => ({ ...prev, ...userRes.data }));
      setAllUsers(usersRes.data.users || []);
    }).catch(() => toast.error("Failed to load settings"))
      .finally(() => setLoading(false));
  }, []);

  const set = (key, value) => setSettings(prev => ({ ...prev, [key]: value }));
  const setPref = (key, value) => setUserPrefs(prev => ({ ...prev, [key]: value }));

  const testOllama = async () => {
    const url = (settings.ollama_url || "").trim();
    if (!url) { toast.error("Enter an Ollama URL first"); return; }
    setTesting(true);
    setOllamaStatus(null);
    setOllamaError("");
    setAvailableModels([]);
    try {
      const { data } = await api.get("/api/settings/ollama/test", { params: { url } });
      if (data.success) {
        setOllamaStatus("ok");
        setAvailableModels(data.models);
        toast.success(`Connected! ${data.models.length} models found.`);
        if (!settings.ollama_model || !data.models.includes(settings.ollama_model)) {
          if (data.models.length > 0) set("ollama_model", data.models[0]);
        }
      } else {
        setOllamaStatus("error");
        setOllamaError(data.error || "Unknown error");
        toast.error(`${data.error}`);
      }
    } catch {
      setOllamaStatus("error");
      setOllamaError("Request failed — check backend logs");
      toast.error("Test request failed");
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await Promise.all([
        api.post("/api/settings/app", settings),
        api.post("/api/settings/user", userPrefs),
        // Keep digest_schedule timezone in sync with user timezone preference
        api.post("/api/digest/schedule", { timezone: userPrefs.timezone }),
      ]);
      toast.success("Settings saved!");
    } catch {
      toast.error("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  if (!user?.is_admin) return (
    <div className="page-container">
      <div className="empty-state">
        <div className="empty-icon">🔒</div>
        <div className="empty-title">Admin Only</div>
      </div>
    </div>
  );

  if (loading) return (
    <div className="page-container">
      <div className="loader-ring" style={{ margin: "60px auto" }} />
    </div>
  );

  const selectedCountry = COUNTRIES.find(c => c.code === (userPrefs.country || "")) || COUNTRIES[0];

  return (
    <div className="page-container" style={{ maxWidth: 720 }}>
      <div style={{ marginBottom: 24, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 800 }}>Settings</h1>
          <p style={{ color: "var(--text3)", fontSize: 13, marginTop: 4 }}>Configure your NewsFlow instance</p>
        </div>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          <Save size={15} /> {saving ? "Saving..." : "Save All"}
        </button>
      </div>

      {/* ── Ollama ── */}
      <div className="settings-section">
        <h3><Brain size={18} /> Ollama AI Configuration</h3>
        <div className="form-group">
          <label className="form-label">Ollama Server URL</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input className="form-input"
              placeholder="http://192.168.1.100:11434"
              value={settings.ollama_url || ""}
              onChange={e => { set("ollama_url", e.target.value); setOllamaStatus(null); setAvailableModels([]); }}
              onKeyDown={e => e.key === "Enter" && testOllama()}
            />
            <button className="btn btn-ghost" onClick={testOllama} disabled={testing} style={{
              whiteSpace: "nowrap", minWidth: 100,
              borderColor: ollamaStatus === "ok" ? "var(--like)" : ollamaStatus === "error" ? "var(--dislike)" : undefined,
              color: ollamaStatus === "ok" ? "var(--like)" : ollamaStatus === "error" ? "var(--dislike)" : undefined,
            }}>
              {testing ? <><RefreshCw size={14} className="spinning" /> Testing...</>
                : ollamaStatus === "ok" ? <><CheckCircle size={14} /> Connected</>
                : ollamaStatus === "error" ? <><XCircle size={14} /> Failed</>
                : <><RefreshCw size={14} /> Test</>}
            </button>
          </div>
          {ollamaStatus === "ok" && (
            <div style={{ marginTop: 10, padding: "10px 14px", background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.3)", borderRadius: 10, fontSize: 13, color: "var(--like)" }}>
              ✅ Connected — {availableModels.length} model{availableModels.length !== 1 ? "s" : ""} available
            </div>
          )}
          {ollamaStatus === "error" && (
            <div style={{ marginTop: 10, padding: "10px 14px", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 10, fontSize: 13, color: "var(--dislike)" }}>
              ❌ {ollamaError}
            </div>
          )}
        </div>

        <div className="form-group">
          <label className="form-label">
            Model
            {availableModels.length === 0 && settings.ollama_model && (
              <span style={{ color: "var(--text3)", fontWeight: 400, marginLeft: 8 }}>(click Test to refresh list)</span>
            )}
          </label>
          {availableModels.length > 0 ? (
            <>
              <ModelPicker models={availableModels} value={settings.ollama_model || ""} onChange={v => set("ollama_model", v)} />
              <p style={{ fontSize: 12, color: "var(--text3)", marginTop: 8 }}>
                💡 For dual 3060: <strong>mistral-nemo:12b</strong> (fast, 1 GPU) · <strong>mixtral:8x7b</strong> (best, both GPUs) · <strong>qwen2.5:14b</strong> (great quality)
              </p>
            </>
          ) : (
            <div style={{ padding: "12px 16px", background: "var(--bg3)", border: "1px dashed var(--border)", borderRadius: 10, fontSize: 13, color: "var(--text3)", textAlign: "center" }}>
              {settings.ollama_model
                ? <>Current: <strong style={{ color: "var(--text)" }}>{settings.ollama_model}</strong> — click <strong>Test</strong> to see all models</>
                : <>Enter your Ollama URL and click <strong>Test</strong> to see available models</>}
            </div>
          )}
        </div>

        <div className="toggle-row">
          <div>
            <div className="toggle-label">Auto-summarize articles</div>
            <div className="toggle-desc">Automatically summarize new articles with AI</div>
          </div>
          <Toggle checked={settings.auto_summarize === "true"} onChange={v => set("auto_summarize", v ? "true" : "false")} />
        </div>
      </div>

      {/* ── Regional Preferences ── */}
      <div className="settings-section">
        <h3><Globe size={18} /> Regional Preferences</h3>
        <p style={{ fontSize: 13, color: "var(--text3)", marginBottom: 16, marginTop: -4 }}>
          Your country preference biases topic feeds and NewsAPI searches toward local sources and stories.
        </p>

        <div className="form-group">
          <label className="form-label">Your Country</label>
          <select className="form-input" value={userPrefs.country || ""} onChange={e => setPref("country", e.target.value)}>
            {COUNTRIES.map(c => (
              <option key={c.code} value={c.code}>{c.label}</option>
            ))}
          </select>
          {userPrefs.country && (
            <p style={{ fontSize: 12, color: "var(--text3)", marginTop: 6 }}>
              {selectedCountry.label} topics and sources will be prioritised in your feed.
            </p>
          )}
        </div>

        <div className="form-group">
          <label className="form-label">Timezone</label>
          <select className="form-input" value={userPrefs.timezone || "UTC"} onChange={e => setPref("timezone", e.target.value)}>
            {TIMEZONES.map(group => (
              <optgroup key={group.group} label={group.group}>
                {group.zones.map(tz => (
                  <option key={tz} value={tz}>{tz.replace(/_/g, " ")}</option>
                ))}
              </optgroup>
            ))}
          </select>
          <p style={{ fontSize: 12, color: "var(--text3)", marginTop: 6 }}>Used for scheduling your daily email digest.</p>
        </div>
      </div>

      {/* ── Feed Settings ── */}
      <div className="settings-section">
        <h3><Rss size={18} /> Feed Settings</h3>
        <div className="form-group">
          <label className="form-label">Refresh Interval</label>
          <select className="form-input" value={settings.refresh_interval_minutes || "60"} onChange={e => set("refresh_interval_minutes", e.target.value)}>
            <option value="15">Every 15 minutes</option>
            <option value="30">Every 30 minutes</option>
            <option value="60">Every hour</option>
            <option value="360">Every 6 hours</option>
            <option value="720">Every 12 hours</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">Max Articles Per Topic Per Fetch</label>
          <select className="form-input" value={settings.max_articles_per_topic || "20"} onChange={e => set("max_articles_per_topic", e.target.value)}>
            <option value="10">10</option>
            <option value="20">20</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">Keep Articles For</label>
          <select className="form-input" value={settings.article_retention_days || "30"} onChange={e => set("article_retention_days", e.target.value)}>
            <option value="7">7 days</option>
            <option value="14">14 days</option>
            <option value="30">30 days (default)</option>
            <option value="60">60 days</option>
            <option value="90">90 days</option>
            <option value="365">1 year</option>
          </select>
          <p style={{ fontSize: 12, color: "var(--text3)", marginTop: 6 }}>
            Articles older than this are automatically deleted overnight. Articles you've liked or interacted with are always kept.
          </p>
        </div>
        <div className="form-group">
          <label className="form-label">Read Later Expiry</label>
          <select className="form-input" value={settings.read_later_expiry_days || "30"} onChange={e => set("read_later_expiry_days", e.target.value)}>
            <option value="0">Never expire</option>
            <option value="7">7 days</option>
            <option value="14">14 days</option>
            <option value="30">30 days (default)</option>
            <option value="60">60 days</option>
            <option value="90">90 days</option>
          </select>
          <p style={{ fontSize: 12, color: "var(--text3)", marginTop: 6 }}>
            Saved articles are automatically removed from your Read Later list after this period.
          </p>
        </div>
        <div className="form-group">
          <label className="form-label">Site URL <span style={{ color: "var(--text3)", fontWeight: 400 }}>(optional)</span></label>
          <input className="form-input" placeholder="https://news.yourdomain.com"
            value={settings.site_url || ""} onChange={e => set("site_url", e.target.value)} />
          <p style={{ fontSize: 12, color: "var(--text3)", marginTop: 6 }}>
            Used for link tracking. If blank, your server's IP is used. When you set a domain, all past article tracking links update automatically.
          </p>
        </div>
        <div className="form-group">
          <label className="form-label">Allow New Signups</label>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <input
              type="checkbox"
              id="allowSignups"
              checked={settings.allow_signups !== "false"}
              onChange={e => set("allow_signups", e.target.checked ? "true" : "false")}
            />
            <label htmlFor="allowSignups" style={{ cursor: "pointer", userSelect: "none" }}>
              Allow new users to register
            </label>
          </div>
          <p style={{ fontSize: 12, color: "var(--text3)", marginTop: 6 }}>
            When disabled, the registration tab is hidden on the login page and new accounts cannot be created. Existing accounts are unaffected.
          </p>
        </div>
        <div className="form-group">
          <label className="form-label">NewsAPI Key <span style={{ color: "var(--text3)", fontWeight: 400 }}>(optional)</span></label>
          <input className="form-input" placeholder="Get a free key at newsapi.org"
            value={settings.newsapi_key || ""} onChange={e => set("newsapi_key", e.target.value)} />
          <p style={{ fontSize: 12, color: "var(--text3)", marginTop: 6 }}>
            Adds 100+ extra sources with country-aware search. Free tier: 100 req/day.
          </p>
        </div>
      </div>

      {/* ── Email ── */}
      <div className="settings-section">
        <h3><Mail size={18} /> Email Digest (SMTP)</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 120px", gap: 12 }}>
          <div className="form-group">
            <label className="form-label">SMTP Host</label>
            <input className="form-input" placeholder="smtp.gmail.com"
              value={settings.smtp_host || ""} onChange={e => set("smtp_host", e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Port</label>
            <input className="form-input" placeholder="587"
              value={settings.smtp_port || "587"} onChange={e => set("smtp_port", e.target.value)} />
          </div>
        </div>
        <div className="form-group">
          <label className="form-label">SMTP Username</label>
          <input className="form-input" placeholder="your@email.com"
            value={settings.smtp_user || ""} onChange={e => set("smtp_user", e.target.value)} />
        </div>
        <div className="form-group">
          <label className="form-label">SMTP Password</label>
          <input className="form-input" type="password" placeholder="App password"
            value={settings.smtp_password === "••••••••" ? "" : (settings.smtp_password || "")}
            onChange={e => set("smtp_password", e.target.value)} />
          <p style={{ fontSize: 12, color: "var(--text3)", marginTop: 6 }}>
            Gmail: use an <a href="https://support.google.com/accounts/answer/185833" target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>App Password</a>.
          </p>
        </div>
        <div className="form-group">
          <label className="form-label">From Address</label>
          <input className="form-input" placeholder="NewsFlow <your@email.com>"
            value={settings.smtp_from || ""} onChange={e => set("smtp_from", e.target.value)} />
        </div>
      </div>

      <button className="btn btn-primary" onClick={save} disabled={saving}
        style={{ width: "100%", justifyContent: "center", padding: 14 }}>
        <Save size={16} /> {saving ? "Saving..." : "Save Settings"}
      </button>

      {/* ── Admin: User Management ── */}
      <div className="settings-section">
        <h3><Users size={18} /> User Management</h3>
        {allUsers.map(u => (
          <div key={u.id} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "10px 0", borderBottom: "1px solid var(--border)",
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, color: "var(--text)" }}>
                {u.username}
                {u.is_admin && <span style={{
                  marginLeft: 6, fontSize: 10, fontWeight: 700,
                  background: "var(--accent-glow)", color: "var(--accent)",
                  padding: "1px 6px", borderRadius: 10, textTransform: "uppercase",
                }}>Admin</span>}
                {u.id === user.id && <span style={{
                  marginLeft: 6, fontSize: 10, color: "var(--text3)",
                }}>(you)</span>}
              </div>
              <div style={{ fontSize: 12, color: "var(--text3)" }}>{u.email}</div>
            </div>
            <button className="btn btn-ghost" style={{ padding: "5px 10px", fontSize: 12 }}
              onClick={() => {
                setEditingUser(u);
                setEditForm({ username: u.username, email: u.email, password: "", is_admin: !!u.is_admin });
              }}>
              <Key size={13} /> Edit
            </button>
            {u.id !== user.id && (
              <button className="btn btn-ghost" style={{ padding: "5px 10px", fontSize: 12, color: "var(--dislike)", borderColor: "var(--dislike)" }}
                onClick={() => setDeletingUser(u)}>
                <Trash2 size={13} />
              </button>
            )}
          </div>
        ))}

        {/* Edit user modal */}
        {editingUser && (
          <div style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }}>
            <div style={{
              background: "var(--bg2)", border: "1px solid var(--border)",
              borderRadius: 16, padding: 28, maxWidth: 420, width: "100%",
            }}>
              <h3 style={{ marginBottom: 20, fontFamily: "'Playfair Display', serif" }}>
                Edit: {editingUser.username}
              </h3>
              <div className="form-group">
                <label className="form-label">Username</label>
                <input className="form-input" value={editForm.username}
                  onChange={e => setEditForm(f => ({ ...f, username: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input className="form-input" value={editForm.email}
                  onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">New Password <span style={{ color: "var(--text3)", fontWeight: 400 }}>(leave blank to keep current)</span></label>
                <input className="form-input" type="password" placeholder="Enter new password"
                  value={editForm.password}
                  onChange={e => setEditForm(f => ({ ...f, password: e.target.value }))} />
              </div>
              <div className="form-group" style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <input type="checkbox" id="editIsAdmin" checked={editForm.is_admin}
                  onChange={e => setEditForm(f => ({ ...f, is_admin: e.target.checked }))} />
                <label htmlFor="editIsAdmin" style={{ cursor: "pointer" }}>
                  <Shield size={14} style={{ verticalAlign: "middle", marginRight: 4 }} />
                  Admin access
                </label>
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
                <button className="btn btn-ghost" style={{ flex: 1 }} onClick={() => setEditingUser(null)}>
                  Cancel
                </button>
                <button className="btn btn-primary" style={{ flex: 1 }} onClick={async () => {
                  try {
                    await api.patch(`/api/auth/users/${editingUser.id}`, editForm);
                    toast.success("User updated");
                    setAllUsers(prev => prev.map(u => u.id === editingUser.id
                      ? { ...u, username: editForm.username, email: editForm.email, is_admin: editForm.is_admin }
                      : u
                    ));
                    setEditingUser(null);
                  } catch (e) {
                    toast.error(e.response?.data?.detail || "Update failed");
                  }
                }}>
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Delete user confirmation */}
        {deletingUser && (
          <div style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }}>
            <div style={{
              background: "var(--bg2)", border: "1px solid var(--border)",
              borderRadius: 16, padding: 28, maxWidth: 400, width: "100%",
            }}>
              <h3 style={{ marginBottom: 12, fontFamily: "'Playfair Display', serif", color: "var(--dislike)" }}>
                Delete {deletingUser.username}?
              </h3>
              <p style={{ color: "var(--text2)", fontSize: 14, marginBottom: 20 }}>
                This will permanently delete their account and all their data — interactions, preferences, share links, and digest settings. This cannot be undone.
              </p>
              <div style={{ display: "flex", gap: 10 }}>
                <button className="btn btn-ghost" style={{ flex: 1 }} onClick={() => setDeletingUser(null)}>
                  Cancel
                </button>
                <button className="btn btn-primary" style={{ flex: 1, background: "var(--dislike)", borderColor: "var(--dislike)" }}
                  onClick={async () => {
                    try {
                      await api.delete(`/api/auth/users/${deletingUser.id}`);
                      toast.success(`${deletingUser.username} deleted`);
                      setAllUsers(prev => prev.filter(u => u.id !== deletingUser.id));
                      setDeletingUser(null);
                    } catch (e) {
                      toast.error(e.response?.data?.detail || "Delete failed");
                    }
                  }}>
                  Delete Account
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Danger zone: delete own account ── */}
      <div className="settings-section" style={{ borderColor: "rgba(239,68,68,0.3)" }}>
        <h3 style={{ color: "var(--dislike)" }}><Trash2 size={18} /> Delete My Account</h3>
        <p style={{ fontSize: 13, color: "var(--text2)", marginBottom: 16 }}>
          Permanently deletes your account and all your data. This cannot be undone.
          {user?.is_admin && " As the admin, you must promote another user to admin first."}
        </p>
        {!showDeleteSelf ? (
          <button className="btn btn-ghost"
            style={{ color: "var(--dislike)", borderColor: "var(--dislike)" }}
            onClick={() => setShowDeleteSelf(true)}>
            <Trash2 size={14} /> Delete My Account
          </button>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <p style={{ fontSize: 13, color: "var(--text2)" }}>
              Type <strong style={{ color: "var(--text)" }}>DELETE</strong> to confirm:
            </p>
            <input className="form-input" placeholder="Type DELETE to confirm"
              value={deleteSelfConfirm}
              onChange={e => setDeleteSelfConfirm(e.target.value)} />
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn-ghost" style={{ flex: 1 }}
                onClick={() => { setShowDeleteSelf(false); setDeleteSelfConfirm(""); }}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                disabled={deleteSelfConfirm !== "DELETE"}
                style={{ flex: 1, background: "var(--dislike)", borderColor: "var(--dislike)", opacity: deleteSelfConfirm !== "DELETE" ? 0.5 : 1 }}
                onClick={async () => {
                  try {
                    await api.delete("/api/auth/me");
                    toast.success("Account deleted");
                    logout();
                  } catch (e) {
                    toast.error(e.response?.data?.detail || "Could not delete account");
                  }
                }}>
                Delete My Account
              </button>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes spinning { to { transform: rotate(360deg); } }
        .spinning { animation: spinning 1s linear infinite; display: inline-block; }
      `}</style>
    </div>
  );
}
