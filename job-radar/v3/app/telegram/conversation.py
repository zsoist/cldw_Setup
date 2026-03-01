"""Natural language conversation engine — Gemini Flash intent routing.

Cost-optimized Gemini best practices:
- System instruction via dedicated field (elevated priority)
- 6 compact few-shot examples (short replies only — no verbose examples)
- Thinking budget = 0 (classification task, no reasoning needed)
- Structured JSON output via responseMimeType
- Conversation history capped at 3 pairs, 200 chars each
- Temperature 0.2, maxOutputTokens 400
- Robust JSON parser with truncation detection
- NEVER leaks raw JSON to the user
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from app.config import cfg, dyn, set_dynamic, DYNAMIC_DEFAULTS
from app.database import get_conn

logger = logging.getLogger(__name__)

# In-memory conversation history per chat
_history: dict[int, list[dict]] = {}
_MAX_HISTORY_PAIRS = 3
_MAX_HISTORY_CHARS = 200


@dataclass
class NLResponse:
    text: str
    jobs: list[dict] = field(default_factory=list)


# ── System Instruction (token-efficient: ~350 tokens) ────────────

SYSTEM_INSTRUCTION = """\
You are Job Radar, a Telegram job search assistant.
Owner: junior dev in Colombia seeking remote AI/ML roles.

# Scoring (deterministic, zero LLM)
Three dimensions 0-100:
- Opportunity ({w_opp}%): AI/ML tech matches, funded signals, salary
- Junior ({w_jr}%): YoE requirements, seniority signals, requirement count
- Colombia ({w_col}%): Remote policy, timezone flex, contractor OK
Composite = Opp*{w_opp_dec} + Jr*{w_jr_dec} + Col*{w_col_dec}
Hot = composite>=70 | Hidden junior = no seniority title + jr>=55 + <=7 reqs

# Config
{config_block}

# Sources (6 connectors)
Brave, HN Who's Hiring, RemoteOK, WeWorkRemotely, Jobicy, Watchlist (27 AI startups)
Sync 4x/day | AM digest 08:00 COT | PM 18:00 COT

# Tweakable (via "tweak" intent)
weight_opportunity/junior/colombia: 0-100 (must sum 100)
digest_min_composite: 0-100 | digest_max_jobs: 1-30 | job_max_age_days: 7-90

# Response: ALWAYS valid JSON
{{"intent":"search|explain|stats|tweak|system|chat","params":{{}},"reply":"short text"}}

Params by intent:
- search: {{"query":"text","filter":"hot|hidden|saved|applied|all","limit":5}}
- explain: {{"query":"company or title"}}
- stats: {{"days":7}}
- tweak: {{"key":"param_name","value":number}}
- system: {{"topic":"scoring|dedup|connectors|watchlist|digest"}}
- chat: {{}}

