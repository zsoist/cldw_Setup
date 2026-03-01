"""Natural language conversation engine — Gemini Flash intent routing.

Deep COT-optimized NL engine v2 (2026-03-01):
- Pre-Gemini fast-path: greetings, thanks, help, ack → zero LLM cost
- 24 few-shot examples: typos, multilingual, multi-turn refs, edge cases
- responseSchema enforcement: Gemini returns guaranteed-valid JSON structure
- Temperature 0.0: deterministic classification (no creativity needed)
- Regex fallback classifier: handles Gemini failures gracefully
- History: 5 pairs, 300 chars each (better multi-turn context)
- Confirmation gate: destructive NL actions require explicit confirm
- Robust JSON parser: no repeated imports, handles truncation
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
_MAX_HISTORY_PAIRS = 5
_MAX_HISTORY_CHARS = 300

# Pending confirmations for destructive actions
_pending_confirm: dict[int, dict] = {}


@dataclass
class NLResponse:
    text: str
    jobs: list[dict] = field(default_factory=list)


# ── Pre-Gemini Fast Paths (zero LLM cost) ────────────────────────

_GREETING_RE = re.compile(
    r'^(h[eai]y?|hi+|hello|hola|buenas?|buenos?\s*d[ií]as?|que\s*tal|'
    r'sup|yo|what\'?s?\s*up|howdy|hallo|oi|hey\s*there|good\s*(morning|evening|afternoon))[\s!?.]*$',
    re.IGNORECASE
)

_THANKS_RE = re.compile(
    r'^(thanks?|thank\s*you|thx|ty|gracias|muchas\s*gracias|'
    r'great|awesome|perfect|cool|nice|ok[ay]*|got\s*it|understood|'
    r'cheers|ta|merci|danke|arigato)[\s!?.]*$',
    re.IGNORECASE
)

_HELP_RE = re.compile(
    r'^(help|ayuda|commands?|que\s*puedo\s*hacer|what\s*can\s*you\s*do|'
    r'how\s*does?\s*(this|it)\s*work|features?|options?|menu|'
    r'what\s*are\s*(the|your)\s*commands?)[\s?!.]*$',
    re.IGNORECASE
)

_IDENTITY_RE = re.compile(
    r'^(who\s*are\s*you|what\s*are\s*you|que\s*eres|qui[ée]n\s*eres)[\s?!.]*$',
    re.IGNORECASE
)


def _check_fast_path(text: str) -> NLResponse | None:
    """Check if message matches a fast-path pattern. Returns None if no match."""
    stripped = text.strip()

    if _GREETING_RE.match(stripped):
        return NLResponse(
            text="👋 Hey! I'm your job search assistant. "
                 "Ask me anything — search for jobs, check scores, tweak settings, or just chat.\n"
                 "Try: \"show me ML jobs\" or \"how's the pipeline?\""
        )

    if _THANKS_RE.match(stripped):
        return NLResponse(text="👍 Anytime! Let me know if you need anything else.")

    if _HELP_RE.match(stripped):
        return NLResponse(
            text="🔍 Here's what I can do:\n\n"
                 "💬 Natural language:\n"
                 "  • \"show me ML jobs\" — search by keyword\n"
                 "  • \"best jobs\" / \"hot leads\" — top-scoring\n"
                 "  • \"why did X score low?\" — explain scores\n"
                 "  • \"how many jobs this week?\" — pipeline stats\n"
                 "  • \"set opportunity weight to 40\" — tweak config\n"
                 "  • \"how does scoring work?\" — system info\n"
                 "  • \"dismiss all\" / \"pause cron\" — management\n\n"
                 "⌨️ Commands: /jobs /search /saved /applied /stats /health /sync /cron /pause /resume /dismiss_all /help"
        )

    if _IDENTITY_RE.match(stripped):
        return NLResponse(
            text="🤖 I'm Job Radar — your AI job search assistant.\n"
                 "I scout remote AI/ML roles, score them for fit, and surface the best leads.\n"
                 "Ask me anything or use /help for commands."
        )

    return None


# ── Regex Fallback Classifier (when Gemini fails) ─────────────────

_SEARCH_PATTERNS = re.compile(
    r'((?:show|find|search|buscar|look\s*for|get|list)\s+(?!cron|scheduler|sched)(?:\w)|'
    r'jobs?\s*(for|about|with|in)\b|'
    r'roles?\s*(for|about|with|in)\b|'
    r'(?:ml|ai|python|pytorch|rag|llm|nlp|data|remote)\s*(?:jobs?|roles?|positions?))',
    re.IGNORECASE
)

_HOT_PATTERNS = re.compile(
    r'(best|top|hot|highest|mejores|buenos|good)\s*(jobs?|leads?|roles?|ones?)?',
    re.IGNORECASE
)

_HIDDEN_PATTERNS = re.compile(
    r'(hidden|junior|entry|beginner|sin\s*experiencia)',
    re.IGNORECASE
)

_EXPLAIN_PATTERNS = re.compile(
    r'(why\s*(did|does|is|was)|explain|score\s*(so|low|high|break)|'
    r'como|por\s*qu[ée]|what\s*about|tell\s*me\s*about|details?\s*(on|for|about))',
    re.IGNORECASE
)

_STATS_PATTERNS = re.compile(
    r'(stats?|statistics?|pipeline\s*health|how\s*many\s*(jobs?|roles?|leads?)|'
    r'count\s*(of\s*)?(jobs?|roles?)|summary|report|overview|dashboard|'
    r'estad[ií]sticas?|cuant[oa]s?\s*(jobs?|trabajos?))',
    re.IGNORECASE
)

_TWEAK_PATTERNS = re.compile(
    r'(set|change|adjust|tweak|modify|update|increase|decrease|lower|raise|'
    r'weight|threshold|cambiar|ajustar)\s.*(weight|threshold|composite|digest|age|opportunity|junior|colombia)',
    re.IGNORECASE
)

_MANAGE_PATTERNS = re.compile(
    r'(dismiss\s*all|cancel\s*all|clear\s*(all|jobs)|start\s*fresh|clean|'
    r'pause|stop\s*(cron|sync|scheduler)|resume|unpause|'
    r'cron\s*(status|jobs?)|scheduled?\s*(jobs?|tasks?)|show\s*cron)',
    re.IGNORECASE
)

_SYSTEM_PATTERNS = re.compile(
    r'(how\s*does?|what\s*is|explain\s*(the|how)|tell\s*me\s*about)\s*'
    r'(scor|dedup|connect|source|watchlist|digest|pipeline|system|enrichment|sync)',
    re.IGNORECASE
)

_SAVED_PATTERNS = re.compile(
    r'(saved|guardados?|bookmarked?|my\s*saved|show\s*saved)',
    re.IGNORECASE
)

_APPLIED_PATTERNS = re.compile(
    r'(appl(ied|ication|y\s*to)|my\s*applications?|'
    r'(what|where)\s*(did|have)\s*i\s*appl|'
    r'(did|have)\s*i\s*appl|aplicaciones)',
    re.IGNORECASE
)

_RECENT_PATTERNS = re.compile(
    r'(new|recent|latest|newest|fresh|today|yesterday|last\s*\d+|'
    r'nuevos?|recientes?|[uú]ltimos?)\s*(jobs?|roles?|leads?)?',
    re.IGNORECASE
)


def _regex_classify(text: str) -> dict | None:
    """Fallback classifier using regex patterns. Returns intent dict or None."""
    stripped = text.strip()

    # Manage intent (check first — "cancel all" is unambiguous)
    if _MANAGE_PATTERNS.search(stripped):
        action = "cron_status"
        lower = stripped.lower()
        if any(w in lower for w in ("dismiss", "cancel all", "clear", "start fresh", "clean")):
            action = "dismiss_all"
        elif any(w in lower for w in ("pause", "stop cron", "stop sync", "stop scheduler")):
            action = "pause"
        elif any(w in lower for w in ("resume", "unpause", "start cron", "start sync")):
            action = "resume"
        return {"intent": "manage", "params": {"action": action}, "reply": ""}

    # Tweak intent
    if _TWEAK_PATTERNS.search(stripped):
        return {"intent": "tweak", "params": {}, "reply": "What would you like to change?"}

    # Stats intent
    if _STATS_PATTERNS.search(stripped) and not _SEARCH_PATTERNS.search(stripped):
        days = 7
        m = re.search(r'(\d+)\s*d', stripped)
        if m:
            days = min(int(m.group(1)), 90)
        return {"intent": "stats", "params": {"days": days}, "reply": f"Pipeline health ({days}d):"}

    # Explain intent
    if _EXPLAIN_PATTERNS.search(stripped):
        # Extract the subject (company/title name)
        query = re.sub(
            r'(why|explain|score|how|como|por\s*qu[ée]|what\s*about|tell\s*me\s*about|'
            r'details?\s*(on|for|about)|did|does|is|the|that|this|so|low|high|have|got|it|one|rated|poorly)',
            '', stripped, flags=re.IGNORECASE
        ).strip(' ?!.,')
        if query:
            return {"intent": "explain", "params": {"query": query}, "reply": f"Checking scores for {query}."}
        else:
            # Multi-turn reference — "why did that score low" (no explicit subject)
            return {"intent": "explain", "params": {"query": "last result"}, "reply": "Looking at those scores:"}

    # Saved / applied shortcuts
    if _SAVED_PATTERNS.search(stripped):
        return {"intent": "search", "params": {"filter": "saved", "limit": 10}, "reply": "Your saved jobs:"}
    if _APPLIED_PATTERNS.search(stripped):
        return {"intent": "search", "params": {"filter": "applied", "limit": 10}, "reply": "Application pipeline:"}

    # Recent/new jobs
    if _RECENT_PATTERNS.search(stripped):
        return {"intent": "search", "params": {"filter": "all", "limit": 10}, "reply": "Most recent jobs:"}

    # Hot leads
    if _HOT_PATTERNS.search(stripped):
        return {"intent": "search", "params": {"filter": "hot", "limit": 5}, "reply": "Top-scoring leads:"}

    # Hidden junior
    if _HIDDEN_PATTERNS.search(stripped) and not _EXPLAIN_PATTERNS.search(stripped):
        return {"intent": "search", "params": {"filter": "hidden", "limit": 10}, "reply": "Hidden junior opportunities:"}

    # System info
    if _SYSTEM_PATTERNS.search(stripped):
        topic = "scoring"
        lower = stripped.lower()
        if "dedup" in lower:
            topic = "dedup"
        elif any(w in lower for w in ("connect", "source")):
            topic = "connectors"
        elif "watchlist" in lower:
            topic = "watchlist"
        elif "digest" in lower:
            topic = "digest"
        return {"intent": "system", "params": {"topic": topic}, "reply": ""}

    # General search (broadest — check last)
    if _SEARCH_PATTERNS.search(stripped):
        # Extract meaningful search terms
        query = re.sub(
            r'(show|find|search|buscar|look\s*for|any|get|list|me|for|please|por\s*favor)',
            '', stripped, flags=re.IGNORECASE
        ).strip(' ?!.,')
        return {
            "intent": "search",
            "params": {"query": query, "limit": 10},
            "reply": f"Searching for {query}:" if query else "Here are the top jobs:"
        }

    return None


# ── System Instruction (expanded intent coverage) ─────────────────

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
Sync 2x/day (05:00, 17:00 UTC) | AM digest 08:00 COT | PM 18:00 COT

# Tweakable (via "tweak" intent)
weight_opportunity/junior/colombia: 0-100 (must sum 100)
digest_min_composite: 0-100 | digest_max_jobs: 1-30 | job_max_age_days: 7-90

# Response: ALWAYS valid JSON matching the schema
Params by intent:
- search: {{"query":"text","filter":"hot|hidden|saved|applied|all","limit":5}}
- explain: {{"query":"company or title"}}
- stats: {{"days":7}}
- tweak: {{"key":"param_name","value":number}}
- system: {{"topic":"scoring|dedup|connectors|watchlist|digest"}}
- manage: {{"action":"dismiss_all|pause|resume|cron_status"}}
- chat: {{}}

CRITICAL RULES:
1. For search/stats/explain: keep "reply" to ONE short intro sentence. The system appends real data.
2. For system/chat: put full answer in "reply" (max 3 short paragraphs).
3. For tweak: confirm change in "reply".
4. For manage: map user intent to action:
   "cancel all"/"dismiss all"/"clear jobs"/"start fresh" → dismiss_all
   "pause cron"/"stop syncs"/"cancel cron"/"pause scheduler" → pause
   "resume cron"/"start syncs"/"resume" → resume
   "cron status"/"show cron"/"scheduled jobs" → cron_status
5. Handle typos generously: "pythn" → python, "machne lerning" → machine learning
6. Multi-turn references: "that one" / "the first one" / "save it" / "more" / "explain it" → use context from history
7. Match user's language (Spanish ↔ English). Never fabricate data. Be concise.
"""

