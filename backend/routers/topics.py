from fastapi import APIRouter, Depends
from routers.auth import get_current_user
from database import DB_PATH
import aiosqlite

router = APIRouter()

@router.get("/")
async def get_all_topics(current_user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT t.*, 
                   CASE WHEN ut.user_id IS NOT NULL THEN 1 ELSE 0 END as subscribed,
                   COUNT(a.id) as article_count
            FROM topics t
            LEFT JOIN user_topics ut ON t.id = ut.topic_id AND ut.user_id = ?
            LEFT JOIN articles a ON t.id = a.topic_id
            GROUP BY t.id
            ORDER BY t.category, t.name
        """, (current_user["id"],)) as cur:
            rows = await cur.fetchall()

    topics = [dict(r) for r in rows]
    # Group by category
    grouped = {}
    for t in topics:
        cat = t["category"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(t)

    return {"topics": topics, "grouped": grouped}

@router.post("/{topic_id}/subscribe")
async def subscribe(topic_id: int, current_user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_topics (user_id, topic_id) VALUES (?, ?)",
            (current_user["id"], topic_id)
        )
        await db.commit()
    return {"status": "subscribed"}

@router.delete("/{topic_id}/subscribe")
async def unsubscribe(topic_id: int, current_user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM user_topics WHERE user_id = ? AND topic_id = ?",
            (current_user["id"], topic_id)
        )
        await db.commit()
    return {"status": "unsubscribed"}

@router.get("/subscribed")
async def get_subscribed(current_user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT t.*, COUNT(a.id) as article_count
            FROM topics t
            INNER JOIN user_topics ut ON t.id = ut.topic_id AND ut.user_id = ?
            LEFT JOIN articles a ON t.id = a.topic_id
            GROUP BY t.id
            ORDER BY t.category, t.name
        """, (current_user["id"],)) as cur:
            rows = await cur.fetchall()
    return {"topics": [dict(r) for r in rows]}
