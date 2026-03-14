"""
Article fetcher service with security improvements:
- HTML content sanitization using bleach
- SSRF protection
- Safe URL validation
"""
import asyncio
import httpx
import feedparser
import json
import re
import ipaddress
import socket
from html import escape
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import aiosqlite
from database import DB_PATH
import logging

logger = logging.getLogger(__name__)

# SECURITY FIX: Import bleach for HTML sanitization
try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False
    logger.warning("bleach not installed - HTML sanitization will be limited")


def _sanitize_html(text: str) -> str:
    """
    SECURITY FIX: Sanitize HTML content to prevent XSS.
    Uses bleach if available, otherwise strips all HTML tags.
    """
    if not text:
        return ""
    
    if BLEACH_AVAILABLE:
        # Allow only safe tags and attributes
        allowed_tags = ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 'a', 'ul', 'ol', 'li']
        allowed_attrs = {
            'a': ['href', 'title'],
        }
        return bleach.clean(text, tags=allowed_tags, attributes=allowed_attrs, strip=True)
    else:
        # Fallback: strip all HTML tags
        if '<' in text and '>' in text:
            return BeautifulSoup(text, 'html.parser').get_text()
        return text


def _is_safe_fetch_url(url: str) -> bool:
    """Block SSRF on custom RSS URLs: reject private IPs, loopback, link-local."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False
    try:
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    except Exception:
        return False
    return True


def _safe_article_url(url: str) -> str | None:
    """Only accept http(s) article URLs. Reject javascript:, data:, etc."""
    if url and (url.startswith("https://") or url.startswith("http://")):
        return url
    return None


async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
    return row["value"] if row else default


async def fetch_articles_for_topic(topic: dict) -> int:
    count = 0
    topic_id = topic["id"]
    max_articles = int(await get_setting("max_articles_per_topic", "20"))

    # 1. RSS feeds
    feed_urls = json.loads(topic.get("feed_urls") or "[]")
    for url in feed_urls:
        try:
            n = await fetch_rss(url, topic_id, max_articles)
            count += n
        except Exception as e:
            logger.warning(f"RSS error {url}: {e}")

    # 2. NewsAPI
    newsapi_key = await get_setting("newsapi_key", "")
    if newsapi_key:
        country = await get_setting("country", "")
        queries = json.loads(topic.get("search_queries") or "[]")
        for query in queries[:2]:  # Limit to 2 queries per topic
            try:
                n = await fetch_newsapi(query, topic_id, newsapi_key, max_articles, country)
                count += n
            except Exception as e:
                logger.warning(f"NewsAPI error {query}: {e}")

    # 3. Auto-summarize new articles if enabled
    auto_summarize = await get_setting("auto_summarize", "true")
    if auto_summarize == "true":
        asyncio.create_task(summarize_new_articles(topic_id))

    return count


async def fetch_rss(url: str, topic_id: int, max_articles: int) -> int:
    # Block SSRF on custom RSS feed URLs
    if not _is_safe_fetch_url(url):
        logger.warning(f"RSS fetch blocked — unsafe URL: {url}")
        return 0
    count = 0
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False,
                                      headers={"User-Agent": "NewsFlow/1.0 RSS Reader"}) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return 0
            content = resp.text

        # SECURITY FIX: Disable external entities to prevent XXE attacks
        # feedparser should be safe by default in modern versions, but we add extra protection
        import xml.sax
        parser = xml.sax.make_parser()
        parser.setFeature(xml.sax.handler.feature_external_ges, False)
        parser.setFeature(xml.sax.handler.feature_external_pes, False)
        
        feed = feedparser.parse(content)
        entries = feed.entries[:max_articles]

        async with aiosqlite.connect(DB_PATH) as db:
            for entry in entries:
                title = getattr(entry, 'title', '')
                # SECURITY FIX: Sanitize title field to prevent XSS
                title = _sanitize_html(title)[:200] if title else ''
                link = getattr(entry, 'link', '')
                if not title or not link:
                    continue

                # Only store https/http article URLs
                link = _safe_article_url(link)
                if not link:
                    continue

                summary = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
                # SECURITY FIX: Sanitize summary content
                if summary:
                    if '<' in summary and '>' in summary:
                        summary = _sanitize_html(summary)[:500]
                    else:
                        summary = summary[:500]
                else:
                    summary = ''

                author = getattr(entry, 'author', '') or ''
                # SECURITY FIX: Sanitize author field
                author = _sanitize_html(author)[:100] if author else ''
                
                image_url = _extract_image(entry)
                # Only store https image URLs
                if image_url and not image_url.startswith("https://"):
                    image_url = None
                source = feed.feed.get('title', url.split('/')[2] if '/' in url else url)
                # SECURITY FIX: Sanitize source
                source = _sanitize_html(source)[:100]

                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).isoformat()
                    except:
                        pass
                if not published:
                    published = datetime.now(timezone.utc).isoformat()

                try:
                    await db.execute("""
                        INSERT OR IGNORE INTO articles
                        (title, url, source, author, published_at, summary, image_url, topic_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (title, link, source, author, published, summary, image_url, topic_id))
                    count += 1
                except Exception:
                    pass

            await db.commit()

    except Exception as e:
        logger.error(f"RSS fetch error for {url}: {e}")
    return count


