"""Brave Web Search connector — primary job discovery source."""
import logging
import httpx
from app.config import cfg

logger = logging.getLogger(__name__)

BRAVE_QUERIES = [
    'remote AI engineer site:greenhouse.io OR site:lever.co OR site:ashbyhq.com',
    'remote "machine learning" engineer site:greenhouse.io OR site:ashbyhq.com OR site:wellfound.com',
    'remote ML engineer OR "AI engineer" entry OR junior site:lever.co OR site:workable.com',
    'remote python pytorch LLM engineer site:greenhouse.io OR site:lever.co',
    'remote NLP OR "computer vision" OR "deep learning" engineer site:ashbyhq.com OR site:greenhouse.io',
    'remote AI engineer LATAM OR "Latin America" OR "Americas timezone" site:wellfound.com OR site:lever.co OR site:ashbyhq.com',
]


async def fetch_brave_jobs() -> list[dict]:
    """Run all Brave queries and return raw job dicts."""
    if not cfg.BRAVE_API_KEY:
        logger.warning("BRAVE_API_KEY not set, skipping Brave connector")
        return []

    all_jobs = []
    seen_urls = set()

    async with httpx.AsyncClient(timeout=20) as client:
        for query in BRAVE_QUERIES:
            try:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": cfg.BRAVE_API_KEY, "Accept": "application/json"},
                    params={"q": query, "count": cfg.BRAVE_RESULTS_PER_QUERY, "freshness": "pm"},
                )
                resp.raise_for_status()
                data = resp.json()

                for result in data.get("web", {}).get("results", []):
                    url = result.get("url", "")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    all_jobs.append({
                        "title": result.get("title", ""),
                        "url": url,
                        "description": result.get("description", ""),
                        "company": _extract_company_from_url(url) or _extract_company_from_title(result.get("title", "")),
                        "source": "brave",
                        "posted_at": result.get("page_age"),
                    })

                logger.info("Brave query returned %d results: %s", len(data.get("web", {}).get("results", [])), query[:60])
            except Exception as e:
                logger.error("Brave query failed: %s — %s", query[:60], e)

    logger.info("Brave total: %d unique jobs from %d queries", len(all_jobs), len(BRAVE_QUERIES))
    return all_jobs


def _extract_company_from_url(url: str) -> str:
    """Try to extract company name from ATS URL patterns."""
    import re
    # boards.greenhouse.io/companyname
    m = re.search(r'greenhouse\.io/([\w-]+)', url)
    if m:
        return m.group(1).replace('-', ' ').title()
    # jobs.lever.co/companyname
    m = re.search(r'lever\.co/([\w-]+)', url)
    if m:
        return m.group(1).replace('-', ' ').title()
    # jobs.ashbyhq.com/companyname
    m = re.search(r'ashbyhq\.com/([\w-]+)', url)
    if m:
        return m.group(1).replace('-', ' ').title()
    # apply.workable.com/companyname
    m = re.search(r'workable\.com/([\w-]+)', url)
    if m:
        return m.group(1).replace('-', ' ').title()
    return ""


def _extract_company_from_title(title: str) -> str:
    """Fallback: try 'Role at Company' or 'Role - Company' patterns."""
    import re
    m = re.search(r'(?:at|@|-|–|—|·)\s*(.+?)(?:\s*[-|]|$)', title)
    if m:
        return m.group(1).strip()
    return ""
