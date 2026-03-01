"""Brave Search enrichment — fetch fuller job descriptions at zero LLM cost.

Strategy:
- Only enrich jobs with unclear remote policy AND decent composite score
- Uses Brave Web Search API (free tier) to get extended snippets
- Merges extra text into description, then rescores
- Budget: max 15 enrichment calls per sync cycle (cost = 0, rate limit only)
- Two query strategies: site-specific first, company+title fallback
"""
import re
import logging
import httpx
from app.config import cfg

logger = logging.getLogger(__name__)

MAX_ENRICH_PER_CYCLE = 15

# Domains where site: queries don't help (aggregators, not the company's own site)
_AGGREGATOR_DOMAINS = {
    'news.ycombinator.com', 'remoteok.com', 'weworkremotely.com',
    'jobicy.com', 'indeed.com', 'linkedin.com', 'glassdoor.com',
}


async def enrich_job_description(job: dict) -> str | None:
    """Fetch a fuller description for a job using Brave Search.

    Returns enriched description text or None if no improvement found.
    Uses two query strategies to maximize hit rate.
    """
    if not cfg.BRAVE_API_KEY:
        return None

    url = job.get("url", "")
    title = job.get("title", "")
    company = job.get("company", "")

    if not url or not company:
        return None

    domain = _get_domain(url)

    # Strategy 1: site-specific query (best for company career pages)
    # Strategy 2: company+title query (works for aggregator-sourced jobs)
    queries = []
    if domain and domain not in _AGGREGATOR_DOMAINS:
        queries.append(f'"{title}" "{company}" site:{domain}')
    queries.append(f'"{company}" "{title}" remote job description')

    fragments = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for query in queries:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "X-Subscription-Token": cfg.BRAVE_API_KEY,
                        "Accept": "application/json",
                    },
                    params={
                        "q": query,
                        "count": 3,
                        "extra_snippets": "true",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                results = data.get("web", {}).get("results", [])
                for result in results:
                    desc = result.get("description", "")
                    if desc:
                        fragments.append(_clean_html(desc))
                    for snippet in result.get("extra_snippets", []):
                        if snippet:
                            fragments.append(_clean_html(snippet))

                # If first query got good results, skip fallback
                if len(fragments) >= 3:
                    break

    except Exception as e:
        logger.warning("Brave enrichment failed for '%s': %s", title[:40], e)
        return None

    if not fragments:
        return None

    # Merge and deduplicate fragments
    merged = _merge_fragments(fragments)

    if len(merged) < 50:
        return None

    # Combine with existing description for maximum signal coverage
    current_desc = job.get("description", "")
    combined = f"{current_desc} {merged}" if current_desc else merged

    logger.info(
        "Enriched '%s' @ %s: %d → %d chars (+%d from Brave)",
        title[:40], company[:20], len(current_desc),
        len(combined), len(merged),
    )
    return combined[:2000]  # Cap at DB field limit


def should_enrich(job_row: dict) -> bool:
    """Decide if a stored job would benefit from enrichment."""
    remote = job_row.get("remote_policy", "")
    composite = job_row.get("score_composite", 0)

    # Enrich if: unclear remote AND decent score
    return (
        remote in ("remote_unspecified", "unknown")
        and composite >= 35
    )


def _get_domain(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return parsed.hostname or ""


def _clean_html(text: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&\w+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _merge_fragments(fragments: list[str]) -> str:
    """Merge text fragments, removing near-duplicates."""
    seen_sentences = set()
    merged_parts = []

    for frag in fragments:
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', frag)
        for sent in sentences:
            # Normalize for dedup
            norm = sent.lower().strip()[:80]
            if norm not in seen_sentences and len(sent) > 20:
                seen_sentences.add(norm)
                merged_parts.append(sent)

    return " ".join(merged_parts)
