"""Jobicy API connector — free, no API key, remote-focused job board."""
import re
import logging
import httpx

from app.connectors.keywords import AI_KEYWORDS

logger = logging.getLogger(__name__)

JOBICY_API = "https://jobicy.com/api/v2/remote-jobs"


async def fetch_jobicy_jobs() -> list[dict]:
    """Fetch remote tech jobs from Jobicy free API."""
    all_jobs = []
    seen_urls = set()

    params_list = [
        {"count": "50", "tag": "python"},
        {"count": "50", "tag": "machine-learning"},
        {"count": "50", "tag": "data-science"},
    ]

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for params in params_list:
            try:
                resp = await client.get(JOBICY_API, params=params, headers={
                    "User-Agent": "JobRadarV3/1.0 (job search aggregator)"
                })
                resp.raise_for_status()
                data = resp.json()

                jobs_data = data.get("jobs", [])
                for entry in jobs_data:
                    url = entry.get("url", "")
                    if not url or url in seen_urls:
                        continue

                    title = entry.get("jobTitle", "")
                    company = entry.get("companyName", "")
                    description = entry.get("jobDescription", "") or ""

                    # Clean HTML
                    description = re.sub(r'<[^>]+>', ' ', description)
                    description = re.sub(r'&\w+;', ' ', description)
                    description = re.sub(r'\s+', ' ', description).strip()

                    combined = f"{title} {description}"
                    if not AI_KEYWORDS.search(combined):
                        continue

                    if not company:
                        continue

                    seen_urls.add(url)
                    geo = entry.get("jobGeo", "")
                    location_raw = geo if geo else "anywhere"

                    all_jobs.append({
                        "title": title[:200],
                        "url": url,
                        "description": description[:2000],
                        "company": company[:100],
                        "source": "jobicy",
                        "posted_at": entry.get("pubDate"),
                        "location_raw": location_raw,
                        "salary_min": _parse_salary(entry.get("annualSalaryMin")),
                        "salary_max": _parse_salary(entry.get("annualSalaryMax")),
                    })

                logger.info("Jobicy tag=%s: %d AI/ML jobs", params.get("tag"), len(jobs_data))
            except Exception as e:
                logger.error("Jobicy fetch failed for tag=%s: %s", params.get("tag"), e)

    logger.info("Jobicy total: %d unique jobs", len(all_jobs))
    return all_jobs


def _parse_salary(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