# ── Few-Shot (24 examples: search, explain, stats, tweak, system, manage, chat) ──

FEW_SHOT = [
    # --- Search intent ---
    ("show me the best jobs",
     '{"intent":"search","params":{"filter":"hot","limit":5},"reply":"Top-scoring active jobs:"}'),

    ("buscar trabajos de ML",
     '{"intent":"search","params":{"query":"ml","limit":10},"reply":"Buscando roles de ML:"}'),

    ("any pytorch roles?",
     '{"intent":"search","params":{"query":"pytorch","limit":10},"reply":"PyTorch roles:"}'),

    ("python machine lerning jobs",  # typo: lerning
     '{"intent":"search","params":{"query":"python machine learning","limit":10},"reply":"Python/ML jobs:"}'),

    ("trabajos remotos para colombia",
     '{"intent":"search","params":{"filter":"all","limit":10},"reply":"Trabajos remotos accesibles desde Colombia:"}'),

    ("show more",
     '{"intent":"search","params":{"filter":"all","limit":15},"reply":"More jobs:"}'),

    ("hidden opportunities",
     '{"intent":"search","params":{"filter":"hidden","limit":10},"reply":"Hidden junior opportunities:"}'),

    ("my saved jobs",
     '{"intent":"search","params":{"filter":"saved","limit":10},"reply":"Your saved jobs:"}'),

    ("what did I apply to?",
     '{"intent":"search","params":{"filter":"applied","limit":10},"reply":"Your applications:"}'),

    ("new jobs today",
     '{"intent":"search","params":{"filter":"all","limit":10},"reply":"Latest jobs:"}'),

    # --- Explain intent ---
    ("why did that Anthropic job score so low?",
     '{"intent":"explain","params":{"query":"Anthropic"},"reply":"Checking the Anthropic job scores."}'),

    ("tell me about the first one",
     '{"intent":"explain","params":{"query":"first result"},"reply":"Looking at that job:"}'),

    ("explain the cohere position",
     '{"intent":"explain","params":{"query":"cohere"},"reply":"Score breakdown for Cohere:"}'),

    # --- Stats intent ---
    ("how many jobs this week?",
     '{"intent":"stats","params":{"days":7},"reply":"Pipeline health (7d):"}'),

    ("full status report",
     '{"intent":"stats","params":{"days":7},"reply":"Full pipeline status:"}'),

    ("estadísticas del último mes",
     '{"intent":"stats","params":{"days":30},"reply":"Estadísticas (30d):"}'),

    # --- Tweak intent ---
    ("give more weight to opportunity, set it to 40",
     '{"intent":"tweak","params":{"key":"weight_opportunity","value":40},"reply":"Opportunity weight set to 40%. Adjust junior/Colombia so weights sum to 100."}'),

    ("lower the digest threshold to 30",
     '{"intent":"tweak","params":{"key":"digest_min_composite","value":30},"reply":"Digest threshold set to 30."}'),

    # --- System intent ---
    ("how does scoring work?",
     '{"intent":"system","params":{"topic":"scoring"},"reply":"Deterministic engine, zero LLM cost. Three dimensions: Opportunity (AI/ML tech matches, funded signals), Junior (YoE, seniority, requirement count), Colombia (remote policy, timezone, contractor OK). Composite = weighted average. 70+ = hot lead."}'),

    ("what sources do you use?",
     '{"intent":"system","params":{"topic":"connectors"},"reply":"6 connectors: Brave Search, HN Who\'s Hiring, RemoteOK, WeWorkRemotely, Jobicy, and a watchlist of 27 AI startups. Sync runs 2x/day."}'),

    # --- Manage intent ---
    ("cancel all",
     '{"intent":"manage","params":{"action":"dismiss_all"},"reply":"Dismissing all active jobs."}'),

    ("pause the cron jobs",
     '{"intent":"manage","params":{"action":"pause"},"reply":"Pausing all scheduled jobs."}'),

    ("resume syncs",
     '{"intent":"manage","params":{"action":"resume"},"reply":"Resuming all scheduled jobs."}'),

    # --- Chat intent ---
    ("you're doing great",
     '{"intent":"chat","params":{},"reply":"Thanks! Let me know if you need anything else. 🚀"}'),
]

