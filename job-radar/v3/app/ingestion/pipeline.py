"""Ingestion pipeline: connector -> dedup -> score -> store."""
import logging
from datetime import datetime, timezone

from app.database import get_conn
from app.connectors.brave import fetch_brave_jobs
from app.connectors.hn import fetch_hn_jobs
from app.connectors.remoteok import fetch_remoteok_jobs
from app.connectors.watchlist import fetch_watchlist_jobs
from app.dedup.engine import dedup_check, canonical_url, content_hash
from app.scoring.rules import score_job
from app.scoring.apply_parser import parse_apply_info
from app.config import cfg

logger = logging.getLogger(__name__)


async def run_discovery_sync(sources: list[str] | None = None):
    """Full discovery pipeline. Returns stats dict."""
    stats = {"fetched": 0, "deduped": 0, "scored": 0, "stored": 0, "errors": 0}

    # 1. Fetch from all connectors
    raw_jobs = []
    connectors = {
        "brave": fetch_brave_jobs,
        "hn": fetch_hn_jobs,
        "remoteok": fetch_remoteok_jobs,
    }
    if sources:
        connectors = {k: v for k, v in connectors.items() if k in sources}

    for name, fetcher in connectors.items():
        try:
            jobs = await fetcher()
            raw_jobs.extend(jobs)
            logger.info("Connector %s: %d jobs", name, len(jobs))
        except Exception as e:
            logger.error("Connector %s failed: %s", name, e)
            stats["errors"] += 1

    stats["fetched"] = len(raw_jobs)
    logger.info("Total fetched: %d raw jobs", len(raw_jobs))

    # 2. Process each job: dedup -> score -> store
    async with get_conn() as conn:
        for job in raw_jobs:
            try:
                # Dedup
                dup = await dedup_check(conn, job)
                if dup["is_dup"]:
                    stats["deduped"] += 1
                    continue

                # Score
                title = job.get("title", "")
                desc = job.get("description", "")
                company = job.get("company", "")
                scores = score_job(title, desc, company)
                stats["scored"] += 1

                # Skip very low composite
                if scores.composite < 20:
                    continue

                # Apply info
                apply_info = parse_apply_info(
                    job.get("url", ""), desc,
                    job.get("ats_platform", "")
                )

                # Ensure company exists
                company_id = await _ensure_company(
                    conn, company,
                    ats_platform=job.get("ats_platform", ""),
                    watchlist=job.get("source") == "watchlist",
                )

                # Store job
                canon = canonical_url(job["url"])
                chash = content_hash(title, company, desc[:500])
                title_norm = title.lower().strip()

                await conn.execute("""
                    INSERT INTO jobs (
                        company_id, title, title_normalized, url, url_canonical,
                        source, description_snippet, tech_stack, seniority_signal,
                        yoe_min, yoe_max, salary_min, salary_max,
                        remote_policy, timezone_signal, contractor_ok,
                        location_raw,
                        score_opportunity, score_junior, score_colombia, score_composite,
                        score_method, confidence, hidden_junior,
                        apply_url, apply_method, apply_notes,
                        content_hash, status, posted_at, discovered_at,
                        expires_at
                    ) VALUES (
                        $1, $2, $3, $4, $5,
                        $6, $7, $8, $9,
                        $10, $11, $12, $13,
                        $14, $15, $16,
                        $17,
                        $18, $19, $20, $21,
                        $22, $23, $24,
                        $25, $26, $27,
                        $28, $29, $30, $31,
                        $32
                    )
                    ON CONFLICT (url_canonical) DO NOTHING
                """,
                    company_id, title, title_norm, job["url"], canon,
                    job.get("source", "unknown"), desc[:2000],
                    scores.tech_stack, scores.seniority_signal,
                    scores.yoe_min, scores.yoe_max, scores.salary_min, scores.salary_max,
                    scores.remote_policy, scores.timezone_signal, scores.contractor_ok,
                    job.get("location_raw", ""),
                    scores.opportunity, scores.junior, scores.colombia, scores.composite,
                    scores.method, scores.confidence, scores.hidden_junior,
                    apply_info["apply_url"], apply_info["apply_method"], apply_info["apply_notes"],
                    chash, "new",
                    _parse_timestamp(job.get("posted_at")),
                    datetime.now(timezone.utc),
                    None,  # expires_at set by cleanup job
                )
                stats["stored"] += 1

            except Exception as e:
                logger.error("Failed to process job '%s': %s", job.get("title", "?"), e)
                stats["errors"] += 1

    logger.info("Pipeline complete: %s", stats)
    return stats


