"""
Settings router with security improvements:
- Sanitized error messages (no internal details leaked)
- Password never returned in API responses
"""
from fastapi import APIRouter, Depends, Query
from routers.auth import get_current_user, get_admin_user
from database import DB_PATH
import aiosqlite
import httpx
import logging

logger = logging.getLogger(__name__)
import ipaddress
import socket

def _is_safe_url(url: str) -> bool:
    """Block SSRF: reject private IPs, loopback, link-local, and non-http(s) schemes."""
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        # Resolve to IP
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        # Block private, loopback, link-local, and reserved ranges
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    except Exception:
        return False
    return True


router = APIRouter()

ADMIN_KEYS = {
    "ollama_url", "ollama_model", "refresh_interval_minutes",
    "newsapi_key", "smtp_host", "smtp_port", "smtp_user",
    "smtp_password", "smtp_from", "max_articles_per_topic", "auto_summarize", "country",
    "site_url", "article_retention_days", "read_later_expiry_days", "allow_signups"
}

@router.get("/app")
async def get_app_settings(current_user: dict = Depends(get_admin_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, value FROM app_settings") as cur:
            rows = await cur.fetchall()
    settings = {r["key"]: r["value"] for r in rows}
    # SECURITY FIX: Never return password in API response
    if "smtp_password" in settings:
        settings["smtp_password"] = ""
    return settings

@router.post("/app")
async def update_app_settings(data: dict, current_user: dict = Depends(get_admin_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        for key, value in data.items():
            if key not in ADMIN_KEYS:
                continue
            # Never blank a password — if the value is empty or placeholder, keep existing
            if key == "smtp_password":
                if not value or str(value).strip() == "":
                    continue  # Skip — keep whatever is stored
            await db.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
        await db.commit()
    return {"status": "saved"}

@router.get("/ollama/test")
async def test_ollama(
    url: str = Query(..., description="Ollama server URL to test"),
    current_user: dict = Depends(get_admin_user)
):
    """Test a connection to Ollama and return available models."""
    clean_url = url.strip().rstrip("/")
    if not _is_safe_url(clean_url):
        return {"success": False, "models": [], "error": "URL not permitted — private or invalid address"}
    logger.info(f"Testing Ollama connection to: {clean_url}")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{clean_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                logger.info(f"Ollama OK — {len(models)} models found")
                return {"success": True, "models": models, "url": clean_url}
            else:
                return {"success": False, "models": [], "error": f"Server returned HTTP {resp.status_code}"}
    except httpx.ConnectError:
        return {"success": False, "models": [], "error": "Connection refused — is Ollama running?"}
    except httpx.TimeoutException:
        return {"success": False, "models": [], "error": "Connection timed out — check the URL and firewall"}
    except Exception as e:
        # SECURITY FIX: Log full error internally, return generic message
        logger.error(f"Ollama test error: {e}")
        return {"success": False, "models": [], "error": "Connection failed"}

# SECURITY FIX: Changed from get_current_user to get_admin_user (CRIT-01)
@router.get("/ollama/models")
async def get_ollama_models(
    url: str = Query(None),
    current_user: dict = Depends(get_admin_user)
):
    """Get available Ollama models - ADMIN ONLY to prevent SSRF."""
    if not url:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT value FROM app_settings WHERE key = 'ollama_url'") as cur:
                row = await cur.fetchone()
        url = row["value"] if row else "http://localhost:11434"
    # SECURITY FIX: Validate URL before calling test_ollama
    if not _is_safe_url(url):
        return {"models": [], "error": "URL not permitted — private or invalid address"}
    result = await test_ollama(url=url, current_user=current_user)
    return {"models": result.get("models", []), "error": result.get("error")}

@router.get("/user")
async def get_user_settings(current_user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT key, value FROM user_settings WHERE user_id = ?",
            (current_user["id"],)
        ) as cur:
            rows = await cur.fetchall()
    return {r["key"]: r["value"] for r in rows}

USER_KEYS = {"timezone", "country", "articles_per_page", "theme", "read_later_expiry_days"}

@router.post("/user")
async def update_user_settings(data: dict, current_user: dict = Depends(get_current_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in data.items():
            if key not in USER_KEYS:
                continue
            await db.execute(
                "INSERT OR REPLACE INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
                (current_user["id"], key, str(value)[:500])  # length limit
            )
        await db.commit()
    return {"status": "saved"}
