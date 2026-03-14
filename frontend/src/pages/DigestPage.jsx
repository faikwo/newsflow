import { useState, useEffect } from "react";
import api from "../api";
import toast from "react-hot-toast";
import { Mail, Plus, Trash2, RefreshCw, Clock, Rss, Send } from "lucide-react";

const PRESET_TIMES = ["05:00","06:00","07:00","08:00","09:00","10:00","12:00",
                       "14:00","16:00","18:00","20:00","21:00","22:00"];

function Toggle({ checked, onChange }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} />
      <span className="toggle-slider" />
    </label>
  );
}

export default function DigestPage() {
  const [schedule, setSchedule] = useState({ enabled: false, send_times: ["07:00"], timezone: "UTC" });
  const [feeds, setFeeds]   = useState([]);
  const [topics, setTopics] = useState([]);
  const [newFeed, setNewFeed] = useState({ url: "", name: "", topic_id: "" });
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);
  const [sending, setSending]   = useState(false);
  const [addingFeed, setAddingFeed] = useState(false);
  const [customTime, setCustomTime] = useState("");

  useEffect(() => {
    Promise.all([
      api.get("/api/digest/schedule"),
      api.get("/api/digest/custom-feeds"),
      api.get("/api/topics/subscribed"),
      api.get("/api/settings/user"),
    ]).then(([s, f, t, u]) => {
      const sched = s.data;
      if (typeof sched.send_times === "string") {
        try { sched.send_times = JSON.parse(sched.send_times); } catch { sched.send_times = ["07:00"]; }
      }
      // Sync timezone from user settings — digest_schedule timezone should always match
      const userTz = u.data?.timezone;
      if (userTz) sched.timezone = userTz;
      setSchedule(sched);
      setFeeds(f.data.feeds || []);
      setTopics(t.data.topics || []);
    }).catch(() => toast.error("Failed to load digest settings"))
      .finally(() => setLoading(false));
  }, []);

  const saveSchedule = async () => {
    setSaving(true);
    try {
      await api.post("/api/digest/schedule", schedule);
      toast.success("Digest schedule saved!");
    } catch { toast.error("Failed to save"); }
    finally { setSaving(false); }
  };

  const sendNow = async () => {
    setSending(true);
    try {
      await api.post("/api/digest/send-now");
      toast.success("Digest queued — check your inbox in a moment.");
    } catch { toast.error("Failed to send digest"); }
    finally { setSending(false); }
  };

  const addTime = (t) => {
    const time = t || customTime;
    if (!time) return;
    if (schedule.send_times.includes(time)) { toast("That time is already added"); return; }
    setSchedule(p => ({ ...p, send_times: [...p.send_times, time].sort() }));
    setCustomTime("");
  };

  const removeTime = (t) => {
    if (schedule.send_times.length <= 1) { toast("Keep at least one send time"); return; }
    setSchedule(p => ({ ...p, send_times: p.send_times.filter(x => x !== t) }));
  };

  const addFeed = async () => {
    if (!newFeed.url.trim()) { toast.error("Enter a feed URL"); return; }
    setAddingFeed(true);
    try {
      await api.post("/api/digest/custom-feeds", newFeed);
      const { data } = await api.get("/api/digest/custom-feeds");
      setFeeds(data.feeds || []);
      setNewFeed({ url: "", name: "", topic_id: "" });
      toast.success("Feed added!");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to add feed");
    } finally { setAddingFeed(false); }
  };

  const deleteFeed = async (id) => {
    try {
      await api.delete(`/api/digest/custom-feeds/${id}`);
      setFeeds(p => p.filter(f => f.id !== id));
      toast("Feed removed");
    } catch { toast.error("Failed to remove feed"); }
  };

  const fetchFeed = async (id) => {
    try {
      const { data } = await api.post(`/api/digest/custom-feeds/${id}/fetch`);
      toast.success(`Fetched ${data.articles_fetched} articles`);
    } catch { toast.error("Failed to fetch feed"); }
  };

  if (loading) return <div className="page-container"><div className="loader-ring" style={{ margin: "60px auto" }} /></div>;

  return (
    <div className="page-container" style={{ maxWidth: 720 }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 800 }}>Email Digest</h1>
        <p style={{ color: "var(--text3)", fontSize: 13, marginTop: 4 }}>
          Schedule daily email digests and manage custom RSS feeds
        </p>
      </div>

      {/* ── Schedule ── */}
      <div className="settings-section">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <h3 style={{ margin: 0 }}><Mail size={18} /> Digest Schedule</h3>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, color: "var(--text3)" }}>
              {schedule.enabled ? "Enabled" : "Disabled"}
            </span>
            <Toggle checked={schedule.enabled} onChange={v => setSchedule(p => ({ ...p, enabled: v }))} />
          </div>
        </div>

        {/* Send times */}
        <div className="form-group">
          <label className="form-label">
            <Clock size={13} style={{ display: "inline", marginRight: 5 }} />
            Send Times
            <span style={{ color: "var(--text3)", fontWeight: 400, marginLeft: 8, fontSize: 12 }}>
              ({schedule.send_times?.length || 0} time{schedule.send_times?.length !== 1 ? "s" : ""} per day)
            </span>
          </label>

          {/* Current times */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
            {(schedule.send_times || []).map(t => (
              <div key={t} style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                background: "var(--accent-glow)", border: "1px solid var(--accent)",
                borderRadius: 8, padding: "5px 10px", fontSize: 13, color: "var(--accent)",
              }}>
                <Clock size={12} />
                {t}
                <button onClick={() => removeTime(t)} style={{
                  background: "none", border: "none", cursor: "pointer",
                  color: "var(--text3)", padding: 0, lineHeight: 1,
                  display: "flex", alignItems: "center",
                }}>×</button>
              </div>
            ))}
          </div>

          {/* Preset quick-add */}
          <div style={{ marginBottom: 10 }}>
            <p style={{ fontSize: 12, color: "var(--text3)", marginBottom: 8 }}>Quick add:</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {PRESET_TIMES.filter(t => !(schedule.send_times || []).includes(t)).map(t => (
                <button key={t} onClick={() => addTime(t)} className="btn btn-ghost"
                  style={{ padding: "4px 10px", fontSize: 12 }}>
                  + {t}
                </button>
              ))}
            </div>
          </div>

          {/* Custom time */}
          <div style={{ display: "flex", gap: 8 }}>
            <input type="time" className="form-input" value={customTime}
              onChange={e => setCustomTime(e.target.value)}
              style={{ maxWidth: 140 }} />
            <button className="btn btn-ghost" onClick={() => addTime()} disabled={!customTime}>
              <Plus size={14} /> Add custom time
            </button>
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, marginTop: 20 }}>
          <button className="btn btn-primary" onClick={saveSchedule} disabled={saving}>
            {saving ? "Saving..." : "Save Schedule"}
          </button>
          <button className="btn btn-ghost" onClick={sendNow} disabled={sending}
            style={{ borderColor: "var(--accent)", color: "var(--accent)" }}>
            <Send size={14} /> {sending ? "Sending..." : "Send Now"}
          </button>
        </div>

        {schedule.enabled && schedule.send_times?.length > 0 && (
          <div style={{
            marginTop: 16, padding: "10px 14px",
            background: "rgba(79,142,247,0.06)", border: "1px solid rgba(79,142,247,0.2)",
            borderRadius: 10, fontSize: 13, color: "var(--text2)",
          }}>
            📬 Digest will be sent at: <strong>{schedule.send_times.join(", ")}</strong>
            {" "}({schedule.timezone})
          </div>
        )}
      </div>

      {/* ── Custom RSS Feeds ── */}
      <div className="settings-section">
        <h3><Rss size={18} /> Custom RSS Feeds</h3>
        <p style={{ fontSize: 13, color: "var(--text3)", marginBottom: 16, marginTop: -4 }}>
          Add any RSS feed. Articles will appear in your feed under the topic you assign.
        </p>

        {/* Add new feed */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">Feed URL *</label>
            <input className="form-input" placeholder="https://example.com/feed.xml"
              value={newFeed.url} onChange={e => setNewFeed(p => ({ ...p, url: e.target.value }))} />
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">Display Name</label>
            <input className="form-input" placeholder="My Custom Feed"
              value={newFeed.name} onChange={e => setNewFeed(p => ({ ...p, name: e.target.value }))} />
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", marginBottom: 20 }}>
          <div className="form-group" style={{ margin: 0, flex: 1 }}>
            <label className="form-label">Assign to Topic</label>
            <select className="form-input" value={newFeed.topic_id}
              onChange={e => setNewFeed(p => ({ ...p, topic_id: e.target.value }))}>
              <option value="">— Auto (first subscribed topic) —</option>
              {topics.map(t => (
                <option key={t.id} value={t.id}>{t.icon} {t.name}</option>
              ))}
            </select>
          </div>
          <button className="btn btn-primary" onClick={addFeed} disabled={addingFeed}
            style={{ flexShrink: 0, alignSelf: "flex-end" }}>
            <Plus size={14} /> {addingFeed ? "Adding..." : "Add Feed"}
          </button>
        </div>

        {/* Feed list */}
        {feeds.length === 0 ? (
          <div style={{
            padding: "20px", background: "var(--bg3)", borderRadius: 10,
            textAlign: "center", color: "var(--text3)", fontSize: 13,
          }}>
            No custom feeds yet — add one above
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {feeds.map(feed => (
              <div key={feed.id} style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "12px 16px", background: "var(--bg3)",
                borderRadius: 10, border: "1px solid var(--border)",
              }}>
                <Rss size={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)" }}>
                    {feed.name || feed.url}
                  </div>
                  {feed.name && (
                    <div style={{ fontSize: 12, color: "var(--text3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {feed.url}
                    </div>
                  )}
                </div>
                <button className="btn btn-ghost" onClick={() => fetchFeed(feed.id)}
                  style={{ flexShrink: 0, padding: "5px 10px", fontSize: 12 }} title="Fetch now">
                  <RefreshCw size={12} /> Fetch
                </button>
                <button onClick={() => deleteFeed(feed.id)} style={{
                  background: "none", border: "none", cursor: "pointer",
                  color: "var(--text3)", padding: 4, display: "flex", alignItems: "center",
                }} title="Remove feed">
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
