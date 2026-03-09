"""REST API routes — for OpenClaw skill + programmatic access."""
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Query
from app.database import get_conn
from app.scoring.enrichment import explain_scores
from app.config import cfg, dyn

router = APIRouter(prefix="/api/v1")


@router.get("/jobs")
async def list_jobs(
    limit: int = Query(5, le=50),
    hidden_junior_only: bool = False,
    min_composite: int = Query(0, ge=0, le=100),
    status: str = Query("new"),
):
    async with get_conn() as conn:
        if hidden_junior_only:
            rows = await conn.fetch("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE j.status = $1 AND j.hidden_junior = true
                  AND j.discovered_at > now() - INTERVAL '21 days'
                  AND j.score_composite >= $2 AND c.auto_suppress = false
                ORDER BY j.score_composite DESC LIMIT $3
            """, status, min_composite, limit)
        else:
            rows = await conn.fetch("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE j.status = $1
                  AND j.discovered_at > now() - INTERVAL '21 days'
                  AND j.score_composite >= $2 AND c.auto_suppress = false
                ORDER BY j.score_composite DESC LIMIT $3
            """, status, min_composite, limit)

    return [dict(r) for r in rows]


@router.get("/jobs/search")
async def search_jobs(q: str, limit: int = 10):
    async with get_conn() as conn:
        rows = await conn.fetch("""
            SELECT j.*, c.name as company_name
            FROM jobs j JOIN companies c ON j.company_id = c.id
            WHERE (j.title ILIKE $1 OR c.name ILIKE $1 OR $2 = ANY(j.tech_stack))
              AND j.status NOT IN ('expired', 'closed')
            ORDER BY j.score_composite DESC LIMIT $3
        """, f"%{q}%", q.lower(), limit)
    return [dict(r) for r in rows]


@router.get("/jobs/{job_id}")
async def job_detail(job_id: str):
    async with get_conn() as conn:
        row = await conn.fetchrow("""
            SELECT j.*, c.name as company_name, c.careers_url, c.ats_platform
            FROM jobs j JOIN companies c ON j.company_id = c.id
            WHERE j.id = $1::uuid
        """, job_id)
    if not row:
        return {"error": "Job not found"}
    return dict(row)


@router.get("/jobs/{job_id}/why")
async def job_why(job_id: str):
    async with get_conn() as conn:
        row = await conn.fetchrow("""
            SELECT j.*, c.name as company_name, c.careers_url, c.ats_platform
            FROM jobs j JOIN companies c ON j.company_id = c.id
            WHERE j.id = $1::uuid
        """, job_id)
    if not row:
        return {"error": "Job not found"}
    explanation = await explain_scores(dict(row))
    return {"job_id": job_id, "explanation": explanation}


@router.post("/jobs/{job_id}/save")
async def save_job(job_id: str):
    async with get_conn() as conn:
        await conn.execute("UPDATE jobs SET status = 'saved' WHERE id = $1::uuid", job_id)
        await conn.execute(
            "INSERT INTO job_feedback (job_id, action) VALUES ($1::uuid, 'save')", job_id
        )
    return {"ok": True}


@router.post("/jobs/{job_id}/dismiss")
async def dismiss_job(job_id: str, reason: str = "other", note: str = ""):
    async with get_conn() as conn:
        await conn.execute("UPDATE jobs SET status = 'dismissed' WHERE id = $1::uuid", job_id)
        await conn.execute(
            "INSERT INTO job_feedback (job_id, action, reason, note) VALUES ($1::uuid, 'dismiss', $2, $3)",
            job_id, reason, note
        )
        company_dismissals = await conn.fetchval("""
            SELECT COUNT(*) FROM job_feedback f
            JOIN jobs j ON f.job_id = j.id
            WHERE j.company_id = (SELECT company_id FROM jobs WHERE id = $1::uuid)
              AND f.reason = 'company'
              AND f.created_at > now() - INTERVAL '90 days'
        """, job_id)
        if company_dismissals >= 3:
            await conn.execute("""
                UPDATE companies SET auto_suppress = true,
                    suppress_reason = 'Auto: 3+ company dismissals'
                WHERE id = (SELECT company_id FROM jobs WHERE id = $1::uuid)
            """, job_id)
    return {"ok": True, "reason": reason}


