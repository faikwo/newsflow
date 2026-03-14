import { useState, useEffect, useCallback } from "react";
import api from "../api";
import toast from "react-hot-toast";
import { formatDistanceToNow } from "date-fns";
import { Bookmark, BookmarkX, ExternalLink, Loader2, RefreshCw } from "lucide-react";

const PER_PAGE = 20;

export default function ReadLaterPage() {
  const [articles, setArticles] = useState([]);
  const [shareUrls, setShareUrls] = useState({}); // articleId -> share URL
  const [loading, setLoading]   = useState(true);
  const [total, setTotal]       = useState(0);
  const [page, setPage]         = useState(1);

  const load = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/articles/saved", { params: { page: p, per_page: PER_PAGE } });
      const arts = data.articles || [];
      setArticles(arts);
      setTotal(data.total || 0);
      setPage(p);

      // Fetch share tokens in parallel for all loaded articles
      const tokens = await Promise.allSettled(
        arts.map(a => api.get(`/api/articles/${a.id}/share-token`).then(r => [a.id, r.data.url]))
      );
      const urlMap = {};
      tokens.forEach(r => { if (r.status === "fulfilled") urlMap[r.value[0]] = r.value[1]; });
      setShareUrls(urlMap);
    } catch {
      toast.error("Failed to load saved articles");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(1); }, [load]);

  const unsave = async (articleId, title) => {
    try {
      await api.post(`/api/articles/${articleId}/interact?action=unsave`);
      setArticles(prev => prev.filter(a => a.id !== articleId));
      setTotal(prev => prev - 1);
      toast(`Removed "${title.slice(0, 40)}…" from Read Later`);
    } catch {
      toast.error("Could not remove article");
    }
  };

  const totalPages = Math.ceil(total / PER_PAGE);

  return (
    <div className="page-content" style={{ maxWidth: 760, margin: "0 auto", padding: "32px 24px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
        <div>
          <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, margin: 0 }}>
            <Bookmark size={22} style={{ verticalAlign: "middle", marginRight: 8, color: "#f59e0b" }} />
            Read Later
          </h1>
          {!loading && (
            <p style={{ color: "var(--text3)", fontSize: 13, margin: "4px 0 0" }}>
              {total === 0 ? "No saved articles" : `${total} saved article${total !== 1 ? "s" : ""}`}
            </p>
          )}
        </div>
        <button className="btn btn-ghost" onClick={() => load(page)} disabled={loading}>
          <RefreshCw size={14} className={loading ? "spinning" : ""} />
        </button>
      </div>

      {/* Empty state */}
      {!loading && articles.length === 0 && (
        <div style={{ textAlign: "center", padding: "80px 0", color: "var(--text3)" }}>
          <Bookmark size={48} style={{ opacity: 0.2, marginBottom: 16 }} />
          <p style={{ fontSize: 16, margin: 0 }}>Nothing saved yet</p>
          <p style={{ fontSize: 13, marginTop: 8 }}>
            Hit the <Bookmark size={12} style={{ verticalAlign: "middle" }} /> icon on any article card to save it here.
          </p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
          <Loader2 size={28} className="spinning" style={{ color: "var(--accent)" }} />
        </div>
      )}

      {/* Article list */}
      {!loading && articles.map(article => (
        <SavedArticleRow key={article.id} article={article} shareUrl={shareUrls[article.id]} onUnsave={unsave} />
      ))}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 32 }}>
          <button className="btn btn-ghost" disabled={page <= 1} onClick={() => load(page - 1)}>
            ← Prev
          </button>
          <span style={{ lineHeight: "36px", color: "var(--text3)", fontSize: 13 }}>
            {page} / {totalPages}
          </span>
          <button className="btn btn-ghost" disabled={page >= totalPages} onClick={() => load(page + 1)}>
            Next →
          </button>
        </div>
      )}

      <style>{`
        @keyframes spinning { to { transform: rotate(360deg); } }
        .spinning { animation: spinning 1s linear infinite; display: inline-block; }
      `}</style>
    </div>
  );
}

function SavedArticleRow({ article, shareUrl, onUnsave }) {
  const href = shareUrl || article.url;
  const savedAgo = article.saved_at
    ? formatDistanceToNow(new Date(article.saved_at), { addSuffix: true })
    : null;

  return (
    <div style={{
      display: "flex", gap: 16, padding: "18px 0",
      borderBottom: "1px solid var(--border)",
    }}>
      {/* Image */}
      {article.image_url ? (
        <img
          src={article.image_url}
          alt=""
          style={{ width: 90, height: 70, objectFit: "cover", borderRadius: 8, flexShrink: 0 }}
          onError={e => { e.target.style.display = "none"; }}
        />
      ) : (
        <div style={{
          width: 90, height: 70, borderRadius: 8, flexShrink: 0,
          background: "var(--bg3)", display: "flex", alignItems: "center",
          justifyContent: "center", fontSize: 24,
        }}>
          {article.topic_icon || "📰"}
        </div>
      )}

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
          <span style={{
            fontSize: 10, fontWeight: 700, color: "var(--accent)",
            background: "var(--accent-glow)", padding: "1px 6px", borderRadius: 10,
            textTransform: "uppercase", letterSpacing: "0.4px",
          }}>
            {article.topic_icon} {article.topic_name || "News"}
          </span>
          <span style={{ color: "var(--text3)", fontSize: 11 }}>{article.source}</span>
        </div>

        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          style={{
            color: "var(--text)", textDecoration: "none", fontWeight: 600,
            fontSize: 15, lineHeight: 1.4, display: "block",
          }}
        >
          {article.title}
        </a>

        {article.ai_summary && (
          <p style={{
            color: "var(--text2)", fontSize: 12, lineHeight: 1.5,
            margin: "5px 0 0",
            display: "-webkit-box", WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical", overflow: "hidden",
          }}>
            {article.ai_summary}
          </p>
        )}

        {/* Footer row */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
          {savedAgo && (
            <span style={{ color: "var(--text3)", fontSize: 11 }}>
              <Bookmark size={10} style={{ verticalAlign: "middle", marginRight: 3, color: "#f59e0b" }} />
              Saved {savedAgo}
            </span>
          )}
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="action-btn read-more"
            style={{ marginLeft: "auto", padding: "4px 10px", fontSize: 12 }}
          >
            Read <ExternalLink size={10} />
          </a>
          <button
            className="action-btn"
            onClick={() => onUnsave(article.id, article.title)}
            title="Remove from Read Later"
            style={{ color: "var(--text3)", padding: "4px 8px" }}
          >
            <BookmarkX size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
