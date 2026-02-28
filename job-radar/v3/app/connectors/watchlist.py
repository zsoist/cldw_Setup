"""Startup watchlist monitor — curated high-precision source."""
import logging
import httpx
from app.config import cfg

logger = logging.getLogger(__name__)

STARTUP_WATCHLIST = [
    {"name": "Together AI", "url": "https://jobs.ashbyhq.com/together", "ats": "ashby"},
    {"name": "Fireworks AI", "url": "https://jobs.ashbyhq.com/fireworks-ai", "ats": "ashby"},
    {"name": "Modal", "url": "https://jobs.ashbyhq.com/modal", "ats": "ashby"},
    {"name": "Replicate", "url": "https://jobs.lever.co/replicate", "ats": "lever"},
    {"name": "Mistral AI", "url": "https://jobs.ashbyhq.com/mistral", "ats": "ashby"},
    {"name": "Perplexity", "url": "https://jobs.ashbyhq.com/perplexity", "ats": "ashby"},
    {"name": "Cohere", "url": "https://jobs.lever.co/cohere", "ats": "lever"},
    {"name": "Weights & Biases", "url": "https://boards.greenhouse.io/wandb", "ats": "greenhouse"},
    {"name": "Pinecone", "url": "https://boards.greenhouse.io/pinecone", "ats": "greenhouse"},
    {"name": "Weaviate", "url": "https://boards.greenhouse.io/weaviate", "ats": "greenhouse"},
    {"name": "Lightning AI", "url": "https://jobs.lever.co/lightningai", "ats": "lever"},
    {"name": "Labelbox", "url": "https://boards.greenhouse.io/labelbox", "ats": "greenhouse"},
    {"name": "Anyscale", "url": "https://jobs.lever.co/anyscale", "ats": "lever"},
    {"name": "Character AI", "url": "https://boards.greenhouse.io/characterai", "ats": "greenhouse"},
    {"name": "Runway", "url": "https://boards.greenhouse.io/runwayml", "ats": "greenhouse"},
    {"name": "Hugging Face", "url": "https://apply.workable.com/huggingface", "ats": "workable"},
    {"name": "Stability AI", "url": "https://boards.greenhouse.io/stabilityai", "ats": "greenhouse"},
    {"name": "Grafana Labs", "url": "https://boards.greenhouse.io/grafanalabs", "ats": "greenhouse"},
    {"name": "GitLab", "url": "https://boards.greenhouse.io/gitlab", "ats": "greenhouse"},
    {"name": "Datadog", "url": "https://boards.greenhouse.io/datadog", "ats": "greenhouse"},
    {"name": "dbt Labs", "url": "https://boards.greenhouse.io/dbtlabsinc", "ats": "greenhouse"},
    {"name": "Prefect", "url": "https://boards.greenhouse.io/prefect", "ats": "greenhouse"},
    {"name": "Scale AI", "url": "https://boards.greenhouse.io/scaleai", "ats": "greenhouse"},
    {"name": "Deel", "url": "https://jobs.ashbyhq.com/Deel", "ats": "ashby"},
    {"name": "Remote.com", "url": "https://boards.greenhouse.io/remotecom", "ats": "greenhouse"},
    {"name": "Anthropic", "url": "https://boards.greenhouse.io/anthropic", "ats": "greenhouse"},
    {"name": "OpenAI", "url": "https://boards.greenhouse.io/openai", "ats": "greenhouse"},
]

# Keywords to filter relevant roles from careers pages
ROLE_KEYWORDS = [
    'engineer', 'developer', 'scientist', 'researcher', 'analyst',
    'ml', 'ai', 'machine learning', 'data', 'nlp', 'infrastructure',
    'platform', 'backend', 'full stack', 'intern',
]


async def fetch_watchlist_jobs() -> list[dict]:
    """Check watchlist companies via Brave search for current openings."""
    if not cfg.BRAVE_API_KEY:
        logger.warning("BRAVE_API_KEY not set, skipping watchlist")
        return []

    all_jobs = []
    seen_urls = set()

    async with httpx.AsyncClient(timeout=20) as client:
        for company in STARTUP_WATCHLIST:
            try:
                query = f'site:{_get_domain(company["url"])} {company["name"]} engineer OR scientist OR ML OR AI remote'
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": cfg.BRAVE_API_KEY, "Accept": "application/json"},
                    params={"q": query, "count": 5},
                )
                resp.raise_for_status()
                data = resp.json()

                for result in data.get("web", {}).get("results", []):
                    url = result.get("url", "")
                    title = result.get("title", "")

                    if url in seen_urls:
                        continue
                    # Filter: must look like a job posting
                    if not _is_job_posting(url, title):
                        continue

                    seen_urls.add(url)
                    all_jobs.append({
                        "title": _clean_title(title, company["name"]),
                        "url": url,
                        "description": result.get("description", ""),
                        "company": company["name"],
                        "source": "watchlist",
                        "ats_platform": company["ats"],
                    })

            except Exception as e:
                logger.error("Watchlist check failed for %s: %s", company["name"], e)

    logger.info("Watchlist: %d jobs from %d companies", len(all_jobs), len(STARTUP_WATCHLIST))
    return all_jobs


def _get_domain(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).hostname or ""


def _is_job_posting(url: str, title: str) -> bool:
    """Heuristic: is this URL likely a specific job posting?"""
    title_lower = title.lower()
    # Must match at least one role keyword
    has_role = any(kw in title_lower for kw in ROLE_KEYWORDS)
    # URL should not be a generic careers page
    is_generic = url.rstrip('/').endswith(('/careers', '/jobs', '/openings'))
    return has_role and not is_generic


def _clean_title(title: str, company: str) -> str:
    """Remove company name and noise from title."""
    import re
    # Remove "at Company" or "- Company" suffixes
    title = re.sub(rf'\s*(?:at|@|-|–|—|·)\s*{re.escape(company)}.*$', '', title, flags=re.IGNORECASE)
    # Remove "Company -" prefix
    title = re.sub(rf'^{re.escape(company)}\s*(?:-|–|—|·)\s*', '', title, flags=re.IGNORECASE)
    return title.strip()
