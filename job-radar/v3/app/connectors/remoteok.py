"""RemoteOK JSON feed connector."""
import re
import logging
import httpx

logger = logging.getLogger(__name__)

REMOTEOK_FEEDS = [
    "https://remoteok.com/remote-ai-jobs.json",
    "https://remoteok.com/remote-machine-learning-jobs.json",
]


async def fetch_remoteok_jobs() -> list[dict]:
    """Fetch AI/ML jobs from RemoteOK JSON feeds."""
    all_jobs = []
    seen_urls = set()

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for feed_url in REMOTEOK_FEEDS:
            try:
                resp = await client.get(feed_url, headers={
                    "User-Agent": "JobRadarV3/1.0 (job search aggregator)"
                })
                resp.raise_for_status()
                entries = resp.json()

                # First entry is metadata, skip it
                for entry in entries[1:] if len(entries) > 1 else []:
                    url = entry.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    company = entry.get("company", "") or ""
                    if not company:
                        continue

                    description = entry.get("description", "") or ""
                    # RemoteOK sometimes has HTML in description
                    description = re.sub(r'<[^>]+>', ' ', description)
                    description = re.sub(r'\s+', ' ', description).strip()

                    all_jobs.append({
                        "title": entry.get("position", ""),
                        "url": f"https://remoteok.com{url}" if url.startswith('/') else url,
                        "description": description[:2000],
                        "company": company,
                        "source": "remoteok",
                        "posted_at": entry.get("date"),
                        "location_raw": entry.get("location", ""),
                        "salary_min": _parse_salary(entry.get("salary_min")),
                        "salary_max": _parse_salary(entry.get("salary_max")),
                        "tags": entry.get("tags", []),
                    })

                logger.info("RemoteOK %s: %d jobs", feed_url.split('/')[-1], len(entries) - 1)
            except Exception as e:
                logger.error("RemoteOK fetch failed for %s: %s", feed_url, e)

    logger.info("RemoteOK total: %d unique jobs", len(all_jobs))
    return all_jobs


def _parse_salary(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
