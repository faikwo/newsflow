from fastapi import APIRouter, Depends
from routers.auth import get_current_user
from database import DB_PATH
import aiosqlite

router = APIRouter()

@router.get("/stats")
async def get_user_stats(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Current state per article
        async with db.execute("""
            SELECT action, COUNT(*) as count FROM user_article_interactions
            WHERE user_id = ? GROUP BY action
        """, (user_id,)) as cur:
            interactions = {r["action"]: r["count"] for r in await cur.fetchall()}

        # Saved articles count (separate table)
        async with db.execute(
            "SELECT COUNT(*) as c FROM saved_articles WHERE user_id = ?", (user_id,)
        ) as cur:
            saved_count = (await cur.fetchone())["c"]

        # Top liked topics
        async with db.execute("""
            SELECT t.name, t.icon, COUNT(*) as count
            FROM user_article_interactions uai
            JOIN articles a ON uai.article_id = a.id
            JOIN topics t ON a.topic_id = t.id
            WHERE uai.user_id = ? AND uai.action = 'like'
            GROUP BY t.id ORDER BY count DESC LIMIT 10
        """, (user_id,)) as cur:
            top_topics = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT COUNT(*) as c FROM user_topics WHERE user_id = ?", (user_id,)
        ) as cur:
            sub_count = (await cur.fetchone())["c"]

    # Merge hide into dislike for display — both are negative signals
    interactions["dislike"] = interactions.get("dislike", 0) + interactions.get("hide", 0)
    interactions["saved"] = saved_count

    return {
        "interactions": interactions,
        "top_liked_topics": top_topics,
        "subscribed_topics": sub_count
    }