# ── Gemini Response Schema (enforced at API level) ────────────────

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {
            "type": "STRING",
            "enum": ["search", "explain", "stats", "tweak", "system", "manage", "chat"],
        },
        "params": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING"},
                "filter": {"type": "STRING"},
                "limit": {"type": "INTEGER"},
                "days": {"type": "INTEGER"},
                "key": {"type": "STRING"},
                "value": {"type": "INTEGER"},
                "topic": {"type": "STRING"},
                "action": {"type": "STRING"},
            },
        },
        "reply": {"type": "STRING"},
    },
    "required": ["intent", "params", "reply"],
}


async def process_message(text: str, chat_id: int) -> NLResponse:
    """Process a plain-text message and return a structured response."""

    # 1. Fast-path: greetings, thanks, help, identity (zero LLM cost)
    fast = _check_fast_path(text)
    if fast:
        _add_history(chat_id, "user", text)
        _add_history(chat_id, "model", fast.text[:80])
        return fast

    # 2. Check for pending confirmation (destructive action safety gate)
    confirm_result = await _check_pending_confirm(text, chat_id)
    if confirm_result is not None:
        return confirm_result

    if not cfg.GEMINI_API_KEY:
        # 3. No Gemini key: try regex fallback
        fallback = _regex_classify(text)
        if fallback:
            return await _route_intent(fallback, chat_id, text)
        return NLResponse(text="Gemini API key not configured. Use /help for commands.")

    try:
        system = _build_system_instruction()
        result = await _call_gemini(system, text, chat_id)

        if not result:
            # Gemini failed — try regex fallback
            fallback = _regex_classify(text)
            if fallback:
                logger.info("Gemini failed, regex fallback classified as: %s", fallback.get("intent"))
                return await _route_intent(fallback, chat_id, text)

            # Both failed — clean up history
            if chat_id in _history and _history[chat_id]:
                _history[chat_id] = [m for m in _history[chat_id] if m["text"] != text[:_MAX_HISTORY_CHARS]]
            return NLResponse(text="I couldn't process that. Try rephrasing, or use /help.")

        return await _route_intent(result, chat_id, text)

    except Exception as e:
        logger.error("Conversation error: %s", e, exc_info=True)
        # Last resort: regex fallback
        fallback = _regex_classify(text)
        if fallback:
            try:
                return await _route_intent(fallback, chat_id, text)
            except Exception:
                pass
        return NLResponse(text="Something went wrong. Try /help for commands.")


