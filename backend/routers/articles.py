import asyncio
import html
import re
import secrets

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import RedirectResponse

from routers.auth import get_current_user
from database import DB_PATH
import aiosqlite
from services.ollama_service import get_ai_summary
from services.fetcher import fetch_articles_for_topic
from services.recommendation import build_feed, update_affinity

router = APIRouter()


# SECURITY FIX: Removed get_user_from_query_token function (HIGH-01)
# JWT tokens should NEVER be passed in URL query parameters as they leak to:
# - Server access logs
# - Browser history  
# - Referrer headers
# - Proxy/CDN logs
# Use Authorization: Bearer header instead.

# ── Text cleaning ─────────────────────────────────────────────────────────────

# Phrases Ollama likes to open with — strip them for cleaner card teasers
_SUMMARY_OPENERS = re.compile(
    r'^(this article\s+(discusses|covers|explores|examines|reports|looks at|is about|details|presents|explains)'
    r'|in this article[,\s]'
    r'|the article\s+(discusses|covers|explores|examines|reports|looks at|is about|details|presents|explains)'
    r'|this piece\s+(discusses|covers|explores|examines)'
    r'|the piece\s+(discusses|covers|explores|examines)'
    r'|according to (the article|this article)[,\s])',
    re.IGNORECASE
)

def clean_text(text: str) -> str:
    if not text:
        return text
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def clean_summary(text: str) -> str:
    """Clean text AND strip filler opener phrases."""
    text = clean_text(text)
    if not text:
        return text
    # Strip opener, then capitalise first letter
    stripped = _SUMMARY_OPENERS.sub('', text).strip().lstrip(',').strip()
    if stripped:
        text = stripped[0].upper() + stripped[1:]
    return text

def clean_article(a: dict) -> dict:
    a['title']      = clean_text(a.get('title', ''))
    a['summary']    = clean_text(a.get('summary', ''))
    a['ai_summary'] = clean_summary(a.get('ai_summary', ''))
    return a


# ── Share link helpers ────────────────────────────────────────────────────────

def _new_token() -> str:
    """128-bit URL-safe token, 22 chars. ~3.4×10³⁸ possible values."""
    return secrets.token_urlsafe(16)   # 16 bytes → 22 base64url chars

