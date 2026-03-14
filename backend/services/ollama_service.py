import httpx
import json
import re
from collections import Counter
import aiosqlite
from database import DB_PATH
import logging

logger = logging.getLogger(__name__)

async def get_ollama_config():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, value FROM app_settings WHERE key IN ('ollama_url','ollama_model')") as cur:
            rows = await cur.fetchall()
    config = {r["key"]: r["value"] for r in rows}
    return config.get("ollama_url", "http://localhost:11434"), config.get("ollama_model", "llama3.1:8b")

async def ollama_generate(prompt: str, system: str = None, max_tokens: int = 500) -> str:
    url, model = await get_ollama_config()
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.3}
    }
    if system:
        payload["system"] = system

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{url}/api/generate", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response", "").strip()
    except Exception as e:
        logger.error(f"Ollama error: {e}")
    return ""

async def get_ai_summary(text: str, title: str = "") -> str:
    if len(text) < 30:
        return ""

    prompt = f"""Article title: {title}

Article content: {text[:2000]}

Write a concise 2-3 sentence summary of this article. Be factual and informative.
Start directly with the key information — do NOT begin with phrases like "This article", "In this article", "The article", "This piece", or any similar meta-reference to the article itself."""

    return await ollama_generate(prompt, system="You are a news summarizer. Write brief, accurate summaries. Never begin with 'This article', 'In this article', 'The article discusses', or any similar opener. Start immediately with the substance.", max_tokens=150)

async def score_article_for_user(candidates: list, liked_articles: list, limit: int) -> list:
    if not candidates:
        return []

    # Step 1: Keyword scoring (fast, no AI needed)
    liked_words = Counter()
    for art in liked_articles:
        text = f"{art.get('title', '')} {art.get('ai_summary', '')}".lower()
        words = re.findall(r'\b[a-z]{4,}\b', text)
        liked_words.update(words)

    # Score each candidate
    stopwords = {'this', 'that', 'with', 'from', 'have', 'will', 'been', 'were',
                 'they', 'their', 'what', 'when', 'your', 'more', 'also', 'into'}

    for article in candidates:
        text = f"{article.get('title', '')} {article.get('ai_summary', '') or article.get('summary', '')}".lower()
        words = re.findall(r'\b[a-z]{4,}\b', text)
        keyword_score = sum(liked_words.get(w, 0) for w in words if w not in stopwords)
        article["_keyword_score"] = keyword_score

    # Sort by keyword score
    candidates.sort(key=lambda x: x["_keyword_score"], reverse=True)
    top_candidates = candidates[:min(limit * 3, 60)]

    # Step 2: AI re-ranking (if we have liked articles)
    if liked_articles and len(liked_articles) >= 3:
        try:
            liked_summary = "\n".join([
                f"- {a.get('title', '')}" for a in liked_articles[:10]
            ])
            candidate_list = "\n".join([
                f"{i+1}. {a.get('title', '')}" for i, a in enumerate(top_candidates[:20])
            ])

            prompt = f"""Based on the user's reading history, rank which articles they would most enjoy.

User's previously liked articles:
{liked_summary}

Articles to rank (by number):
{candidate_list}

Return ONLY a JSON array of article numbers in order from most to least relevant, like: [3,1,7,2,...]
Return only the JSON array, nothing else."""

            response = await ollama_generate(prompt, max_tokens=100)

            # Parse the ranking
            match = re.search(r'\[[\d,\s]+\]', response)
            if match:
                ranking = json.loads(match.group())
                ranked = []
                used = set()
                for idx in ranking:
                    i = int(idx) - 1
                    if 0 <= i < len(top_candidates) and i not in used:
                        ranked.append(top_candidates[i])
                        used.add(i)
                # Append any not included
                for i, art in enumerate(top_candidates):
                    if i not in used:
                        ranked.append(art)
                top_candidates = ranked
        except Exception as e:
            logger.warning(f"AI re-ranking failed: {e}")

    # Clean up internal score field
    for a in top_candidates:
        a.pop("_keyword_score", None)

    return top_candidates[:limit]

async def generate_digest_intro(articles: list) -> str:
    if not articles:
        return "Here are your top news stories for today."

    topics = list(set([a.get("topic_name", "") for a in articles[:5]]))
    headlines = "\n".join([f"- {a['title']}" for a in articles[:8]])

    prompt = f"""Write a friendly, engaging 2-3 sentence intro paragraph for a personalized news digest email.
The digest covers topics like: {', '.join(topics)}

Key headlines:
{headlines}

Write a warm, journalistic intro that summarizes the day's themes. Don't use the word 'digest'."""

    result = await ollama_generate(prompt, max_tokens=120)
    return result or "Here are your personalized news highlights for today."