async def _route_intent(result: dict, chat_id: int, user_text: str) -> NLResponse:
    """Route a classified intent to the appropriate handler."""
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
    elif intent == "manage":
        resp = await _handle_manage(params, reply, chat_id)
        _add_history(chat_id, "model", resp.text[:80])
        return resp
    else:
        _add_history(chat_id, "model", reply)
        return NLResponse(text=reply or "I'm not sure what you mean. Try /help for available commands.")


# ── Confirmation Gate (destructive actions) ───────────────────────

async def _check_pending_confirm(text: str, chat_id: int) -> NLResponse | None:
    """Check if user is responding to a pending confirmation prompt."""
    if chat_id not in _pending_confirm:
        return None

    pending = _pending_confirm[chat_id]
    stripped = text.strip().lower()

    # Check for explicit yes/confirm
    if stripped in ("yes", "y", "confirm", "sí", "si", "dale", "ok", "do it", "proceed", "go ahead"):
        del _pending_confirm[chat_id]
        action = pending.get("action")
        _add_history(chat_id, "user", text)

        if action == "dismiss_all":
            async with get_conn() as conn:
                result = await conn.execute(
                    "UPDATE jobs SET status = 'dismissed' "
                    "WHERE status NOT IN ('dismissed', 'expired', 'closed')"
                )
            dismissed = int(result.split()[-1])
            logger.info("NL bulk-dismissed %d jobs (confirmed)", dismissed)
            resp = NLResponse(
                text=f"✅ Dismissed {dismissed} jobs. Pipeline is clean.\nUse /sync to fetch fresh leads."
            )
            _add_history(chat_id, "model", resp.text[:80])
            return resp

        return NLResponse(text="Action completed.")

    elif stripped in ("no", "n", "cancel", "cancelar", "nah", "nope", "never mind", "abort"):
        del _pending_confirm[chat_id]
        _add_history(chat_id, "user", text)
        _add_history(chat_id, "model", "Cancelled.")
        return NLResponse(text="👍 Cancelled. Nothing was changed.")

    # If there's a pending confirm but user said something else, clear it and process normally
    del _pending_confirm[chat_id]
    return None


