"""Gemini Flash enrichment — ONLY used for /job_why explanations. Not batch."""
import logging
import httpx
from app.config import cfg

logger = logging.getLogger(__name__)


async def explain_scores(job: dict) -> str:
    """Call Gemini Flash to produce a human-readable score explanation."""
    if not cfg.GEMINI_API_KEY:
        return _fallback_explanation(job)

    prompt = f"""You are a job search assistant. Explain why this job scored the way it did.
Be concise (max 150 words). Use bullet points.

Job: {job.get('title', 'Unknown')} @ {job.get('company_name', 'Unknown')}
Scores: Opportunity={job.get('score_opportunity',0)}, Junior={job.get('score_junior',0)}, Colombia={job.get('score_colombia',0)}, Composite={job.get('score_composite',0)}
Tech: {', '.join(job.get('tech_stack', []))}
Remote: {job.get('remote_policy', 'unknown')}
Seniority: {job.get('seniority_signal', 'unknown')}
YoE: {job.get('yoe_min', '?')}-{job.get('yoe_max', '?')}
Contractor OK: {job.get('contractor_ok', False)}
Description snippet: {(job.get('description_snippet', '') or '')[:500]}

Explain each score dimension briefly."""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.ENRICHMENT_MODEL}:generateContent"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                params={"key": cfg.GEMINI_API_KEY},
                json={"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"maxOutputTokens": 300, "temperature": 0.1}},
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return text.strip()
    except Exception as e:
        logger.warning("Gemini enrichment failed: %s", e)
        return _fallback_explanation(job)


def _fallback_explanation(job: dict) -> str:
    lines = []
    opp = job.get('score_opportunity', 0)
    jr = job.get('score_junior', 0)
    col = job.get('score_colombia', 0)

    if opp >= 60:
        lines.append(f"Opp {opp}: Good tech stack match, clear role definition")
    else:
        lines.append(f"Opp {opp}: Limited tech stack overlap or unclear role")

    if jr >= 60:
        lines.append(f"Jr {jr}: Accessible — low YoE requirements or junior-friendly signals")
    else:
        lines.append(f"Jr {jr}: Senior-leaning — high YoE or many requirements")

    if col >= 60:
        lines.append(f"COL {col}: Colombia-viable — remote-friendly, good timezone fit")
    elif col == 0:
        lines.append(f"COL {col}: Geo-blocked — US/EU only restriction detected")
    else:
        lines.append(f"COL {col}: Uncertain geo fit — no clear remote policy")

    return "\n".join(lines)