CRITICAL RULES:
- For search/stats/explain: keep "reply" to ONE short intro sentence. The system appends real data.
- For system/chat: put full answer in "reply" (max 3 short paragraphs).
- For tweak: confirm change in "reply".
- Match user's language. Never fabricate data. Be concise.
"""

# ── Few-Shot (6 compact examples, ~150 tokens total) ─────────────

FEW_SHOT = [
    ("show me the best jobs",
     '{"intent":"search","params":{"filter":"hot","limit":5},"reply":"Top-scoring active jobs:"}'),

    ("why did that Anthropic job score so low?",
     '{"intent":"explain","params":{"query":"Anthropic"},"reply":"Checking the Anthropic job scores."}'),

    ("how many jobs this week?",
     '{"intent":"stats","params":{"days":7},"reply":"Pipeline health (7d):"}'),

    ("give more weight to opportunity, set it to 40",
     '{"intent":"tweak","params":{"key":"weight_opportunity","value":40},"reply":"Opportunity weight set to 40%. Adjust junior/Colombia so weights sum to 100."}'),

    ("how does scoring work?",
     '{"intent":"system","params":{"topic":"scoring"},"reply":"Deterministic engine, zero LLM cost. Three dimensions: Opportunity (AI/ML tech matches, funded signals), Junior (YoE, seniority, requirement count), Colombia (remote policy, timezone, contractor OK). Composite = weighted average. 70+ = hot lead."}'),

    ("hola, buscar trabajos de RAG",
     '{"intent":"search","params":{"query":"rag","limit":10},"reply":"Buscando roles de RAG:"}'),

    ("buscar trabajos remotos para Colombia",
     '{"intent":"search","params":{"filter":"all","limit":10},"reply":"Trabajos remotos accesibles desde Colombia:"}'),

    ("full status report",
     '{"intent":"stats","params":{"days":7},"reply":"Full pipeline status report:"}'),

    ("search python machine learning",
     '{"intent":"search","params":{"query":"python machine learning","limit":10},"reply":"Python/ML jobs:"}'),
]


async def process_message(text: str, chat_id: int) -> NLResponse:
    """Process a plain-text message and return a structured response."""
    if not cfg.GEMINI_API_KEY:
        return NLResponse(text="Gemini API key not configured. Use /help for commands.")

    try:
        system = _build_system_instruction()
        result = await _call_gemini(system, text, chat_id)

        if not result:
            # Remove the failed user message from history to avoid pollution
            if chat_id in _history and _history[chat_id]:
                _history[chat_id] = [m for m in _history[chat_id] if m["text"] != text[:_MAX_HISTORY_CHARS]]
            return NLResponse(text="I couldn't process that. Try rephrasing, or use /help.")

        intent = result.get("intent", "chat")
        params = result.get("params", {})
        reply = result.get("reply", "")

        if intent == "search":
            return await _handle_search(params, reply, chat_id)
        elif intent == "explain":
            return await _handle_explain(params, reply, chat_id)
        elif intent == "stats":
            return await _handle_stats(params, reply)
        elif intent == "tweak":
            resp = await _handle_tweak(params, reply)
            _add_history(chat_id, "model", resp.text[:80])
            return resp
        else:
            _add_history(chat_id, "model", reply)
            return NLResponse(text=reply)

    except Exception as e:
        logger.error("Conversation error: %s", e, exc_info=True)
        return NLResponse(text="Something went wrong. Try /help for commands.")


# ── Search Term Extraction ───────────────────────────────────────

# Multi-word tech terms to keep as phrases (not split into words)
_MULTI_WORD_TECH = [
    'machine learning', 'deep learning', 'computer vision', 'reinforcement learning',
    'vector database', 'distributed training', 'model serving', 'vertex ai', 'azure ml',
    'github actions', 'fine tuning', 'fine-tuning', 'data science', 'data scientist',
    'data engineering', 'scikit-learn',
]

_SEARCH_NOISE = {
    'jobs', 'job', 'roles', 'role', 'positions', 'position', 'for', 'the', 'a', 'an',
    'remote', 'trabajo', 'trabajos', 'de', 'para', 'en', 'openings', 'opportunities',
    'with', 'and', 'or', 'in', 'at', 'buscar', 'search', 'find', 'show', 'me',
}


def _extract_search_terms(query: str) -> tuple[list[str], list[str]]:
    """Extract ILIKE patterns and tech_stack terms from a search query.

    Returns (like_patterns, tech_terms):
      - like_patterns: list of '%term%' for ILIKE ANY matching
      - tech_terms: list of lowercase terms for tech_stack && array overlap
    """
    query_lower = query.lower().strip()

    # Extract multi-word tech terms first
    tech_terms = []
    remaining = query_lower
    for mwt in _MULTI_WORD_TECH:
        if mwt in remaining:
            tech_terms.append(mwt)
            remaining = remaining.replace(mwt, ' ')

    # Single-word terms (after removing noise words)
    words = [w for w in remaining.split() if w not in _SEARCH_NOISE and len(w) > 1]
    tech_terms.extend(words)

    # ILIKE patterns: full query + individual terms
    like_patterns = [f"%{query_lower}%"]
    for term in tech_terms:
        pattern = f"%{term}%"
        if pattern not in like_patterns:
            like_patterns.append(pattern)

    return like_patterns, tech_terms


# ── Intent Handlers ──────────────────────────────────────────────

_LOCATION_ONLY = re.compile(
    r'^(remote|remoto|colombia|latam|worldwide|anywhere|para colombia|'
    r'remote jobs|trabajos remotos|remote for colombia)$', re.IGNORECASE
)

# Minimum opportunity score — filters out non-tech roles in browse mode
_MIN_OPP = 30


async def _handle_search(params: dict, reply: str, chat_id: int) -> NLResponse:
    """Search jobs in the database."""
    query = params.get("query", "")
    filter_mode = params.get("filter", "all")
    limit = min(int(params.get("limit", 5)), 15)

    # Strip location-only queries — all results are already filtered
    if query and _LOCATION_ONLY.match(query.strip()):
        query = ""  # Fall through to default "all" listing

    async with get_conn() as conn:
        if filter_mode == "hot":
            rows = await conn.fetch("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE j.status NOT IN ('dismissed','expired','closed')
                  AND j.score_composite >= 70
                  AND j.score_opportunity >= $2
                  AND j.remote_policy NOT IN ('us_only', 'hybrid')
                  AND j.discovered_at > now() - INTERVAL '21 days'
                  AND c.auto_suppress = false
                ORDER BY j.score_composite DESC LIMIT $1
            """, limit, _MIN_OPP)
        elif filter_mode == "hidden":
            rows = await conn.fetch("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE j.status NOT IN ('dismissed','expired','closed')
                  AND j.hidden_junior = true
                  AND j.score_opportunity >= $2
                  AND j.score_composite < 70
                  AND j.remote_policy NOT IN ('us_only', 'hybrid')
                  AND j.discovered_at > now() - INTERVAL '21 days'
                  AND c.auto_suppress = false
                ORDER BY j.score_composite DESC LIMIT $1
            """, limit, _MIN_OPP)
        elif filter_mode == "saved":
            rows = await conn.fetch("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE j.status = 'saved'
                ORDER BY j.score_composite DESC LIMIT $1
            """, limit)
        elif filter_mode == "applied":
            rows = await conn.fetch("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE j.status IN ('applied','interviewing','offered')
                ORDER BY j.discovered_at DESC LIMIT $1
            """, limit)
        elif query:
            # Explicit text search: split into terms, no geo/opp filters
            like_patterns, tech_terms = _extract_search_terms(query)
            rows = await conn.fetch("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE (j.title ILIKE ANY($1::text[])
                       OR c.name ILIKE ANY($1::text[])
                       OR j.tech_stack && $2::text[]
                       OR j.description_snippet ILIKE ANY($1::text[]))
                  AND j.status NOT IN ('expired','closed')
                ORDER BY j.score_composite DESC LIMIT $3
            """, like_patterns, tech_terms, limit)
        else:
            rows = await conn.fetch("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE j.status NOT IN ('dismissed','expired','closed')
                  AND j.score_opportunity >= $2
                  AND j.remote_policy NOT IN ('us_only', 'hybrid')
                  AND j.discovered_at > now() - INTERVAL '21 days'
                  AND c.auto_suppress = false
                ORDER BY j.score_composite DESC LIMIT $1
            """, limit, _MIN_OPP)

    if not rows:
        return NLResponse(text=f"{reply}\n\nNo jobs found matching that criteria.")

    jobs = [dict(r) for r in rows]
    summary = ", ".join(
        f"{j['title']}@{j.get('company_name','?')}({j.get('score_composite',0)})"
        for j in jobs[:5]
    )
    _add_history(chat_id, "model", f"Showed: {summary}")
    return NLResponse(text=reply, jobs=jobs)


async def _handle_explain(params: dict, reply: str, chat_id: int) -> NLResponse:
    """Find a job and explain its scores using Gemini."""
    query = params.get("query", "")
    if not query:
        return NLResponse(text="Which job? Give me a company name or job title.")

    async with get_conn() as conn:
        row = None

        if '@' in query:
            # Gemini often generates "Title@Company" from conversation history
            parts = query.split('@', 1)
            title_q = parts[0].strip()
            company_q = re.sub(r'\(\d+\)$', '', parts[1].strip()).strip()
            row = await conn.fetchrow("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE j.title ILIKE $1 AND c.name ILIKE $2
                  AND j.status NOT IN ('expired', 'closed')
                ORDER BY j.score_composite DESC LIMIT 1
            """, f"%{title_q}%", f"%{company_q}%")
            if not row:
                # Fallback: company name only
                row = await conn.fetchrow("""
                    SELECT j.*, c.name as company_name, c.ats_platform
                    FROM jobs j JOIN companies c ON j.company_id = c.id
                    WHERE c.name ILIKE $1
                      AND j.status NOT IN ('expired', 'closed')
                    ORDER BY j.score_composite DESC LIMIT 1
                """, f"%{company_q}%")

        if not row:
            # Standard search: title or company
            row = await conn.fetchrow("""
                SELECT j.*, c.name as company_name, c.ats_platform
                FROM jobs j JOIN companies c ON j.company_id = c.id
                WHERE (j.title ILIKE $1 OR c.name ILIKE $1)
                  AND j.status NOT IN ('expired', 'closed')
                ORDER BY j.score_composite DESC LIMIT 1
            """, f"%{query}%")

    if not row:
        return NLResponse(text=f"No job found matching '{query}'.")

    job = dict(row)
    explanation = await _explain_job_scores(job)

    text = (
        f"{job['title']} @ {job['company_name']}\n"
        f"{'=' * 30}\n"
        f"Opp: {job.get('score_opportunity',0)} | Jr: {job.get('score_junior',0)} | "
        f"COL: {job.get('score_colombia',0)} -> {job.get('score_composite',0)}\n"
        f"Confidence: {job.get('confidence', 'medium')}\n\n"
        f"{explanation}\n\n"
        f"{job.get('url', '')}"
    )

    _add_history(chat_id, "model", f"Explained {job['title']}@{job['company_name']}")
    return NLResponse(text=text, jobs=[job])