async def run_watchlist_sync():
    """Separate watchlist sync (runs every 12h)."""
    stats = {"fetched": 0, "deduped": 0, "scored": 0, "stored": 0, "errors": 0}

    try:
        raw_jobs = await fetch_watchlist_jobs()
        stats["fetched"] = len(raw_jobs)
    except Exception as e:
        logger.error("Watchlist fetch failed: %s", e)
        return stats

    async with get_conn() as conn:
        for job in raw_jobs:
            try:
                dup = await dedup_check(conn, job)
                if dup["is_dup"]:
                    stats["deduped"] += 1
                    continue

                title = job.get("title", "")
                desc = job.get("description", "")
                company = job.get("company", "")
                scores = score_job(title, desc, company)
                stats["scored"] += 1

                if scores.composite < 20:
                    continue

                apply_info = parse_apply_info(job.get("url", ""), desc, job.get("ats_platform", ""))
                company_id = await _ensure_company(
                    conn, company, ats_platform=job.get("ats_platform", ""), watchlist=True,
                )

                canon = canonical_url(job["url"])
                chash = content_hash(title, company, desc[:500])

                await conn.execute("""
                    INSERT INTO jobs (
                        company_id, title, title_normalized, url, url_canonical,
                        source, description_snippet, tech_stack, seniority_signal,
                        yoe_min, yoe_max, salary_min, salary_max,
                        remote_policy, timezone_signal, contractor_ok,
                        score_opportunity, score_junior, score_colombia, score_composite,
                        score_method, confidence, hidden_junior,
                        apply_url, apply_method, apply_notes,
                        content_hash, status, discovered_at
                    ) VALUES (
                        $1, $2, $3, $4, $5,
                        $6, $7, $8, $9,
                        $10, $11, $12, $13,
                        $14, $15, $16,
                        $17, $18, $19, $20,
                        $21, $22, $23,
                        $24, $25, $26,
                        $27, $28, $29
                    )
                    ON CONFLICT (url_canonical) DO NOTHING
                """,
                    company_id, title, title.lower().strip(), job["url"], canon,
                    "watchlist", desc[:2000], scores.tech_stack, scores.seniority_signal,
                    scores.yoe_min, scores.yoe_max, scores.salary_min, scores.salary_max,
                    scores.remote_policy, scores.timezone_signal, scores.contractor_ok,
                    scores.opportunity, scores.junior, scores.colombia, scores.composite,
                    scores.method, scores.confidence, scores.hidden_junior,
                    apply_info["apply_url"], apply_info["apply_method"], apply_info["apply_notes"],
                    chash, "new", datetime.now(timezone.utc),
                )
                stats["stored"] += 1

            except Exception as e:
                logger.error("Watchlist job failed '%s': %s", job.get("title", "?"), e)
                stats["errors"] += 1

    logger.info("Watchlist sync complete: %s", stats)
    return stats


async def cleanup_expired():
    """Expire old jobs and clean dedup index."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg.JOB_MAX_AGE_DAYS)
    async with get_conn() as conn:
        # Expire jobs older than max age
        expired = await conn.execute(
            "UPDATE jobs SET status = 'expired' WHERE status = 'new' "
            "AND discovered_at < $1", cutoff
        )
        # Clean dedup index
        cleaned = await conn.execute(
            "DELETE FROM dedup_index WHERE expires_at < now()"
        )
        logger.info("Cleanup: expired jobs=%s, cleaned dedup=%s", expired, cleaned)


async def _ensure_company(conn, name: str, ats_platform: str = "", watchlist: bool = False):
    """Get or create company, return UUID."""
    name_norm = name.lower().strip()
    if not name_norm:
        name_norm = "unknown"
        name = "Unknown"

    row = await conn.fetchrow(
        "SELECT id FROM companies WHERE name_normalized = $1", name_norm
    )
    if row:
        # Update last_seen
        await conn.execute(
            "UPDATE companies SET last_seen_at = now() WHERE id = $1", row['id']
        )
        return row['id']

    row = await conn.fetchrow("""
        INSERT INTO companies (name, name_normalized, ats_platform, watchlist)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (name_normalized) DO UPDATE SET last_seen_at = now()
        RETURNING id
    """, name, name_norm, ats_platform or None, watchlist)
    return row['id']


def _parse_timestamp(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        from dateutil.parser import parse
        return parse(str(val))
    except Exception:
        return None