# ── Search Term Extraction ────────────────────────────────────────

# Multi-word tech terms to keep as phrases (not split into words)
_MULTI_WORD_TECH = [
    'machine learning', 'deep learning', 'computer vision', 'reinforcement learning',
    'vector database', 'distributed training', 'model serving', 'vertex ai', 'azure ml',
    'github actions', 'fine tuning', 'fine-tuning', 'data science', 'data scientist',
    'data engineering', 'scikit-learn', 'natural language', 'large language',
    'prompt engineering', 'generative ai', 'gen ai',
]

_SEARCH_NOISE = {
    'jobs', 'job', 'roles', 'role', 'positions', 'position', 'for', 'the', 'a', 'an',
    'remote', 'trabajo', 'trabajos', 'de', 'para', 'en', 'openings', 'opportunities',
    'with', 'and', 'or', 'in', 'at', 'buscar', 'search', 'find', 'show', 'me',
    'any', 'some', 'get', 'list', 'please', 'por', 'favor',
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


# ── Intent Handlers ───────────────────────────────────────────────

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

    # Handle multi-turn references like "first result", "that one", "the second"
    if query.lower() in ("first result", "that one", "it", "the first", "the last", "that"):
        # Try to get from recent history
        history = _history.get(chat_id, [])
        for msg in reversed(history):
            if msg["role"] == "model" and "Showed:" in msg["text"]:
                # Extract first job reference from history
                shown = msg["text"].replace("Showed: ", "")
                first_job = shown.split(",")[0].strip()
                if "@" in first_job:
                    query = first_job.split("(")[0].strip()  # Remove score suffix
                    break

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


async def _handle_manage(params: dict, reply: str, chat_id: int) -> NLResponse:
    """Handle management actions: dismiss_all, pause, resume, cron_status."""
    from app.scheduler import pause_scheduler, resume_scheduler, get_scheduler_status

    action = params.get("action", "")

    if action == "dismiss_all":
        # Confirmation gate for destructive action
        async with get_conn() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM jobs WHERE status NOT IN ('dismissed', 'expired', 'closed')"
            )
        if count == 0:
            return NLResponse(text="No active jobs to dismiss. Pipeline is already clean.")

        # Store pending confirmation
        _pending_confirm[chat_id] = {"action": "dismiss_all", "count": count}
        return NLResponse(
            text=f"⚠️ This will dismiss **{count}** active jobs. This cannot be undone.\n\n"
                 f"Reply **yes** to confirm or **no** to cancel."
        )

    elif action == "pause":
        msg = pause_scheduler()
        return NLResponse(text=msg)

    elif action == "resume":
        msg = resume_scheduler()
        return NLResponse(text=msg)

    elif action == "cron_status":
        msg = get_scheduler_status()
        return NLResponse(text=msg)

    else:
        return NLResponse(
            text="Available actions: dismiss all jobs, pause cron, resume cron, show cron status.\n"
                 "Or use /dismiss_all, /pause, /resume, /cron."
        )


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