async def _handle_stats(params: dict, reply: str) -> NLResponse:
    """Get pipeline statistics."""
    days = min(int(params.get("days", 7)), 90)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_conn() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE discovered_at > $1", cutoff)
        by_status = await conn.fetch(
            "SELECT status, COUNT(*) as count FROM jobs WHERE discovered_at > $1 "
            "GROUP BY status ORDER BY count DESC", cutoff)
        by_source = await conn.fetch(
            "SELECT source, COUNT(*) as count FROM jobs WHERE discovered_at > $1 "
            "GROUP BY source ORDER BY count DESC", cutoff)
        avg_composite = await conn.fetchval(
            "SELECT ROUND(AVG(score_composite)) FROM jobs WHERE discovered_at > $1", cutoff)
        hot_count = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE discovered_at > $1 AND score_composite >= 70 "
            "AND status NOT IN ('dismissed','expired','closed')", cutoff)
        hidden_count = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE discovered_at > $1 AND hidden_junior = true "
            "AND status NOT IN ('dismissed','expired','closed')", cutoff)
        dismiss_reasons = await conn.fetch(
            "SELECT reason, COUNT(*) as count FROM job_feedback "
            "WHERE action = 'dismiss' AND created_at > $1 "
            "GROUP BY reason ORDER BY count DESC", cutoff)

    lines = [
        reply, "",
        f"Pipeline Health ({days}d)",
        "=" * 30,
        f"Total discovered: {total}",
        f"Avg composite: {avg_composite or 0}",
        f"Hot leads (>=70): {hot_count}",
        f"Hidden junior: {hidden_count}",
        "", "By Status:",
    ]
    for s in by_status:
        lines.append(f"  {s['status']}: {s['count']}")
    lines.append("\nBy Source:")
    for s in by_source:
        lines.append(f"  {s['source']}: {s['count']}")
    if dismiss_reasons:
        lines.append("\nDismiss Reasons:")
        for s in dismiss_reasons:
            lines.append(f"  {s['reason'] or 'unspecified'}: {s['count']}")

    return NLResponse(text="\n".join(lines))


