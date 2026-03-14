from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import aiosqlite
import json
import logging
from database import DB_PATH

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

async def start_scheduler():
    try:
        scheduler.add_job(
            scheduled_fetch_all,
            trigger=IntervalTrigger(minutes=60),
            id="fetch_articles",
            replace_existing=True,
            misfire_grace_time=300
        )
        scheduler.add_job(
            check_and_send_digests,
            trigger=CronTrigger(minute="*"),  # Every minute — checks send time internally
            id="send_digests",
            replace_existing=True,
            misfire_grace_time=60
        )
        scheduler.add_job(
            nightly_maintenance,
            trigger=CronTrigger(hour=3, minute=0),  # 3am UTC
            id="nightly_maintenance",
            replace_existing=True
        )
        scheduler.start()
        print("[Scheduler] Started OK — digest job runs every minute", flush=True)
        logger.info("Scheduler started")
        await update_scheduler_interval()
    except Exception as e:
        print(f"[Scheduler] FAILED TO START: {e}", flush=True)
        logger.error(f"Scheduler failed to start: {e}")
        raise


async def nightly_maintenance():
    """Runs at 3am UTC: prune old articles + decay affinities + expire saved articles."""
    from services.recommendation import prune_old_articles, decay_affinities
    logger.info("Running nightly maintenance")
    try:
        deleted = await prune_old_articles()
        logger.info(f"Nightly prune: removed {deleted} old articles")
    except Exception as e:
        logger.error(f"Article pruning failed: {e}")
    try:
        await decay_affinities()
    except Exception as e:
        logger.error(f"Affinity decay failed: {e}")
    try:
        await expire_saved_articles()
    except Exception as e:
        logger.error(f"Saved article expiry failed: {e}")


async def expire_saved_articles():
    """Remove saved_articles entries older than each user's read_later_expiry_days setting."""
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Get global default
        async with db.execute(
            "SELECT value FROM app_settings WHERE key = 'read_later_expiry_days'"
        ) as cur:
            row = await cur.fetchone()
        default_days = int(row["value"]) if row else 30

        # Get per-user overrides
        async with db.execute(
            "SELECT user_id, value FROM user_settings WHERE key = 'read_later_expiry_days'"
        ) as cur:
            user_overrides = {r["user_id"]: int(r["value"]) for r in await cur.fetchall()}

        # Get all users with saved articles
        async with db.execute(
            "SELECT DISTINCT user_id FROM saved_articles"
        ) as cur:
            user_ids = [r["user_id"] for r in await cur.fetchall()]

        total_expired = 0
        for uid in user_ids:
            days = user_overrides.get(uid, default_days)
            if days == 0:
                continue  # 0 = never expire
            result = await db.execute(
                "DELETE FROM saved_articles WHERE user_id = ? AND saved_at < datetime('now', ? || ' days')",
                (uid, f"-{days}")
            )
            total_expired += result.rowcount
        await db.commit()
    logger.info(f"Expired {total_expired} saved article entries")

async def stop_scheduler():
    scheduler.shutdown(wait=False)

async def update_scheduler_interval():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT value FROM app_settings WHERE key = 'refresh_interval_minutes'") as cur:
            row = await cur.fetchone()
    minutes = int(row["value"]) if row else 60
    scheduler.reschedule_job("fetch_articles", trigger=IntervalTrigger(minutes=minutes))
    logger.info(f"Fetch interval set to {minutes} minutes")

async def scheduled_fetch_all():
    from services.fetcher import fetch_articles_for_topic
    logger.info("Starting scheduled article fetch")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT DISTINCT t.* FROM topics t
            INNER JOIN user_topics ut ON t.id = ut.topic_id
        """) as cur:
            topics = [dict(r) for r in await cur.fetchall()]

    total = 0
    for topic in topics:
        try:
            n = await fetch_articles_for_topic(topic)
            total += n
        except Exception as e:
            logger.error(f"Error fetching topic {topic['name']}: {e}")
    logger.info(f"Scheduled fetch complete: {total} articles")

async def check_and_send_digests():
    """
    Check every user's digest schedule and send if it's their send time.
    Converts their configured timezone to UTC before comparing to now.
    Handles multiple send_times per day.
    """
    from datetime import datetime, timezone, timedelta
    from routers.email_digest import send_digest_for_user

    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    now_utc = datetime.now(timezone.utc)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT ds.*, u.email, u.username, u.id as id
            FROM digest_schedule ds
            JOIN users u ON ds.user_id = u.id
            WHERE ds.enabled = 1
        """) as cur:
            schedules = [dict(r) for r in await cur.fetchall()]

    for sched in schedules:
        try:
            tz_name = sched.get("timezone") or "UTC"
            try:
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = ZoneInfo("UTC")

            # Current time in the user's timezone
            now_local = now_utc.astimezone(tz)
            current_hhmm = now_local.strftime("%H:%M")

            # Parse send_times — support both old single send_time and new JSON array
            raw = sched.get("send_times") or sched.get("send_time") or '["07:00"]'
            try:
                if raw.startswith("["):
                    send_times = json.loads(raw)
                else:
                    send_times = [raw]
            except Exception:
                send_times = ["07:00"]

            if current_hhmm not in send_times:
                continue

            # Don't resend within 50 minutes of last send (handles restarts/double-ticks)
            last_sent = sched.get("last_sent")
            if last_sent:
                try:
                    ls = datetime.fromisoformat(last_sent)
                    # last_sent is stored as UTC naive — make it aware
                    if ls.tzinfo is None:
                        ls = ls.replace(tzinfo=timezone.utc)
                    if (now_utc - ls).total_seconds() < 50 * 60:
                        continue
                except Exception:
                    pass

            logger.info(f"Sending digest to {sched['email']} (local time {current_hhmm} {tz_name})")
            await send_digest_for_user(sched)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE digest_schedule SET last_sent = datetime('now') WHERE user_id = ?",
                    (sched["user_id"],)
                )
                await db.commit()

        except Exception as e:
            logger.error(f"Error sending digest to {sched.get('email', '?')}: {e}")
