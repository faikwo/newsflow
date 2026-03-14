"""
Share link router — permanent, user-attributed article links.
SECURITY FIXES:
- Strict token validation with regex pattern
- Rate limiting on public share endpoint

GET  /r/{token}          — public redirect, no auth needed, tracks click
POST /api/share/{id}     — generate/retrieve share token for an article (requires auth)
"""
import re
import secrets
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
import aiosqlite
from database import DB_PATH
from routers.auth import get_current_user
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

router = APIRouter()
share_router = APIRouter()   # mounted at /r, no /api prefix

# SECURITY FIX: Rate limiter for public share endpoints
limiter = Limiter(key_func=get_remote_address)

# SECURITY FIX: Strict token validation pattern
# URL-safe base64: A-Z, a-z, 0-9, -, _
VALID_TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{22}$')


def _gen_token() -> str:
    """22 URL-safe base64 chars = 16 bytes = 128 bits of randomness."""
    return secrets.token_urlsafe(16)


async def _get_or_create_share_link(user_id: int, article_id: int) -> str:
    """
    Returns the permanent share token for this user+article pair.
    Creates one lazily if it doesn't exist yet.
    Guaranteed unique per user per article; different users get different tokens.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Check if one already exists for this user+article
        async with db.execute(
            "SELECT token FROM share_links WHERE user_id=? AND article_id=?",
            (user_id, article_id)
        ) as cur:
            row = await cur.fetchone()

        if row:
            return row["token"]

        # Create a new unique token — loop handles (astronomically unlikely) collision
        while True:
            token = _gen_token()
            try:
                await db.execute(
                    """INSERT INTO share_links (token, user_id, article_id)
                       VALUES (?, ?, ?)""",
                    (token, user_id, article_id)
                )
                await db.commit()
                return token
            except aiosqlite.IntegrityError:
                # Token collision — try again (expected frequency: never)
                continue


# ── POST /api/share/{article_id} ─────────────────────────────────────────────
# Called by the frontend when the user first clicks Read on an article.
# Returns the permanent share URL so the frontend can update the href.

@router.post("/{article_id}")
async def get_share_link(
    article_id: int,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]

    # Verify article exists
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id FROM articles WHERE id=?", (article_id,)) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Article not found")

    token = await _get_or_create_share_link(user_id, article_id)
    return {"token": token, "path": f"/r/{token}"}


# ── GET /r/{token} ────────────────────────────────────────────────────────────
# Public endpoint — no auth required.
# SECURITY FIX: Added rate limiting

@share_router.get("/{token}")
@limiter.limit("60/minute")  # SECURITY FIX: Rate limit public share links
async def follow_share_link(token: str, request: Request):
    # SECURITY FIX: Strict regex-based token validation
    if not VALID_TOKEN_PATTERN.match(token):
        raise HTTPException(status_code=404, detail="Invalid link")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """SELECT sl.user_id, sl.article_id, a.url
               FROM share_links sl
               JOIN articles a ON a.id = sl.article_id
               WHERE sl.token = ?""",
            (token,)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Link not found or expired")

        user_id    = row["user_id"]
        article_id = row["article_id"]
        real_url   = row["url"]

        # Increment click count and timestamp
        await db.execute(
            """UPDATE share_links
               SET click_count = click_count + 1,
                   last_clicked = datetime('now')
               WHERE token = ?""",
            (token,)
        )

        # Record in article_clicks
        await db.execute(
            "INSERT INTO article_clicks (user_id, article_id) VALUES (?, ?)",
            (user_id, article_id)
        )

        # Upsert read interaction — if already liked/disliked don't downgrade it
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

    # Update affinity async — multiple visits compound the signal
    from services.recommendation import update_affinity
    asyncio.create_task(update_affinity(user_id, article_id, "read"))

    return RedirectResponse(url=real_url, status_code=302)
