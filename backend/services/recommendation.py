"""
Recommendation engine for NewsFlow.

Architecture:
  1. Topic Affinity — per-user per-topic score [0..1] updated on every interaction
  2. Article Scoring — composite of: topic affinity + keyword TF-IDF match + recency boost
  3. Feed Assembly — chronological feed with recommendation slots injected every N articles
  4. Ollama enrichment — used for cross-topic classification and AI-assisted ranking when
     the user has enough history to make it worthwhile

Affinity update rules (applied immediately on interaction):
  like      → +0.15 (capped at 1.0)
  read      → +0.05
  dislike   → -0.12
  hide      → -0.20
  no action → slow decay toward 0.5 over time (handled by nightly job)
"""

import asyncio
import math
import re
import json
import logging
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta

import aiosqlite
from database import DB_PATH

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

AFFINITY_DELTAS = {
    "like":    +0.15,
    "read":    +0.05,
    "dislike": -0.12,
    "hide":    -0.20,
}
AFFINITY_DEFAULT = 0.5
AFFINITY_MIN     = 0.05   # never completely suppress a topic
AFFINITY_MAX     = 1.0

# Recency boost: articles published within this many hours get a bonus
RECENCY_BOOST_HOURS = 6
RECENCY_BOOST_VALUE = 0.25

# How many feed slots between recommendation injections
REC_INJECT_EVERY = 5

STOPWORDS = {
    'this','that','with','from','have','will','been','were','they','their',
    'what','when','your','more','also','into','than','then','these','those',
    'about','after','before','would','could','should','there','which','while',
    'where','though','through','over','under','some','such','just','only',
    'even','back','than','much','most','many','both','each','other','same',
    'news','says','said','report','according','make','made','take','year',
    'time','first','last','week','month','today','yesterday','latest',
}

# ── Affinity helpers ──────────────────────────────────────────────────────────

