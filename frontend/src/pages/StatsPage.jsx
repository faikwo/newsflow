import { useState, useEffect } from "react";
import api from "../api";
import { ThumbsUp, ThumbsDown, BookOpen, Eye } from "lucide-react";

export default function StatsPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/api/preferences/stats")
      .then(r => setStats(r.data))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="page-container">
      <div className="loader-ring" style={{ margin: "60px auto" }} />
    </div>
  );

  const interactions = stats?.interactions || {};
  const statCards = [
    { icon: <ThumbsUp size={20} />, label: "Articles Liked", value: interactions.like || 0, color: "var(--like)" },
    { icon: <ThumbsDown size={20} />, label: "Disliked", value: interactions.dislike || 0, color: "var(--dislike)" },
    { icon: <BookOpen size={20} />, label: "Articles Read", value: interactions.read || 0, color: "var(--accent)" },
    { icon: <Eye size={20} />, label: "Topics Subscribed", value: stats?.subscribed_topics || 0, color: "var(--accent2)" },
  ];

  return (
    <div className="page-container">
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 800, marginBottom: 6 }}>
          My Reading Stats
        </h1>
        <p style={{ color: "var(--text3)", fontSize: 14 }}>
          See how your taste is shaping NewsFlow's recommendations.
        </p>
      </div>

      {/* Stat cards */}
      <div className="stats-grid">
        {statCards.map(s => (
          <div key={s.label} className="stat-card">
            <div style={{ color: s.color, marginBottom: 8 }}>{s.icon}</div>
            <div className="stat-number" style={{ color: s.color }}>{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Top topics */}
      {stats?.top_liked_topics?.length > 0 && (
        <div className="settings-section">
          <h3>❤️ Your Favourite Topics</h3>
          <p style={{ fontSize: 13, color: "var(--text3)", marginBottom: 16 }}>
            Based on articles you've liked. NewsFlow uses this to score recommendations.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {stats.top_liked_topics.map((t, i) => {
              const max = stats.top_liked_topics[0].count;
              const pct = Math.round((t.count / max) * 100);
              return (
                <div key={t.name}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 14 }}>
                    <span>{t.icon} {t.name}</span>
                    <span style={{ color: "var(--text3)", fontSize: 13 }}>{t.count} likes</span>
                  </div>
                  <div style={{ background: "var(--bg3)", borderRadius: 4, height: 6, overflow: "hidden" }}>
                    <div style={{
                      width: `${pct}%`,
                      height: "100%",
                      background: `linear-gradient(90deg, var(--accent), var(--accent2))`,
                      borderRadius: 4,
                      transition: "width 0.8s ease"
                    }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* How recommendations work */}
      <div className="settings-section">
        <h3>🧠 How Your AI Learns</h3>
        <div style={{ display: "grid", gap: 14, color: "var(--text2)", fontSize: 14, lineHeight: 1.7 }}>
          <p>
            Every time you <strong style={{ color: "var(--like)" }}>👍 like</strong> an article,
            NewsFlow extracts keywords and topics from it. These build your personal interest profile.
          </p>
          <p>
            When new articles arrive, a <strong style={{ color: "var(--accent)" }}>hybrid engine</strong> first
            scores them by keyword overlap with your liked articles, then sends the top candidates
            to your Ollama AI for intelligent re-ranking.
          </p>
          <p>
            Articles you <strong style={{ color: "var(--dislike)" }}>👎 dislike</strong> or hide teach
            the engine what to avoid. The more you interact, the smarter it gets.
          </p>
        </div>
      </div>
    </div>
  );
}
