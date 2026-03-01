"""Hacker News 'Who is Hiring?' connector."""
import re
import logging
from datetime import datetime, timezone
import httpx

from app.connectors.keywords import AI_KEYWORDS

logger = logging.getLogger(__name__)
REMOTE_KEYWORDS = re.compile(r'\b(remote|worldwide|anywhere|LATAM|Americas)\b', re.IGNORECASE)

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"


async def fetch_hn_jobs() -> list[dict]:
    """Fetch current month's Who's Hiring thread and parse AI/remote jobs."""
    now = datetime.now(timezone.utc)
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

    # Find the actual role title — skip generic types, locations, URLs
    generic_skip = re.compile(
        r'^(full.?time|part.?time|contract|freelance|remote|onsite|hybrid|'
        r'remote\s*\(.+\)(\s*\+.+)?|http|www|on.?site|relocat|anywhere|worldwide|'
        r'san francisco|new york|nyc|berlin|london|sf|la|eu|us|usa|'
        r'\d+k?\s*[-–]\s*\d+k?|salary|compensation|benefits)$',
        re.IGNORECASE
    )
    title = None
    for i in range(1, len(parts)):
        candidate = parts[i].strip()
        if candidate and not generic_skip.match(candidate) and len(candidate) > 3:
            title = candidate
            break

    # Fallback: extract role from description body if pipe parts were all generic
    if not title:
        role_match = re.search(
            r'(?:hiring|looking for|seeking|role|position)[:\s]+(?:a\s+)?'
            r'([A-Z][\w\s/]+(?:Engineer|Developer|Scientist|Analyst|Architect|Designer))',
            text
        )
        if role_match:
            title = role_match.group(1).strip()
        else:
            title = "Engineering Role"

    # Fix: clean company name — remove CLOSED/hiring notices, parenthetical stage info
    company = re.sub(r'\s*(?:CLOSED|closed|Closed)\s*[-–—]?\s*.*$', '', company).strip()
    # Truncate company at reasonable length
    if len(company) > 60:
        company = company[:60].rsplit(' ', 1)[0]

    # Fix: truncate title at reasonable boundary, remove dangling fragments
    if len(title) > 80:
        title = title[:80].rsplit(' ', 1)[0]

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