async def get_or_create_share_token(user_id: int, article_id: int) -> str:
    """Return existing token for this user+article, or create one."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT token FROM share_links WHERE user_id=? AND article_id=?",
            (user_id, article_id)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return row["token"]
        # Generate unique token (collision probability negligible but handle anyway)
        for _ in range(5):
            token = _new_token()
            try:
                await db.execute(
                    """INSERT INTO share_links (token, user_id, article_id)
                       VALUES (?, ?, ?)""",
                    (token, user_id, article_id)
                )
                await db.commit()
                return token
            except aiosqlite.IntegrityError:
                continue   # token collision — try again
    raise RuntimeError("Could not generate unique share token")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/")
async def get_articles(
    topic_id: int = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    result = await build_feed(
        user_id=current_user["id"],
        page=page,
        per_page=per_page,
        topic_id=topic_id
    )
    result["articles"] = [clean_article(a) for a in result["articles"]]
    return result


@router.post("/{article_id}/interact")
async def interact(
    article_id: int,
    action: str = Query(..., regex="^(like|dislike|hide|read|save_later|unsave)$"),
    current_user: dict = Depends(get_current_user)
):
    score_map = {"like": 1.0, "dislike": -1.0, "hide": -2.0, "read": 0.3}
    user_id = current_user["id"]

    async with aiosqlite.connect(DB_PATH) as db:
        if action == "save_later":
            await db.execute(
                "INSERT OR IGNORE INTO saved_articles (user_id, article_id) VALUES (?, ?)",
                (user_id, article_id)
            )
        elif action == "unsave":
            await db.execute(
                "DELETE FROM saved_articles WHERE user_id=? AND article_id=?",
                (user_id, article_id)
            )
        else:
            await db.execute("""
                INSERT INTO user_article_interactions (user_id, article_id, action, score)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, article_id) DO UPDATE SET
                    action=excluded.action, score=excluded.score,
                    interacted_at=CURRENT_TIMESTAMP
            """, (user_id, article_id, action, score_map.get(action, 0)))
        await db.commit()

    if action not in ("save_later", "unsave"):
        asyncio.create_task(update_affinity(user_id, article_id, action))
    return {"status": "ok", "action": action}


@router.get("/saved")
async def get_saved_articles(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Return articles saved for later, most recently saved first."""
    user_id = current_user["id"]
    offset = (page - 1) * per_page

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT a.*, t.name as topic_name, t.icon as topic_icon,
                   sa.saved_at,
                   uai.action as user_action
            FROM articles a
            LEFT JOIN topics t ON a.topic_id = t.id
            INNER JOIN saved_articles sa ON a.id = sa.article_id AND sa.user_id = ?
            LEFT JOIN user_article_interactions uai ON a.id = uai.article_id AND uai.user_id = ?
            ORDER BY sa.saved_at DESC
            LIMIT ? OFFSET ?
        """, (user_id, user_id, per_page, offset)) as cur:
            articles = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT COUNT(*) as c FROM saved_articles WHERE user_id = ?", (user_id,)
        ) as cur:
            total = (await cur.fetchone())["c"]

    return {"articles": [clean_article(a) for a in articles], "total": total}


@router.get("/{article_id}/share-token")
async def get_share_token(
    article_id: int,
    current_user: dict = Depends(get_current_user),
    request: Request = None
):
    """
    Returns (or lazily creates) the permanent share token for this user+article.
    Frontend uses this to build the copyable /r/<token> URL.
    """
    token = await get_or_create_share_token(current_user["id"], article_id)
    # Use Host header — contains the actual address:port the browser used
    # (e.g. 10.10.1.17:3025), so the link works correctly regardless of port.
    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", "http")
    base = f"{scheme}://{host}".rstrip("/") if host else str(request.base_url).rstrip("/")
    return {"token": token, "url": f"{base}/r/{token}"}


@router.get("/click/{article_id}")
async def track_click(
    article_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    JWT-authenticated click redirect (used when user is logged in and clicks
    the Read button in the app). Creates/returns a share token so the frontend
    can display the copyable /r/ URL after first click.
    """
    user_id = current_user["id"]

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT url FROM articles WHERE id = ?", (article_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Article not found")
        real_url = row["url"]

        await db.execute(
            "INSERT INTO article_clicks (user_id, article_id) VALUES (?, ?)",
            (user_id, article_id)
        )
        async with db.execute(
            "SELECT action FROM user_article_interactions WHERE user_id=? AND article_id=?",
            (user_id, article_id)
        ) as cur:
            existing = await cur.fetchone()
        if not existing:
            await db.execute(
                """INSERT INTO user_article_interactions (user_id, article_id, action, score)
                   VALUES (?, ?, 'read', 0.3)""",
                (user_id, article_id)
            )
        await db.commit()

    asyncio.create_task(update_affinity(user_id, article_id, "read"))
    # Ensure share token exists for this user+article
    asyncio.create_task(_ensure_share_token(user_id, article_id))
    return RedirectResponse(url=real_url, status_code=302)


async def _ensure_share_token(user_id: int, article_id: int):
    try:
        await get_or_create_share_token(user_id, article_id)
    except Exception:
        pass


@router.post("/{article_id}/summarize")
async def summarize_article(article_id: int, current_user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM articles WHERE id = ?", (article_id,)) as cur:
            article = await cur.fetchone()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    article = dict(article)
    if article.get("ai_summary"):
        return {"summary": clean_summary(article["ai_summary"])}

    text = article.get("content") or article.get("summary") or article.get("title", "")
    summary = await get_ai_summary(text, article["title"])

    if summary:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE articles SET ai_summary = ? WHERE id = ?", (summary, article_id))
            await db.commit()

    return {"summary": clean_summary(summary) if summary else "Summary unavailable"}


@router.post("/refresh")
async def refresh_articles(
    topic_id: int = None,
    current_user: dict = Depends(get_current_user)
):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if topic_id:
            async with db.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)) as cur:
                row = await cur.fetchone()
                topics = [dict(row)] if row else []
        else:
            async with db.execute("""
                SELECT t.* FROM topics t
                INNER JOIN user_topics ut ON t.id = ut.topic_id
                WHERE ut.user_id = ?
            """, (current_user["id"],)) as cur:
                topics = [dict(r) for r in await cur.fetchall()]

    count = 0
    for topic in topics:
        n = await fetch_articles_for_topic(topic)
        count += n
    return {"status": "ok", "articles_fetched": count}


@router.get("/affinity")
async def get_affinity(current_user: dict = Depends(get_current_user)):
    from services.recommendation import get_user_affinities
    affinities = await get_user_affinities(current_user["id"])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, name, icon FROM topics") as cur:
            topics = {r["id"]: dict(r) for r in await cur.fetchall()}
    result = []
    for tid, score in sorted(affinities.items(), key=lambda x: -x[1]):
        t = topics.get(tid, {})
        result.append({
            "topic_id": tid,
            "topic_name": t.get("name", "Unknown"),
            "topic_icon": t.get("icon", ""),
            "score": round(score, 3),
        })
    return {"affinities": result}
