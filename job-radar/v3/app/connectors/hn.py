"""Hacker News 'Who is Hiring?' connector."""
import re
import logging
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

AI_KEYWORDS = re.compile(
    r'\b(AI|ML|machine learning|deep learning|NLP|LLM|GPT|computer vision|'
    r'data scien|pytorch|tensorflow|mlops|GenAI)\b', re.IGNORECASE
)
REMOTE_KEYWORDS = re.compile(r'\b(remote|worldwide|anywhere|LATAM|Americas)\b', re.IGNORECASE)

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"


async def fetch_hn_jobs() -> list[dict]:
    """Fetch current month's Who's Hiring thread and parse AI/remote jobs."""
    now = datetime.utcnow()
    month_name = now.strftime("%B")
    year = now.year

    async with httpx.AsyncClient(timeout=30) as client:
        # Find the thread
        try:
            resp = await client.get(HN_SEARCH_URL, params={
                "query": f"Ask HN: Who is hiring? ({month_name} {year})",
                "tags": "story",
                "hitsPerPage": 1,
            })
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        except Exception as e:
            logger.error("HN thread search failed: %s", e)
            return []

        if not hits:
            logger.info("No HN Who's Hiring thread found for %s %d", month_name, year)
            return []

        thread_id = hits[0]["objectID"]
        logger.info("Found HN thread: %s (ID: %s)", hits[0].get("title", ""), thread_id)

        # Fetch top-level comments
        try:
            resp = await client.get(f"https://hn.algolia.com/api/v1/items/{thread_id}")
            resp.raise_for_status()
            children = resp.json().get("children", [])
        except Exception as e:
            logger.error("HN thread comments fetch failed: %s", e)
            return []

    jobs = []
    for comment in children:
        text = comment.get("text", "") or ""
        if not AI_KEYWORDS.search(text):
            continue
        if not REMOTE_KEYWORDS.search(text):
            continue

        parsed = _parse_hn_comment(text, comment.get("id", ""))
        if parsed:
            parsed["source"] = "hn"
            parsed["posted_at"] = comment.get("created_at")
            jobs.append(parsed)

    logger.info("HN: %d AI/remote jobs from %d comments", len(jobs), len(children))
    return jobs


def _parse_hn_comment(text: str, comment_id: str) -> dict | None:
    """Parse semi-structured HN comment into job dict."""
    # Clean HTML
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'&\w+;', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()

    if len(clean) < 50:
        return None

    # First line is usually "Company | Role | Location | ..."
    first_line = clean.split('.')[0] if '.' in clean[:200] else clean[:200]
    parts = re.split(r'\s*[|]\s*', first_line)

    company = parts[0].strip() if parts else "Unknown"
    title = parts[1].strip() if len(parts) > 1 else "Engineering Role"

    # Try to find URL
    url_match = re.search(r'(https?://\S+)', text)
    url = url_match.group(1) if url_match else f"https://news.ycombinator.com/item?id={comment_id}"
    # Clean trailing HTML artifacts from URL
    url = re.sub(r'[<"\'].*$', '', url)

    return {
        "title": title[:200],
        "url": url,
        "description": clean[:2000],
        "company": company[:100],
    }
