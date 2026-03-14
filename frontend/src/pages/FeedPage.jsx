import { useState, useEffect, useCallback, useRef } from "react";
import api from "../api";
import toast from "react-hot-toast";
import { formatDistanceToNow } from "date-fns";
import { ThumbsUp, ThumbsDown, EyeOff, ExternalLink, Sparkles, RefreshCw, Loader2, X, Bookmark } from "lucide-react";


// ── Summary Popout Modal ──────────────────────────────────────────────────────
function SummaryModal({ article, summary, loading, onClose, onInteract, action, shareUrl }) {
  const ref = useRef();

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    const keyHandler = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", keyHandler);
    return () => { document.removeEventListener("mousedown", handler); document.removeEventListener("keydown", keyHandler); };
  }, [onClose]);

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: "20px",
    }}>
      <div ref={ref} style={{
        background: "var(--bg2)", border: "1px solid var(--border)",
        borderRadius: 16, padding: 28, maxWidth: 560, width: "100%",
        boxShadow: "0 24px 60px rgba(0,0,0,0.6)",
        maxHeight: "80vh", display: "flex", flexDirection: "column", gap: 16,
      }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              background: "var(--accent-glow)", color: "var(--accent)",
              fontSize: 11, fontWeight: 700, padding: "2px 8px",
              borderRadius: 20, textTransform: "uppercase", letterSpacing: "0.5px",
              marginBottom: 8,
            }}>
              {article.topic_icon} {article.topic_name}
            </div>
            <h2 style={{
              fontFamily: "'Playfair Display', serif",
              fontSize: 19, fontWeight: 800, lineHeight: 1.3, color: "var(--text)",
            }}>
              {article.title}
            </h2>
            <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 6 }}>
              <strong style={{ color: "var(--text2)" }}>{article.source}</strong>
              {article.published_at && <span> · {formatDistanceToNow(new Date(article.published_at), { addSuffix: true })}</span>}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: "var(--bg3)", border: "1px solid var(--border)",
            borderRadius: 8, padding: 6, cursor: "pointer", color: "var(--text3)",
            display: "flex", alignItems: "center", flexShrink: 0,
          }}>
            <X size={16} />
          </button>
        </div>

        {/* AI Summary body */}
        <div style={{
          background: "rgba(79,142,247,0.06)", border: "1px solid rgba(79,142,247,0.18)",
          borderRadius: 10, padding: "14px 16px", overflowY: "auto", flex: 1,
        }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 5,
            fontSize: 10, fontWeight: 700, textTransform: "uppercase",
            letterSpacing: "0.6px", color: "var(--accent)", marginBottom: 10,
          }}>
            <Sparkles size={10} /> AI Summary
          </div>
          {loading ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--accent)", fontSize: 13 }}>
              <Loader2 size={14} style={{ animation: "spinning 1s linear infinite" }} />
              Summarising with AI…
            </div>
          ) : (
            <p style={{ fontSize: 14, color: "var(--text2)", lineHeight: 1.75, margin: 0 }}>
              {summary || "Summary unavailable for this article."}
            </p>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            className={`action-btn ${action === "like" ? "liked" : ""}`}
            onClick={() => onInteract(action === "like" ? "read" : "like")}
          >
            <ThumbsUp size={13} /> Like
          </button>
          <button
            className={`action-btn ${action === "dislike" ? "disliked" : ""}`}
            onClick={() => onInteract(action === "dislike" ? "read" : "dislike")}
          >
            <ThumbsDown size={13} /> Less
          </button>
          <button className="action-btn" onClick={() => { onInteract("hide"); onClose(); }}>
            <EyeOff size={13} /> Hide
          </button>
          <a
            href={shareUrl || "#"}
            target="_blank"
            rel="noreferrer"
            className="action-btn read-more"
            style={{ marginLeft: "auto" }}
          >
            Read full article <ExternalLink size={12} />
          </a>
        </div>
      </div>
    </div>
  );
}