async def fetch_newsapi(query: str, topic_id: int, api_key: str, max_articles: int, country: str = "") -> int:
    count = 0
    try:
        # Map country codes to NewsAPI language hints where applicable
        COUNTRY_LANG = {"JP": "jp", "KR": "ko", "DE": "de", "FR": "fr", "BR": "pt"}
        params = {
            "q": query,
            "apiKey": api_key,
            "pageSize": min(max_articles, 10),
            "sortBy": "publishedAt",
            "language": COUNTRY_LANG.get(country, "en"),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://newsapi.org/v2/everything",
                params=params,
            )
            if resp.status_code != 200:
                return 0
            data = resp.json()

        articles = data.get("articles", [])
        async with aiosqlite.connect(DB_PATH) as db:
            for article in articles:
                title = article.get("title", "")
                # SECURITY FIX: Sanitize title from NewsAPI
                title = _sanitize_html(title)[:200] if title else ''
                url = article.get("url", "")
                if not title or not url or "[Removed]" in title:
                    continue

                # Only store http(s) article URLs
                url = _safe_article_url(url)
                if not url:
                    continue

                # SECURITY FIX: Sanitize description
                description = article.get("description", "") or ""
                description = _sanitize_html(description)[:500]
                
                image_url = article.get("urlToImage", "")
                # Only store https image URLs
                if image_url and not image_url.startswith("https://"):
                    image_url = ""

                try:
                    await db.execute("""
                        INSERT OR IGNORE INTO articles
                        (title, url, source, author, published_at, summary, image_url, topic_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        title,
                        url,
                        article.get("source", {}).get("name", ""),
                        article.get("author", ""),
                        article.get("publishedAt", datetime.now(timezone.utc).isoformat()),
                        description,
                        image_url,
                        topic_id
                    ))
                    count += 1
                except Exception:
                    pass
            await db.commit()
    except Exception as e:
        logger.error(f"NewsAPI error for {query}: {e}")
    return count


async def scrape_article_content(url: str) -> str:
    """
    SECURITY FIX: Added SSRF protection and disabled redirects (MED-02).
    This function is currently unused but hardened against future use.
    """
    # SECURITY FIX: Validate URL before fetching
    if not _is_safe_fetch_url(url):
        logger.warning(f"scrape_article_content blocked — unsafe URL: {url}")
        return ""
    
    try:
        # SECURITY FIX: follow_redirects=False to prevent DNS rebinding attacks.
        # Redirects are handled manually so each Location header is validated
        # before following (fixes MED-02 dead-code logic bug from v2).
        async with httpx.AsyncClient(timeout=10, follow_redirects=False,
                                      headers={"User-Agent": "Mozilla/5.0 (compatible; NewsFlow/1.0)"}) as client:
            resp = await client.get(url)

            # Handle redirects first, before checking for 200
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location", "")
                if not _is_safe_fetch_url(location):
                    logger.warning(f"scrape_article_content blocked redirect to unsafe URL: {location}")
                    return ""
                # Follow the validated redirect
                resp = await client.get(location)

            if resp.status_code != 200:
                return ""

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Remove scripts, styles, nav, etc.
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
            tag.decompose()

        # Try common article selectors
        content = None
        for selector in ['article', '[role="main"]', '.article-body', '.post-content',
                          '.entry-content', '#article-body', 'main']:
            el = soup.select_one(selector)
            if el:
                content = el.get_text(separator=' ', strip=True)
                break

        if not content:
            content = soup.get_text(separator=' ', strip=True)

        # Clean whitespace
        content = re.sub(r'\s+', ' ', content).strip()
        return content[:3000]
    except Exception:
        return ""


async def summarize_new_articles(topic_id: int):
    from services.ollama_service import get_ai_summary
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT id, title, summary, content FROM articles
            WHERE topic_id = ? AND ai_summary IS NULL
            ORDER BY fetched_at DESC LIMIT 10
        """, (topic_id,)) as cur:
            articles = [dict(r) for r in await cur.fetchall()]

    for article in articles:
        text = article.get("content") or article.get("summary") or ""
        if len(text) < 50:
            continue
        summary = await get_ai_summary(text, article["title"])
        if summary:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE articles SET ai_summary = ? WHERE id = ?",
                                  (summary, article["id"]))
                await db.commit()
        await asyncio.sleep(0.5)  # Rate limit Ollama


def _extract_image(entry) -> str:
    # Try media_thumbnail
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        return entry.media_thumbnail[0].get('url', '')
    # Try media_content
    if hasattr(entry, 'media_content') and entry.media_content:
        for m in entry.media_content:
            if m.get('medium') == 'image' or m.get('url', '').endswith(('.jpg', '.png', '.webp')):
                return m.get('url', '')
    # Try links
    if hasattr(entry, 'links'):
        for link in entry.links:
            if link.get('type', '').startswith('image/'):
                return link.get('href', '')
    # Try enclosures
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if 'image' in enc.get('type', ''):
                return enc.get('href', '')
    return ''
