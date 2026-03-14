import { useState, useEffect } from "react";
import api from "../api";
import toast from "react-hot-toast";
import { Search, CheckCircle } from "lucide-react";

export default function TopicsPage() {
  const [grouped, setGrouped] = useState({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [subscribedCount, setSubscribedCount] = useState(0);

  const fetch = async () => {
    try {
      const { data } = await api.get("/api/topics/");
      setGrouped(data.grouped);
      const total = Object.values(data.grouped).flat().filter(t => t.subscribed).length;
      setSubscribedCount(total);
    } catch {
      toast.error("Failed to load topics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetch(); }, []);

  const toggle = async (topic) => {
    const wasSubscribed = topic.subscribed;
    // Optimistic update
    setGrouped(prev => {
      const updated = { ...prev };
      for (const cat in updated) {
        updated[cat] = updated[cat].map(t =>
          t.id === topic.id ? { ...t, subscribed: !t.subscribed } : t
        );
      }
      return updated;
    });
    setSubscribedCount(prev => wasSubscribed ? prev - 1 : prev + 1);

    try {
      if (wasSubscribed) {
        await api.delete(`/api/topics/${topic.id}/subscribe`);
        toast(`Unsubscribed from ${topic.name}`);
      } else {
        await api.post(`/api/topics/${topic.id}/subscribe`);
        toast.success(`Subscribed to ${topic.name} ${topic.icon}`);
      }
    } catch {
      // Revert
      setGrouped(prev => {
        const updated = { ...prev };
        for (const cat in updated) {
          updated[cat] = updated[cat].map(t =>
            t.id === topic.id ? { ...t, subscribed: wasSubscribed } : t
          );
        }
        return updated;
      });
      setSubscribedCount(prev => wasSubscribed ? prev + 1 : prev - 1);
      toast.error("Failed to update subscription");
    }
  };

  const filterTopics = (topics) => {
    if (!search) return topics;
    return topics.filter(t =>
      t.name.toLowerCase().includes(search.toLowerCase()) ||
      t.category.toLowerCase().includes(search.toLowerCase())
    );
  };

  const categories = Object.entries(grouped).filter(([, topics]) =>
    filterTopics(topics).length > 0
  );

  return (
    <div className="page-container">
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 800, marginBottom: 8 }}>
          Discover Topics
        </h1>
        <p style={{ color: "var(--text2)", fontSize: 14 }}>
          Choose from 60+ topics across all domains. Subscribed to{" "}
          <strong style={{ color: "var(--accent)" }}>{subscribedCount}</strong> topics.
        </p>
      </div>

      {/* Search */}
      <div style={{ position: "relative", marginBottom: 24 }}>
        <Search size={16} style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "var(--text3)" }} />
        <input
          className="form-input"
          placeholder="Search topics..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ paddingLeft: 40 }}
        />
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 60 }}>
          <div className="loader-ring" style={{ margin: "0 auto" }} />
        </div>
      ) : (
        categories.map(([category, topics]) => {
          const filtered = filterTopics(topics);
          return (
            <div key={category} style={{ marginBottom: 32 }}>
              <h2 style={{
                fontSize: 13,
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "1.5px",
                color: "var(--text3)",
                marginBottom: 12
              }}>
                {category} ({filtered.length})
              </h2>
              <div className="topics-grid">
                {filtered.map(topic => (
                  <div
                    key={topic.id}
                    className={`topic-card ${topic.subscribed ? "subscribed" : ""}`}
                    onClick={() => toggle(topic)}
                  >
                    <div className="topic-icon">{topic.icon}</div>
                    <div className="topic-name">{topic.name}</div>
                    <div className="topic-count">
                      {topic.article_count || 0} articles
                    </div>
                    {topic.subscribed && (
                      <div className="topic-subscribed-badge">
                        <CheckCircle size={10} style={{ display: "inline", marginRight: 3 }} />
                        Subscribed
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