// ── Article Card ──────────────────────────────────────────────────────────────
function ArticleCard({ article, onInteract }) {
  const [action, setAction]         = useState(article.user_action || null);
  const [isSaved, setIsSaved]       = useState(!!article.is_saved);
  const [aiSummary, setAiSummary]   = useState(article.ai_summary || null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryFailed, setSummaryFailed]   = useState(false);
  const [showModal, setShowModal]   = useState(false);

  const [shareUrl, setShareUrl] = useState(null);

  // Pre-fetch permanent share token so the Read href is a real URL immediately
  useEffect(() => {
    let cancelled = false;
    api.get(`/api/articles/${article.id}/share-token`)
      .then(({ data }) => { if (!cancelled) setShareUrl(data.url); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [article.id]);

  // Pre-fetch summary in background so modal opens instantly
  useEffect(() => {
    if (aiSummary || summaryLoading || summaryFailed) return;
    let cancelled = false;
    const fetch = async () => {
      setSummaryLoading(true);
      try {
        const { data } = await api.post(`/api/articles/${article.id}/summarize`);
        if (!cancelled) setAiSummary(data.summary !== "Summary unavailable" ? data.summary : null);
      } catch {
        if (!cancelled) setSummaryFailed(true);
      } finally {
        if (!cancelled) setSummaryLoading(false);
      }
    };
    const t = setTimeout(fetch, (article.id % 10) * 400);
    return () => { cancelled = true; clearTimeout(t); };
  }, [article.id]);

  const toggleSave = async () => {
    const newSaved = !isSaved;
    setIsSaved(newSaved);
    try {
      await api.post(`/api/articles/${article.id}/interact?action=${newSaved ? "save_later" : "unsave"}`);
      if (newSaved) toast.success("🔖 Saved for later");
    } catch {
      setIsSaved(!newSaved);
      toast.error("Could not save article");
    }
  };

  const interact = async (newAction) => {
    const prev = action;
    setAction(newAction);
    try {
      await api.post(`/api/articles/${article.id}/interact?action=${newAction}`);
      onInteract?.(article.id, newAction);
      if (newAction === "like") toast.success("👍 Liked!");
      if (newAction === "dislike") toast("👎 Less of this.");
    } catch {
      setAction(prev);
      toast.error("Action failed");
    }
  };

  const timeAgo = article.published_at
    ? formatDistanceToNow(new Date(article.published_at), { addSuffix: true })
    : "";

  if (action === "hide") return null;

  // Pick a deterministic gradient for image placeholder based on topic
  const gradients = [
    "linear-gradient(135deg, #1a1f3a 0%, #0f1628 100%)",
    "linear-gradient(135deg, #1a2a1a 0%, #0f1a0f 100%)",
    "linear-gradient(135deg, #2a1a1a 0%, #1a0f0f 100%)",
    "linear-gradient(135deg, #1a1a2a 0%, #100f1a 100%)",
    "linear-gradient(135deg, #2a2014 0%, #1a1408 100%)",
  ];
  const placeholderGradient = gradients[article.topic_id % gradients.length];

  // Teaser text: 2-line preview shown on the card, click for full
  const teaserText = aiSummary
    ? aiSummary
    : (article.summary || "");

  const hasSummary = !!teaserText || summaryLoading;

  return (
    <>
      <div className="card article-card">
        {/* Fixed-height image slot — placeholder if no image */}
        <div className="article-image-slot">
          {article.image_url ? (
            <img
              src={article.image_url}
              alt=""
              loading="lazy"
              onError={e => { e.target.style.display = "none"; e.target.nextSibling.style.display = "flex"; }}
            />
          ) : null}
          <div className="article-image-placeholder" style={{ background: placeholderGradient }}>
            <span style={{ fontSize: 28, opacity: 0.4 }}>{article.topic_icon}</span>
          </div>
          {article.is_recommendation && (
            <div className="rec-badge">
              <Sparkles size={9} /> For you
            </div>
          )}
        </div>

        <div className="article-card-body">
          {/* Topic tag */}
          <div className="article-topic-tag">
            {article.topic_icon} {article.topic_name}
          </div>

          {/* Title — fixed 2 lines */}
          <h2 className="article-title">{article.title}</h2>

          {/* Summary teaser — click to open full popout */}
          <div
            className={`article-summary-teaser ${hasSummary ? "clickable" : ""}`}
            onClick={hasSummary ? () => setShowModal(true) : undefined}
            title={hasSummary ? "Click to read full AI summary" : ""}
          >
            {summaryLoading ? (
              <span className="summary-loading">
                <Loader2 size={11} style={{ animation: "spinning 1s linear infinite" }} />
                Summarising…
              </span>
            ) : teaserText ? (
              <>
                <span className="summary-label"><Sparkles size={9} /> AI</span>
                <span className="summary-text">{teaserText}</span>
                <span className="summary-expand">read more ›</span>
              </>
            ) : (
              <span className="summary-empty">No summary available</span>
            )}
          </div>

          {/* Meta */}
          <div className="article-meta">
            <span className="article-source">{article.source}</span>
            {timeAgo && <span>· {timeAgo}</span>}
          </div>

          {/* Actions */}
          <div className="article-actions">
            <button
              className={`action-btn ${action === "like" ? "liked" : ""}`}
              onClick={() => interact(action === "like" ? "read" : "like")}
              title="Like"
            >
              <ThumbsUp size={12} /> Like
            </button>
            <button
              className={`action-btn ${action === "dislike" ? "disliked" : ""}`}
              onClick={() => interact(action === "dislike" ? "read" : "dislike")}
              title="Less of this"
            >
              <ThumbsDown size={12} /> Less
            </button>
            <button className="action-btn" onClick={() => interact("hide")} title="Hide">
              <EyeOff size={12} />
            </button>
            <button
              className={`action-btn${isSaved ? " saved" : ""}`}
              onClick={toggleSave}
              title={isSaved ? "Remove from Read Later" : "Save for Later"}
            >
              <Bookmark size={12} />
            </button>
            <a
              href={shareUrl || "#"}
              target="_blank"
              rel="noreferrer"
              className="action-btn read-more"
            >
              Read <ExternalLink size={11} />
            </a>
          </div>
        </div>
      </div>

      {showModal && (
        <SummaryModal
          article={article}
          summary={aiSummary}
          loading={summaryLoading}
          onClose={() => setShowModal(false)}
          onInteract={interact}
          action={action}
          shareUrl={shareUrl}
        />
      )}
    </>
  );
}

// ── Feed Page ─────────────────────────────────────────────────────────────────
export default function FeedPage() {
  const [articles, setArticles]     = useState([]);
  const [subscribed, setSubscribed] = useState([]);
  const [selectedTopic, setSelectedTopic] = useState(null);
  const [page, setPage]     = useState(1);
  const [total, setTotal]   = useState(0);
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    api.get("/api/topics/subscribed").then(r => setSubscribed(r.data.topics));
  }, []);

  const fetchArticles = useCallback(async (reset = false) => {
    setLoading(true);
    const p = reset ? 1 : page;
    if (reset) setPage(1);
    try {
      const params = { page: p, per_page: 20 };
      if (selectedTopic) params.topic_id = selectedTopic;
      const { data } = await api.get("/api/articles/", { params });
      if (reset) {
        setArticles(data.articles);
      } else {
        setArticles(prev => {
          const seen = new Set(prev.map(a => a.url));
          return [...prev, ...data.articles.filter(a => !seen.has(a.url))];
        });
      }
      setTotal(data.total);
    } catch {
      toast.error("Failed to load articles");
    } finally {
      setLoading(false);
    }
  }, [selectedTopic, page]);

  useEffect(() => { fetchArticles(true); }, [selectedTopic]);

  const handleRefresh = async () => {
    setRefreshing(true);
    const toastId = toast.loading("Fetching latest articles...");
    try {
      const params = selectedTopic ? `?topic_id=${selectedTopic}` : "";
      await api.post(`/api/articles/refresh${params}`);
      await fetchArticles(true);
      toast.success("Feed refreshed!", { id: toastId });
    } catch {
      toast.error("Refresh failed", { id: toastId });
    } finally {
      setRefreshing(false);
    }
  };

  const visible = articles.filter(a => a.user_action !== "hide");

  return (
    <div>
      <div className="feed-filters">
        <button className={`filter-chip ${!selectedTopic ? "active" : ""}`} onClick={() => setSelectedTopic(null)}>
          🏠 All Topics
        </button>
        {subscribed.map(t => (
          <button
            key={t.id}
            className={`filter-chip ${selectedTopic === t.id ? "active" : ""}`}
            onClick={() => setSelectedTopic(t.id)}
          >
            {t.icon} {t.name}
          </button>
        ))}
        <button
          className="filter-chip"
          onClick={handleRefresh}
          disabled={refreshing}
          style={{ marginLeft: "auto", borderColor: "var(--accent)", color: "var(--accent)" }}
        >
          <RefreshCw size={13} style={refreshing ? { animation: "spinning 1s linear infinite" } : {}} />
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {loading && articles.length === 0 ? (
        <div className="empty-state">
          <div className="loader-ring" style={{ margin: "0 auto" }} />
          <p style={{ marginTop: 16, color: "var(--text3)" }}>Loading articles...</p>
        </div>
      ) : visible.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📭</div>
          <div className="empty-title">No articles yet</div>
          <div className="empty-desc">Subscribe to topics and click Refresh to fetch articles.</div>
          <button className="btn btn-primary" onClick={handleRefresh}>
            <RefreshCw size={15} /> Fetch Articles
          </button>
        </div>
      ) : (
        <>
          <div className="articles-grid">
            {visible.map(article => (
              <ArticleCard
                key={article.id}
                article={article}
                onInteract={(id, act) => {
                  if (act === "hide") setArticles(prev => prev.filter(a => a.id !== id));
                }}
              />
            ))}
          </div>
          {articles.length < total && (
            <div style={{ textAlign: "center", padding: "24px" }}>
              <button
                className="btn btn-ghost"
                onClick={() => { setPage(p => p + 1); fetchArticles(); }}
                disabled={loading}
              >
                {loading ? "Loading..." : `Load More (${total - articles.length} remaining)`}
              </button>
            </div>
          )}
        </>
      )}

      <style>{`@keyframes spinning { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
