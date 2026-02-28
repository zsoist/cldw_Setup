"""4-layer deduplication engine. SQL-native where possible."""
import hashlib
import re
import logging
from difflib import SequenceMatcher
from urllib.parse import urlparse, parse_qs, urlencode

from app.config import cfg

logger = logging.getLogger(__name__)

# URL params to strip for canonical form
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
    'ref', 'source', 'gh_jid', 'gh_src', 'fbclid', 'gclid',
}


def canonical_url(url: str) -> str:
    parsed = urlparse(url.lower().strip())
    params = {k: v for k, v in parse_qs(parsed.query).items() if k not in TRACKING_PARAMS}
    clean_query = urlencode(params, doseq=True)
    host = (parsed.hostname or "").replace('www.', '')
    path = parsed.path.rstrip('/')
    return f"{host}{path}{'?' + clean_query if clean_query else ''}"


def content_hash(title: str, company: str, description_500: str) -> str:
    blob = f"{title.lower().strip()}|{company.lower().strip()}|{description_500.lower().strip()}"
    blob = re.sub(r'\s+', ' ', blob)
    return hashlib.sha256(blob.encode()).hexdigest()


def normalize_for_fuzzy(text: str) -> str:
    return re.sub(
        r'\b(sr\.?|jr\.?|senior|junior|lead|staff|principal|intern|i+|ii+)\b',
        '', text.lower()
    ).strip()


def fuzzy_match(title_a: str, company_a: str, title_b: str, company_b: str,
                threshold: float | None = None) -> bool:
    if threshold is None:
        threshold = cfg.DEDUP_FUZZY_THRESHOLD
    a = normalize_for_fuzzy(f"{company_a} {title_a}")
    b = normalize_for_fuzzy(f"{company_b} {title_b}")
    return SequenceMatcher(None, a, b).ratio() >= threshold


async def dedup_check(conn, job: dict) -> dict:
    """Run all 4 dedup layers. Returns {is_dup, layer, matched_id}."""

    # Layer 1: URL canonical
    canon = canonical_url(job['url'])
    row = await conn.fetchrow(
        "SELECT id FROM dedup_index WHERE url_canonical = $1", canon
    )
    if row:
        return {"is_dup": True, "layer": "url", "matched_id": str(row['id'])}

    # Also check jobs table directly
    row = await conn.fetchrow(
        "SELECT id FROM jobs WHERE url_canonical = $1", canon
    )
    if row:
        return {"is_dup": True, "layer": "url_jobs", "matched_id": str(row['id'])}

    # Layer 2: Content hash
    desc = (job.get('description', '') or '')[:500]
    chash = content_hash(job.get('title', ''), job.get('company', ''), desc)
    row = await conn.fetchrow(
        "SELECT id FROM dedup_index WHERE content_hash = $1", chash
    )
    if row:
        return {"is_dup": True, "layer": "content_hash", "matched_id": str(row['id'])}

    row = await conn.fetchrow(
        "SELECT id FROM jobs WHERE content_hash = $1", chash
    )
    if row:
        return {"is_dup": True, "layer": "content_hash_jobs", "matched_id": str(row['id'])}

    # Layer 3: Fuzzy match (recent window only, capped for performance)
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg.DEDUP_WINDOW_DAYS)
    recent = await conn.fetch(
        "SELECT id, title_normalized, company_normalized FROM dedup_index "
        "WHERE created_at > $1 LIMIT 500", cutoff
    )
    for r in recent:
        if fuzzy_match(
            job.get('title', ''), job.get('company', ''),
            r['title_normalized'] or '', r['company_normalized'] or ''
        ):
            return {"is_dup": True, "layer": "fuzzy", "matched_id": str(r['id'])}

    # Layer 4: Repost detection (same company, dismissed recently)
    company_norm = (job.get('company', '') or '').lower().strip()
    reposts = await conn.fetch("""
        SELECT j.id, j.title_normalized FROM jobs j
        JOIN companies c ON j.company_id = c.id
        JOIN job_feedback f ON f.job_id = j.id
        WHERE c.name_normalized = $1
          AND f.action = 'dismiss'
          AND f.created_at > now() - INTERVAL '30 days'
    """, company_norm)
    for r in reposts:
        if fuzzy_match(job.get('title', ''), job.get('company', ''),
                       r['title_normalized'] or '', job.get('company', '')):
            return {"is_dup": True, "layer": "repost", "matched_id": str(r['id'])}

    # Not a duplicate — insert into dedup index
    title_norm = normalize_for_fuzzy(job.get('title', ''))
    await conn.execute("""
        INSERT INTO dedup_index (url_canonical, content_hash, title_normalized, company_normalized,
                                 cluster_id, expires_at)
        VALUES ($1, $2, $3, $4, gen_random_uuid(), $5)
    """, canon, chash, title_norm, company_norm,
        datetime.now(timezone.utc) + timedelta(days=cfg.DEDUP_WINDOW_DAYS))

    return {"is_dup": False, "layer": None, "matched_id": None}