async def update_affinity(user_id: int, article_id: int, action: str):
    """Called after every interaction. Updates topic affinity score."""
    delta = AFFINITY_DELTAS.get(action, 0)
    if delta == 0:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Get topic for this article
        async with db.execute(
            "SELECT topic_id FROM articles WHERE id = ?", (article_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return
        topic_id = row["topic_id"]

        # Upsert affinity
        async with db.execute(
            "SELECT score, interaction_count FROM user_topic_affinity WHERE user_id=? AND topic_id=?",
            (user_id, topic_id)
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            new_score = max(AFFINITY_MIN, min(AFFINITY_MAX, existing["score"] + delta))
            new_count = existing["interaction_count"] + 1
            await db.execute(
                """UPDATE user_topic_affinity
                   SET score=?, interaction_count=?, last_updated=datetime('now')
                   WHERE user_id=? AND topic_id=?""",
                (new_score, new_count, user_id, topic_id)
            )
        else:
            new_score = max(AFFINITY_MIN, min(AFFINITY_MAX, AFFINITY_DEFAULT + delta))
            await db.execute(
                """INSERT INTO user_topic_affinity (user_id, topic_id, score, interaction_count)
                   VALUES (?, ?, ?, 1)""",
                (user_id, topic_id, new_score)
            )
        await db.commit()

    # Also update cross-topic affinities using AI (async, non-blocking)
    asyncio.create_task(_update_cross_topic_affinity(user_id, article_id, action, delta))


async def _update_cross_topic_affinity(user_id: int, article_id: int, action: str, delta: float):
    """
    Use Ollama to decide if this article is relevant to other topics the user
    subscribes to, then apply a smaller affinity nudge to those topics too.
    Only runs for like/dislike since those are strong signals.
    """
    if action not in ("like", "dislike"):
        return
    cross_delta = delta * 0.4  # 40% spillover

    try:
        from services.ollama_service import ollama_generate

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT title, ai_summary, summary FROM articles WHERE id = ?", (article_id,)
            ) as cur:
                article = await cur.fetchone()
            if not article:
                return

            # Get user's subscribed topics (excluding the article's own topic)
            async with db.execute(
                """SELECT t.id, t.name FROM topics t
                   JOIN user_topics ut ON t.id = ut.topic_id
                   WHERE ut.user_id = ? AND t.id != (
                       SELECT topic_id FROM articles WHERE id = ?
                   )""",
                (user_id, article_id)
            ) as cur:
                other_topics = [dict(r) for r in await cur.fetchall()]

        if not other_topics or len(other_topics) > 30:
            return

        text = article["title"] + " " + (article["ai_summary"] or article["summary"] or "")
        topic_list = "\n".join(f"{t['id']}:{t['name']}" for t in other_topics)

        prompt = f"""An article titled "{article['title'][:200]}" has been {action}d by a user.
Article excerpt: {text[:400]}

From this list of topics, which (if any) are meaningfully related to this article's subject matter?
Only include topics with a genuine thematic connection — not superficial ones.
Topics:
{topic_list}

Reply ONLY with a JSON array of topic IDs that are related, like: [3, 17, 42]
If none are related, reply with: []"""

        response = await ollama_generate(prompt, max_tokens=80)
        match = re.search(r'\[[\d,\s]*\]', response)
        if not match:
            return

        related_ids = json.loads(match.group())
        if not related_ids:
            return

        valid_ids = {t["id"] for t in other_topics}
        async with aiosqlite.connect(DB_PATH) as db:
            for tid in related_ids:
                if tid not in valid_ids:
                    continue
                async with db.execute(
                    "SELECT score FROM user_topic_affinity WHERE user_id=? AND topic_id=?",
                    (user_id, tid)
                ) as cur:
                    existing = await cur.fetchone()
                if existing:
                    new_score = max(AFFINITY_MIN, min(AFFINITY_MAX, existing["score"] + cross_delta))
                    await db.execute(
                        "UPDATE user_topic_affinity SET score=?, last_updated=datetime('now') WHERE user_id=? AND topic_id=?",
                        (new_score, user_id, tid)
                    )
                else:
                    new_score = max(AFFINITY_MIN, min(AFFINITY_MAX, AFFINITY_DEFAULT + cross_delta))
                    await db.execute(
                        "INSERT INTO user_topic_affinity (user_id, topic_id, score, interaction_count) VALUES (?,?,?,0)",
                        (user_id, tid, new_score)
                    )
            await db.commit()
    except Exception as e:
        logger.debug(f"Cross-topic affinity update failed (non-critical): {e}")


async def get_user_affinities(user_id: int) -> dict:
    """Returns {topic_id: score} for all topics this user has affinity data for."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT topic_id, score FROM user_topic_affinity WHERE user_id = ?", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
    return {r["topic_id"]: r["score"] for r in rows}


# ── TF-IDF keyword scoring ────────────────────────────────────────────────────

def extract_keywords(text: str) -> list:
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    return [w for w in words if w not in STOPWORDS]


def build_user_tfidf(liked_articles: list) -> dict:
    """
    Build a simple TF-IDF-like keyword weight map from liked articles.
    Words that appear in few articles but with high frequency = high weight.
    """
    if not liked_articles:
        return {}

    N = len(liked_articles)
    doc_freq = Counter()   # how many docs contain this word
    term_freq = Counter()  # total occurrences across all docs

    for art in liked_articles:
        text = f"{art.get('title', '')} {art.get('ai_summary', '') or art.get('summary', '')}"
        words = set(extract_keywords(text))
        doc_freq.update(words)
        term_freq.update(extract_keywords(text))

    weights = {}
    for word, df in doc_freq.items():
        tf = term_freq[word] / max(sum(term_freq.values()), 1)
        idf = math.log((N + 1) / (df + 1)) + 1
        weights[word] = tf * idf

    return weights


def keyword_score(article: dict, tfidf_weights: dict) -> float:
    if not tfidf_weights:
        return 0.0
    text = f"{article.get('title', '')} {article.get('ai_summary', '') or article.get('summary', '')}"
    words = extract_keywords(text)
    score = sum(tfidf_weights.get(w, 0) for w in words)
    # Normalise to roughly [0..1]
    max_possible = sum(sorted(tfidf_weights.values(), reverse=True)[:20]) or 1
    return min(score / max_possible, 1.0)


def recency_score(published_at_str: str) -> float:
    """Returns a boost for recent articles, decaying over ~48h."""
    if not published_at_str:
        return 0.0
    try:
        pub = datetime.fromisoformat(published_at_str)
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
        # Exponential decay: full boost < 6h, half at ~12h, near-zero at 48h
        return RECENCY_BOOST_VALUE * math.exp(-age_hours / 16)
    except Exception:
        return 0.0


# ── Main scoring function ─────────────────────────────────────────────────────

async def score_articles_for_user(user_id: int, articles: list, liked_articles: list) -> list:
    """
    Score articles for a user using combined signals:
    - Topic affinity (learned from interactions)
    - TF-IDF keyword match against liked articles
    - Recency boost
    Returns articles with _rec_score attached, sorted best-first.
    """
    affinities = await get_user_affinities(user_id)
    tfidf = build_user_tfidf(liked_articles)
    has_history = len(liked_articles) >= 3

    for art in articles:
        topic_id = art.get("topic_id")
        # Topic affinity: default 0.5 if no data yet
        t_affinity = affinities.get(topic_id, AFFINITY_DEFAULT)

        # Keyword match
        kw = keyword_score(art, tfidf) if has_history else 0.0

        # Recency
        rec = recency_score(art.get("published_at", ""))

        # Composite score:
        # affinity × 0.5 + keyword × 0.35 + recency × 0.15
        # (affinity dominates once the user has history; recency keeps new articles visible)
        if has_history:
            art["_rec_score"] = t_affinity * 0.50 + kw * 0.35 + rec
        else:
            # New user: mostly recency + slight affinity seed
            art["_rec_score"] = rec * 0.6 + t_affinity * 0.4

    articles.sort(key=lambda x: x.get("_rec_score", 0), reverse=True)
    return articles


# ── Feed assembly ─────────────────────────────────────────────────────────────

async def build_feed(user_id: int, page: int, per_page: int, topic_id: int = None) -> dict:
    """
    Assemble the main feed:
    - Base: articles sorted by published_at DESC, filtered by topic affinity weight
    - Injected: every REC_INJECT_EVERY slots, insert a high-scoring recommendation
      that wouldn't otherwise appear at that position
    Returns {articles, total, recommendations_injected}
    """
    offset = (page - 1) * per_page
    # Fetch more than needed so we have pool for recommendations
    fetch_limit = per_page * 3

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if topic_id:
            base_query = """
                SELECT a.*, t.name as topic_name, t.icon as topic_icon,
                       uai.action as user_action,
                       CASE WHEN sa.article_id IS NOT NULL THEN 1 ELSE 0 END as is_saved
                FROM articles a
                LEFT JOIN topics t ON a.topic_id = t.id
                LEFT JOIN user_article_interactions uai ON a.id = uai.article_id AND uai.user_id = ?
                LEFT JOIN saved_articles sa ON a.id = sa.article_id AND sa.user_id = ?
                WHERE a.topic_id = ?
                  AND (uai.action IS NULL OR uai.action NOT IN ('hide'))
                  AND a.id IN (SELECT MIN(id) FROM articles WHERE topic_id = ? GROUP BY url)
                ORDER BY a.published_at DESC
                LIMIT ? OFFSET ?
            """
            async with db.execute(base_query, (user_id, user_id, topic_id, topic_id, fetch_limit, offset)) as cur:
                base_rows = await cur.fetchall()
            async with db.execute("SELECT COUNT(DISTINCT url) as c FROM articles WHERE topic_id = ?", (topic_id,)) as cur:
                total_row = await cur.fetchone()
        else:
            base_query = """
                SELECT a.*, t.name as topic_name, t.icon as topic_icon,
                       uai.action as user_action,
                       CASE WHEN sa.article_id IS NOT NULL THEN 1 ELSE 0 END as is_saved
                FROM articles a
                LEFT JOIN topics t ON a.topic_id = t.id
                LEFT JOIN user_article_interactions uai ON a.id = uai.article_id AND uai.user_id = ?
                LEFT JOIN saved_articles sa ON a.id = sa.article_id AND sa.user_id = ?
                INNER JOIN user_topics ut ON a.topic_id = ut.topic_id AND ut.user_id = ?
                WHERE (uai.action IS NULL OR uai.action NOT IN ('hide'))
                  AND a.id IN (
                      SELECT MIN(a2.id) FROM articles a2
                      INNER JOIN user_topics ut2 ON a2.topic_id = ut2.topic_id AND ut2.user_id = ?
                      GROUP BY a2.url
                  )
                ORDER BY a.published_at DESC
                LIMIT ? OFFSET ?
            """
            async with db.execute(base_query, (user_id, user_id, user_id, user_id, fetch_limit, offset)) as cur:
                base_rows = await cur.fetchall()
            async with db.execute("""SELECT COUNT(DISTINCT a.url) as c FROM articles a
                   INNER JOIN user_topics ut ON a.topic_id = ut.topic_id AND ut.user_id = ?""", (user_id,)) as cur:
                total_row = await cur.fetchone()

        # Get liked articles for scoring
        async with db.execute("""SELECT a.title, a.ai_summary, a.summary FROM articles a
               INNER JOIN user_article_interactions uai ON a.id = uai.article_id
               WHERE uai.user_id = ? AND uai.action = 'like'
               ORDER BY uai.interacted_at DESC LIMIT 50""", (user_id,)) as cur:
            liked_rows = await cur.fetchall()

    articles = [dict(r) for r in base_rows]
    liked = [dict(r) for r in liked_rows]
    total = total_row["c"] if total_row else 0

    # Score all fetched articles
    scored = await score_articles_for_user(user_id, articles, liked)

    # Split into chronological base and recommendation candidates
    # Base = top per_page by recency, Recs = high-scoring articles that aren't in base
    chrono = sorted(articles, key=lambda x: x.get("published_at", ""), reverse=True)[:per_page]
    chrono_ids = {a["id"] for a in chrono}

    # Recommendation pool: high-scoring articles not already in chrono window
    rec_pool = [a for a in scored if a["id"] not in chrono_ids]
    rec_pool = sorted(rec_pool, key=lambda x: x.get("_rec_score", 0), reverse=True)

    # Assemble feed: inject rec every REC_INJECT_EVERY slots
    feed = []
    rec_idx = 0
    recs_injected = 0
    for i, art in enumerate(chrono):
        feed.append({**art, "is_recommendation": False})
        # Inject a recommendation after every Nth article
        if (i + 1) % REC_INJECT_EVERY == 0 and rec_idx < len(rec_pool):
            rec = rec_pool[rec_idx]
            rec_idx += 1
            feed.append({**rec, "is_recommendation": True})
            recs_injected += 1

    # Clean internal score fields
    for a in feed:
        a.pop("_rec_score", None)

    return {
        "articles": feed,
        "total": total,
        "recommendations_injected": recs_injected
    }


# ── Affinity decay (run nightly) ──────────────────────────────────────────────

async def decay_affinities():
    """
    Slowly pull all affinity scores toward 0.5 for topics with no recent interaction.
    Topics with recent activity are left alone.
    Rate: 2% toward centre per day of inactivity, after 7 days of no interaction.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT user_id, topic_id, score FROM user_topic_affinity
            WHERE last_updated < datetime('now', '-7 days')
        """) as cur:
            rows = await cur.fetchall()

        for row in rows:
            current = row["score"]
            # Pull toward 0.5 by 2% of the distance
            new_score = current + 0.02 * (0.5 - current)
            new_score = max(AFFINITY_MIN, min(AFFINITY_MAX, new_score))
            await db.execute(
                "UPDATE user_topic_affinity SET score=? WHERE user_id=? AND topic_id=?",
                (new_score, row["user_id"], row["topic_id"])
            )
        await db.commit()
    logger.info(f"Affinity decay applied to {len(rows)} records")


# ── Article pruning ───────────────────────────────────────────────────────────

async def prune_old_articles():
    """
    Delete articles older than article_retention_days (default 30).
    Keeps articles that the user has interacted with (liked/read/etc).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT value FROM app_settings WHERE key = 'article_retention_days'"
        ) as cur:
            row = await cur.fetchone()
        days = int(row["value"]) if row else 30

        result = await db.execute("""
            DELETE FROM articles
            WHERE fetched_at < datetime('now', ? || ' days')
              AND id NOT IN (
                  SELECT DISTINCT article_id FROM user_article_interactions
              )
        """, (f"-{days}",))
        await db.commit()
        deleted = result.rowcount
    logger.info(f"Pruned {deleted} articles older than {days} days")
    return deleted