async def _handle_tweak(params: dict, reply: str) -> NLResponse:
    """Apply a configuration tweak."""
    key = params.get("key", "")
    value = params.get("value")

    if not key or value is None:
        return NLResponse(text="Specify what to change. Example: 'set digest threshold to 40'")

    ranges = {
        'weight_opportunity': (0, 100),
        'weight_junior': (0, 100),
        'weight_colombia': (0, 100),
        'digest_min_composite': (0, 100),
        'digest_max_jobs': (1, 30),
        'job_max_age_days': (7, 90),
    }

    if key not in ranges:
        return NLResponse(text=f"Unknown param: {key}\nValid: {', '.join(ranges.keys())}")

    try:
        value = int(value)
    except (ValueError, TypeError):
        return NLResponse(text=f"Invalid value for {key}: must be an integer.")

    lo, hi = ranges[key]
    if value < lo or value > hi:
        return NLResponse(text=f"{key} must be between {lo} and {hi}.")

    # Enforce weight sum = 100
    if key.startswith('weight_'):
        weight_keys = ['weight_opportunity', 'weight_junior', 'weight_colombia']
        actual = {k: dyn(k) for k in weight_keys}
        proposed = dict(actual)
        proposed[key] = value
        total = sum(proposed.values())
        if total != 100:
            short = {'weight_opportunity': 'Opp', 'weight_junior': 'Jr', 'weight_colombia': 'Col'}
            actual_str = " + ".join(f"{short[k]}={actual[k]}%" for k in weight_keys)
            proposed_str = " + ".join(f"{short[k]}={proposed[k]}%" for k in weight_keys)
            return NLResponse(
                text=f"Can't set {key}={value}: weights would sum to {total}% (must be 100%).\n"
                f"Now: {actual_str} = {sum(actual.values())}%\n"
                f"Proposed: {proposed_str} = {total}%\n"
                f"Adjust another weight first or set all three."
            )

    try:
        await set_dynamic(key, value)
    except Exception as e:
        logger.error("Failed to persist config: %s", e)
        return NLResponse(text=f"Failed to save: {e}")

    return NLResponse(text=reply or f"Done! {key} = {value}.")