# ── Gemini API (cost-optimized) ───────────────────────────────────

async def _call_gemini(system: str, user_text: str, chat_id: int) -> dict | None:
    """Call Gemini Flash for intent classification. Token-optimized."""
    contents = []

    # Few-shot examples
    for user_ex, model_ex in FEW_SHOT:
        contents.append({"role": "user", "parts": [{"text": user_ex}]})
        contents.append({"role": "model", "parts": [{"text": model_ex}]})

    # Conversation history (5 pairs, 300 char cap)
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
                        "temperature": 0.0,
                        "responseMimeType": "application/json",
                        "responseSchema": RESPONSE_SCHEMA,
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


# ── JSON Parsing (robust, never leaks raw JSON) ──────────────────

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

    # Try to extract at least the intent and params via regex
    if '"intent"' in text:
        for intent in ("search", "explain", "stats", "tweak", "system", "manage", "chat"):
            if f'"{intent}"' in text:
                logger.info("Salvaged truncated intent: %s", intent)
                params = {}

                # Extract all known params in one pass
                param_patterns = {
                    "days": r'"days"\s*:\s*(\d+)',
                    "query": r'"query"\s*:\s*"([^"]*)"?',
                    "filter": r'"filter"\s*:\s*"([^"]*)"?',
                    "key": r'"key"\s*:\s*"([^"]*)"?',
                    "action": r'"action"\s*:\s*"([^"]*)"?',
                    "topic": r'"topic"\s*:\s*"([^"]*)"?',
                }
                for param_name, pattern in param_patterns.items():
                    m = re.search(pattern, text)
                    if m:
                        params[param_name] = m.group(1)

                # Integer params
                value_m = re.search(r'"value"\s*:\s*(\d+)', text)
                if value_m:
                    params["value"] = int(value_m.group(1))
                limit_m = re.search(r'"limit"\s*:\s*(\d+)', text)
                if limit_m:
                    params["limit"] = int(limit_m.group(1))
                if "days" in params:
                    params["days"] = int(params["days"])

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


# ── System Instruction Builder ────────────────────────────────────

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


# ── History Management ────────────────────────────────────────────

def _add_history(chat_id: int, role: str, text: str):
    """Add to conversation history (tight caps to control token cost)."""
    if chat_id not in _history:
        _history[chat_id] = []

    _history[chat_id].append({"role": role, "text": text[:_MAX_HISTORY_CHARS]})

    max_msgs = _MAX_HISTORY_PAIRS * 2
    if len(_history[chat_id]) > max_msgs:
        _history[chat_id] = _history[chat_id][-max_msgs:]