@router.post("/jobs/{job_id}/mark")
async def mark_job(job_id: str, status: str = "applied"):
    valid = {'applied', 'interviewing', 'offered', 'rejected', 'closed'}
    if status not in valid:
        return {"error": f"Invalid status. Valid: {valid}"}
    async with get_conn() as conn:
        await conn.execute("UPDATE jobs SET status = $1 WHERE id = $2::uuid", status, job_id)
        await conn.execute(
            "INSERT INTO job_feedback (job_id, action) VALUES ($1::uuid, $2)", job_id, status
        )
    return {"ok": True, "status": status}


@router.get("/stats")
async def pipeline_stats(days: int = 7):
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with get_conn() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE discovered_at > $1", cutoff
        )
        by_status = await conn.fetch(
            "SELECT status, COUNT(*) as count FROM jobs "
            "WHERE discovered_at > $1 GROUP BY status ORDER BY count DESC", cutoff
        )
        by_source = await conn.fetch(
            "SELECT source, COUNT(*) as count FROM jobs "
            "WHERE discovered_at > $1 GROUP BY source ORDER BY count DESC", cutoff
        )
        dismiss_reasons = await conn.fetch(
            "SELECT reason, COUNT(*) as count FROM job_feedback "
            "WHERE action = 'dismiss' AND created_at > $1 "
            "GROUP BY reason ORDER BY count DESC", cutoff
        )
    return {
        "window_days": days,
        "total_discovered": total,
        "by_status": [dict(r) for r in by_status],
        "by_source": [dict(r) for r in by_source],
        "dismiss_reasons": [dict(r) for r in dismiss_reasons],
    }


@router.post("/ingestion/sync")
async def trigger_sync():
    from app.ingestion.pipeline import run_discovery_sync
    asyncio.create_task(run_discovery_sync())
    return {"ok": True, "message": "Sync started. New jobs in ~1-2 min."}


# --- Scheduler management (used by Sentinel) ---

@router.get("/scheduler/status")
async def scheduler_status():
    from app.scheduler import get_scheduler_status_json
    return get_scheduler_status_json()


@router.post("/scheduler/pause")
async def scheduler_pause():
    from app.scheduler import pause_scheduler
    return {"ok": True, "message": pause_scheduler()}


@router.post("/scheduler/resume")
async def scheduler_resume():
    from app.scheduler import resume_scheduler
    return {"ok": True, "message": resume_scheduler()}


# --- Digest endpoint (consumed by OpenClaw skill) ---

@router.get("/digest")
async def get_digest(
    type: str = Query("am", regex="^(am|pm)$"),
    limit: int = Query(12, le=50),
    min_score: int = Query(0, ge=0, le=100),
):
    """Return digest-ready job data for OpenClaw to format and deliver."""
    effective_min = min_score if min_score > 0 else dyn('digest_min_composite')

    async with get_conn() as conn:
        # Top jobs by composite score
        rows = await conn.fetch("""
            SELECT j.id, j.title, j.url, j.description_snippet,
                   j.score_composite, j.score_opportunity, j.score_junior, j.score_colombia,
                   j.remote_policy, j.tech_stack, j.seniority_signal,
                   j.yoe_min, j.yoe_max, j.salary_min, j.salary_max,
                   j.contractor_ok, j.hidden_junior, j.confidence,
                   j.apply_url, j.discovered_at, j.source,
                   c.name as company_name, c.ats_platform
            FROM jobs j JOIN companies c ON j.company_id = c.id
            WHERE j.status = 'new'
              AND j.discovered_at > now() - INTERVAL '21 days'
              AND j.score_composite >= $1
              AND c.auto_suppress = false
            ORDER BY j.score_composite DESC
            LIMIT $2
        """, effective_min, limit)

        # Pipeline stats
        saved = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE status = 'saved'"
        ) or 0
        applied = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE status = 'applied'"
        ) or 0
        interviewing = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE status = 'interviewing'"
        ) or 0
        total_new = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE status = 'new' "
            "AND discovered_at > now() - INTERVAL '7 days'"
        ) or 0

    jobs = []
    hot_count = 0
    for r in rows:
        job = dict(r)
        # Convert datetime to ISO string for JSON
        if job.get("discovered_at"):
            job["discovered_at"] = job["discovered_at"].isoformat()
        # Count "hot" jobs (composite >= 70)
        if job.get("score_composite", 0) >= 70:
            hot_count += 1
        jobs.append(job)

    return {
        "type": type,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "jobs": jobs,
        "stats": {
            "total_new": total_new,
            "hot_count": hot_count,
            "saved": saved,
            "applied": applied,
            "interviewing": interviewing,
        },
    }