# ── Gemini API (cost-optimized) ──────────────────────────────────

async def _call_gemini(system: str, user_text: str, chat_id: int) -> dict | None:
    """Call Gemini Flash for intent classification. Token-optimized."""
    contents = []

    # Few-shot examples (6 compact pairs)
    for user_ex, model_ex in FEW_SHOT:
        contents.append({"role": "user", "parts": [{"text": user_ex}]})
        contents.append({"role": "model", "parts": [{"text": model_ex}]})

    # Conversation history (3 pairs, 200 char cap)
    history = _history.get(chat_id, [])
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["text"]}]})

    contents.append({"role": "user", "parts": [{"text": user_text}]})
    _add_history(chat_id, "user", user_text)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{cfg.ENRICHMENT_MODEL}:generateContent"
    )

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                url,
                params={"key": cfg.GEMINI_API_KEY},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": contents,
                    "generationConfig": {
                        "maxOutputTokens": 400,
                        "temperature": 0.2,
                        "responseMimeType": "application/json",
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                logger.error("Gemini API error: %s", data["error"])
                return None

            candidates = data.get("candidates")
            if not candidates:
                logger.error("Gemini returned no candidates")
                return None

            candidate = candidates[0]
            parts = (candidate.get("content") or {}).get("parts")
            if not parts or not parts[0].get("text"):
                logger.error("Gemini candidate has no text content")
                return None

            finish = candidate.get("finishReason", "")
            text = parts[0]["text"]

            if finish == "MAX_TOKENS":
                logger.warning("Gemini output truncated (MAX_TOKENS)")
                # Try to salvage the truncated JSON
                result = _parse_truncated_json(text)
            else:
                result = _parse_json_response(text)

            if result.get("reply"):
                _add_history(chat_id, "model", result["reply"][:_MAX_HISTORY_CHARS])

            return result

    except Exception as e:
        logger.error("Gemini call failed: %s", e)
        return None


async def _explain_job_scores(job: dict) -> str:
    """Second Gemini call: explain a specific job's scores. Compact prompt."""
    prompt = (
        f"Explain concisely why this job scored as it did. Bullet points, max 100 words.\n"
        f"Job: {job.get('title', '?')} @ {job.get('company_name', '?')}\n"
        f"Opp={job.get('score_opportunity',0)} Jr={job.get('score_junior',0)} "
        f"COL={job.get('score_colombia',0)} Composite={job.get('score_composite',0)}\n"
        f"Tech: {', '.join(job.get('tech_stack', []))}\n"
        f"Remote: {job.get('remote_policy', '?')} | Seniority: {job.get('seniority_signal', '?')}\n"
        f"YoE: {job.get('yoe_min', '?')}-{job.get('yoe_max', '?')} | "
        f"Contractor: {job.get('contractor_ok', False)}\n"
        f"Desc: {(job.get('description_snippet', '') or '')[:400]}"
    )

    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{cfg.ENRICHMENT_MODEL}:generateContent"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                params={"key": cfg.GEMINI_API_KEY},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 250, "temperature": 0.1},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates")
            if not candidates:
                return _fallback_explanation(job)
            parts = (candidates[0].get("content") or {}).get("parts")
            if not parts or not parts[0].get("text"):
                return _fallback_explanation(job)
            return parts[0]["text"].strip()
    except Exception as e:
        logger.warning("Gemini explain failed: %s", e)
        return _fallback_explanation(job)


