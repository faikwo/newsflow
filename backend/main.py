"""
NewsFlow API - Hardened main application module
SECURITY FIXES:
- Configurable CORS origins (not wildcard in production)
- Rate limiting on all endpoints
- Share router with rate limiting
"""
import os
import sys
import re
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from contextlib import asynccontextmanager
import asyncio

from database import init_db, DB_PATH
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from routers import auth, articles, topics, preferences, settings, email_digest
# SECURITY FIX: Import the share router with rate limiting
from routers.share import share_router, limiter as share_limiter
from services.scheduler import start_scheduler, stop_scheduler

# SECURITY FIX: Validate SECRET_KEY on startup
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY == "newsflow-secret-change-in-production-please":
    sys.exit(
        "FATAL: SECRET_KEY is not set or is still the default placeholder. "
        "Set a strong random SECRET_KEY in your .env file and restart."
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await start_scheduler()
    yield
    await stop_scheduler()

app = FastAPI(title="NewsFlow API", version="1.0.0", lifespan=lifespan)

# SECURITY FIX: Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# SECURITY FIX: Configurable CORS origins
# Default to localhost for development, but production should set ALLOWED_ORIGINS
def _parse_cors_origins():
    """Parse CORS origins from environment variable."""
    origins_env = os.getenv("ALLOWED_ORIGINS", "")
    if origins_env:
        # Split by comma and strip whitespace
        return [origin.strip() for origin in origins_env.split(",") if origin.strip()]
    # Default to localhost for development
    return ["http://localhost:3000", "http://127.0.0.1:3000"]

ALLOWED_ORIGINS = _parse_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(articles.router, prefix="/api/articles", tags=["articles"])
app.include_router(topics.router, prefix="/api/topics", tags=["topics"])
app.include_router(preferences.router, prefix="/api/preferences", tags=["preferences"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(email_digest.router, prefix="/api/digest", tags=["digest"])

# SECURITY FIX: Mount share router with rate limiting
app.include_router(share_router, tags=["share"])

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# URL scheme validation helper
def _validate_redirect_url(url: str) -> bool:
    """Only allow https:// and http:// redirects — block javascript:, data:, etc."""
    return url.startswith("https://") or url.startswith("http://")


# SECURITY FIX: Share link redirect with rate limiting
@app.get("/r/{token}")
@limiter.limit("60/minute")
async def share_link_redirect(token: str, request: Request):
    import aiosqlite
    from services.recommendation import update_affinity
    
    # SECURITY FIX: Strict token validation
    VALID_TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{22}$')
    if not VALID_TOKEN_PATTERN.match(token):
        return HTMLResponse(
            "<h2>Invalid link</h2><p>This share link format is invalid.</p>",
            status_code=404
        )

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """SELECT sl.user_id, sl.article_id, sl.click_count, a.url
               FROM share_links sl
               JOIN articles a ON a.id = sl.article_id
               WHERE sl.token = ?""",
            (token,)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            return HTMLResponse(
                "<h2>Link not found</h2><p>This share link is invalid or the article has been deleted.</p>",
                status_code=404
            )

        real_url = row["url"]

        # Validate URL scheme before redirecting
        if not _validate_redirect_url(real_url):
            return HTMLResponse("<h2>Invalid link</h2><p>This article URL is not safe to redirect to.</p>", status_code=400)

        user_id    = row["user_id"]
        article_id = row["article_id"]
        new_count  = row["click_count"] + 1

        await db.execute(
            """UPDATE share_links SET click_count = ?, last_clicked = datetime('now') WHERE token = ?""",
            (new_count, token)
        )
        await db.execute(
            "INSERT INTO article_clicks (user_id, article_id) VALUES (?, ?)",
            (user_id, article_id)
        )

        repeat_score = min(0.3 + (new_count - 1) * 0.05, 0.8)
        async with db.execute(
            "SELECT action, score FROM user_article_interactions WHERE user_id=? AND article_id=?",
            (user_id, article_id)
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            if existing["action"] in ("read", None):
                await db.execute(
                    """UPDATE user_article_interactions
                       SET action='read', score=?, interacted_at=datetime('now')
                       WHERE user_id=? AND article_id=?""",
                    (repeat_score, user_id, article_id)
                )
        else:
            await db.execute(
                """INSERT INTO user_article_interactions (user_id, article_id, action, score)
                   VALUES (?, ?, 'read', ?)""",
                (user_id, article_id, repeat_score)
            )

        await db.commit()

    asyncio.create_task(update_affinity(user_id, article_id, "read"))
    return RedirectResponse(url=real_url, status_code=302)
