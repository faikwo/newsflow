from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from routers.auth import get_current_user
from database import DB_PATH
import aiosqlite
import json
from services.email_service import send_digest_email
from services.ollama_service import generate_digest_intro

router = APIRouter()

# SECURITY FIX: Import SSRF protection
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.fetcher import _is_safe_fetch_url

@router.get("/schedule")
async def get_schedule(current_user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM digest_schedule WHERE user_id = ?",
            (current_user["id"],)
        ) as cur:
            row = await cur.fetchone()
    if row:
        d = dict(row)
        # Migrate legacy send_time -> send_times
        if "send_times" not in d or not d["send_times"]:
            d["send_times"] = json.dumps([d.get("send_time", "07:00")])
        return d
    return {
        "user_id": current_user["id"],
        "enabled": False,
        "send_times": json.dumps(["07:00"]),
        "timezone": "UTC"
    }

@router.post("/schedule")
async def update_schedule(data: dict, current_user: dict = Depends(get_current_user)):
    send_times = data.get("send_times", ["07:00"])
    if isinstance(send_times, str):
        send_times = json.loads(send_times)
    # Validate times
    valid_times = []
    for t in send_times:
        parts = str(t).strip().split(":")
        if len(parts) == 2:
            try:
                h, m = int(parts[0]), int(parts[1])
                if 0 <= h <= 23 and 0 <= m <= 59:
                    valid_times.append(f"{h:02d}:{m:02d}")
            except ValueError:
                pass
    if not valid_times:
        valid_times = ["07:00"]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO digest_schedule (user_id, enabled, send_times, timezone)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                enabled=excluded.enabled,
                send_times=excluded.send_times,
                timezone=excluded.timezone
        """, (
            current_user["id"],
            1 if data.get("enabled") else 0,
            json.dumps(valid_times),
            data.get("timezone", "UTC")
        ))
        await db.commit()
    return {"status": "saved", "send_times": valid_times}

@router.post("/send-now")
async def send_now(background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    background_tasks.add_task(send_digest_for_user, current_user)
    return {"status": "sending", "message": "Digest is being sent in the background"}

# ── Custom RSS feeds ──────────────────────────────────────────────────────────

@router.get("/custom-feeds")
async def get_custom_feeds(current_user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM custom_feeds WHERE user_id = ? ORDER BY created_at DESC",
            (current_user["id"],)
        ) as cur:
            rows = await cur.fetchall()
    return {"feeds": [dict(r) for r in rows]}

@router.post("/custom-feeds")
async def add_custom_feed(data: dict, current_user: dict = Depends(get_current_user)):
    url = (data.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    # SECURITY FIX: Validate URL before storing (MED-01)
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    if not _is_safe_fetch_url(url):
        raise HTTPException(status_code=400, detail="URL not permitted — private or invalid address")
    name = (data.get("name") or "").strip()
    topic_id = data.get("topic_id")
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO custom_feeds (user_id, url, name, topic_id) VALUES (?, ?, ?, ?)",
                (current_user["id"], url, name, topic_id)
            )
            await db.commit()
        except Exception:
            raise HTTPException(status_code=400, detail="Feed already exists")
    return {"status": "added"}

@router.delete("/custom-feeds/{feed_id}")
async def delete_custom_feed(feed_id: int, current_user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM custom_feeds WHERE id = ? AND user_id = ?",
            (feed_id, current_user["id"])
        )
        await db.commit()
    return {"status": "deleted"}

@router.post("/custom-feeds/{feed_id}/fetch")
async def fetch_custom_feed(feed_id: int, current_user: dict = Depends(get_current_user)):
    from services.fetcher import fetch_rss
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM custom_feeds WHERE id = ? AND user_id = ?",
            (feed_id, current_user["id"])
        ) as cur:
            feed = await cur.fetchone()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    feed = dict(feed)
    # Use topic_id if set, else first subscribed topic as a bucket
    topic_id = feed.get("topic_id")
    if not topic_id:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT topic_id FROM user_topics WHERE user_id = ? LIMIT 1",
                (current_user["id"],)
            ) as cur:
                row = await cur.fetchone()
            topic_id = row["topic_id"] if row else 1
    count = await fetch_rss(feed["url"], topic_id, 50)
    return {"status": "ok", "articles_fetched": count}

# ── Internal helper ───────────────────────────────────────────────────────────

async def send_digest_for_user(user: dict):
    user_id = user["id"]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT a.*, t.name as topic_name, t.icon as topic_icon
            FROM articles a
            JOIN topics t ON a.topic_id = t.id
            JOIN user_topics ut ON t.id = ut.topic_id AND ut.user_id = ?
            LEFT JOIN user_article_interactions uai ON a.id = uai.article_id AND uai.user_id = ?
            WHERE uai.action IS NULL AND a.published_at > datetime('now', '-24 hours')
            ORDER BY a.published_at DESC
            LIMIT 20
        """, (user_id, user_id)) as cur:
            articles = [dict(r) for r in await cur.fetchall()]

    if not articles:
        return

    intro = await generate_digest_intro(articles)
    await send_digest_email(user["email"], user["username"], user["id"], articles, intro)