def _fallback_explanation(job: dict) -> str:
    """Rules-based fallback when Gemini is unavailable."""
    lines = []
    opp = job.get('score_opportunity', 0)
    jr = job.get('score_junior', 0)
    col = job.get('score_colombia', 0)

    if opp >= 60:
        lines.append(f"- Opp {opp}: Good AI/ML tech match")
    else:
        lines.append(f"- Opp {opp}: Limited tech overlap")
    if jr >= 60:
        lines.append(f"- Jr {jr}: Accessible, low YoE")
    else:
        lines.append(f"- Jr {jr}: Senior-leaning")
    if col >= 60:
        lines.append(f"- COL {col}: Remote-friendly")
    elif col == 0:
        lines.append(f"- COL {col}: Geo-blocked")
    else:
        lines.append(f"- COL {col}: Uncertain remote policy")

    return "\n".join(lines)


# ── JSON Parsing (robust, never leaks raw JSON) ─────────────────

def _parse_json_response(text: str) -> dict:
    """Parse JSON from Gemini response. Never returns raw JSON as reply."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract JSON object from surrounding text
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Fallback: clean the text so user never sees raw JSON
    clean = _clean_for_display(text)
    logger.warning("Could not parse Gemini JSON, cleaned for display")
    return {"intent": "chat", "params": {}, "reply": clean}


def _parse_truncated_json(text: str) -> dict:
    """Handle MAX_TOKENS truncated JSON. Extract what we can."""
    # Try adding closing braces
    for suffix in ['"}', '"}}', '}']:
        try:
            return json.loads(text + suffix)
        except json.JSONDecodeError:
            continue

    # Try to extract at least the intent
    intent_match = '"intent"' in text
    if intent_match:
        for intent in ("search", "explain", "stats", "tweak", "system", "chat"):
            if f'"{intent}"' in text:
                logger.info("Salvaged truncated intent: %s", intent)
                # Extract params if possible
                params = {}
                if '"days"' in text:
                    import re
                    m = re.search(r'"days"\s*:\s*(\d+)', text)
                    if m:
                        params["days"] = int(m.group(1))
                if '"query"' in text:
                    import re
                    m = re.search(r'"query"\s*:\s*"([^"]*)"?', text)
                    if m:
                        params["query"] = m.group(1)
                if '"filter"' in text:
                    import re
                    m = re.search(r'"filter"\s*:\s*"([^"]*)"?', text)
                    if m:
                        params["filter"] = m.group(1)
                if '"key"' in text:
                    import re
                    m = re.search(r'"key"\s*:\s*"([^"]*)"?', text)
                    if m:
                        params["key"] = m.group(1)
                if '"value"' in text:
                    import re
                    m = re.search(r'"value"\s*:\s*(\d+)', text)
                    if m:
                        params["value"] = int(m.group(1))
                return {"intent": intent, "params": params, "reply": ""}

    logger.warning("Could not salvage truncated JSON")
    return {"intent": "chat", "params": {}, "reply": "Let me try that again. Could you rephrase?"}


def _clean_for_display(text: str) -> str:
    """Clean text that might contain JSON fragments so it's user-friendly."""
    # If it looks like JSON, don't show it
    stripped = text.strip()
    if stripped.startswith('{') or stripped.startswith('['):
        return "I understood your request but had a formatting issue. Please try again."
    return stripped[:800]


# ── System Instruction Builder ───────────────────────────────────

def _build_system_instruction() -> str:
    """Build system instruction with current dynamic config."""
    w_opp = dyn('weight_opportunity')
    w_jr = dyn('weight_junior')
    w_col = dyn('weight_colombia')

    config_block = (
        f"Weights: Opp {w_opp}% + Jr {w_jr}% + Col {w_col}%\n"
        f"Digest: min={dyn('digest_min_composite')}, max={dyn('digest_max_jobs')} jobs\n"
        f"Job max age: {dyn('job_max_age_days')}d"
    )

    return SYSTEM_INSTRUCTION.format(
        w_opp=w_opp, w_jr=w_jr, w_col=w_col,
        w_opp_dec=round(w_opp / 100, 2),
        w_jr_dec=round(w_jr / 100, 2),
        w_col_dec=round(w_col / 100, 2),
        config_block=config_block,
    )


# ── History Management ───────────────────────────────────────────

def _add_history(chat_id: int, role: str, text: str):
    """Add to conversation history (tight caps to control token cost)."""
    if chat_id not in _history:
        _history[chat_id] = []

    _history[chat_id].append({"role": role, "text": text[:_MAX_HISTORY_CHARS]})

    max_msgs = _MAX_HISTORY_PAIRS * 2
    if len(_history[chat_id]) > max_msgs:
        _history[chat_id] = _history[chat_id][-max_msgs:]
