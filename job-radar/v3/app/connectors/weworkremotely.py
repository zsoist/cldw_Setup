"""WeWorkRemotely RSS feed connector — free, no API key."""
import re
import logging
import httpx

from app.connectors.keywords import AI_KEYWORDS

logger = logging.getLogger(__name__)

WWR_FEEDS = [
    "https://weworkremotely.com/remote-jobs.rss",
]


async def fetch_wwr_jobs() -> list[dict]:
    """Fetch AI/ML-relevant remote jobs from WeWorkRemotely RSS."""
    all_jobs = []
    seen_urls = set()

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for feed_url in WWR_FEEDS:
            try:
                resp = await client.get(feed_url, headers={
                    "User-Agent": "JobRadarV3/1.0 (job search aggregator)"
                })
                resp.raise_for_status()
                jobs = _parse_rss(resp.text, seen_urls)
                all_jobs.extend(jobs)
                logger.info("WWR %s: %d AI/ML jobs", feed_url.split('/')[-1], len(jobs))
            except Exception as e:
                logger.error("WWR fetch failed for %s: %s", feed_url, e)

    logger.info("WWR total: %d unique jobs", len(all_jobs))
    return all_jobs


def _parse_rss(xml_text: str, seen_urls: set) -> list[dict]:
    """Parse RSS XML without external dependency. Simple regex-based."""
    jobs = []
    items = re.findall(r'<item>(.*?)</item>', xml_text, re.DOTALL)

    for item in items:
        title = _extract_tag(item, 'title')
        link = _extract_tag(item, 'link')
        description = _extract_tag(item, 'description')
        pub_date = _extract_tag(item, 'pubDate')

        if not link or link in seen_urls:
            continue

        # Clean HTML from description
        clean_desc = re.sub(r'<[^>]+>', ' ', description)
        clean_desc = re.sub(r'&\w+;', ' ', clean_desc)
        clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

        combined = f"{title} {clean_desc}"
        if not AI_KEYWORDS.search(combined):
            continue

        seen_urls.add(link)

        # Extract company from title: "Company: Role" pattern
        company, role = _parse_title(title)

        jobs.append({
            "title": role[:200],
            "url": link,
            "description": clean_desc[:2000],
            "company": company[:100],
            "source": "wwr",
            "posted_at": pub_date,
        })

    return jobs


def _extract_tag(text: str, tag: str) -> str:
    m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', text, re.DOTALL)
    if m:
        content = m.group(1).strip()
        # Handle CDATA
        cdata = re.match(r'<!\[CDATA\[(.*?)\]\]>', content, re.DOTALL)
        if cdata:
            return cdata.group(1).strip()
        return content
    return ""


def _parse_title(title: str) -> tuple[str, str]:
    """Parse 'Company: Role' or 'Role at Company' patterns."""
    # WeWorkRemotely uses "Company: Role" format
    if ':' in title:
        parts = title.split(':', 1)
        return parts[0].strip(), parts[1].strip()
    m = re.search(r'^(.+?)\s+(?:at|@)\s+(.+)$', title)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    return "Unknown", title
