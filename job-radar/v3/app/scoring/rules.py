"""Deterministic scoring engine. Zero LLM cost. Pure Python. <5ms per job."""
import re
from dataclasses import dataclass
from typing import Optional

# Pre-compiled word-boundary patterns for tech stack matching (avoids substring false positives)
_TECH_PATTERNS: dict[str, re.Pattern] = {}


def _tech_match(term: str, text_lower: str) -> bool:
    """Word-boundary-aware tech stack matching. Avoids 'go' in 'good', 'rag' in 'pragmatic'."""
    if term not in _TECH_PATTERNS:
        _TECH_PATTERNS[term] = re.compile(r'\b' + re.escape(term) + r'\b')
    return bool(_TECH_PATTERNS[term].search(text_lower))


@dataclass
class ScoreResult:
    opportunity: int
    junior: int
    colombia: int
    composite: int
    confidence: str
    hidden_junior: bool
    method: str
    tech_stack: list[str]
    seniority_signal: str
    yoe_min: Optional[int]
    yoe_max: Optional[int]
    salary_min: Optional[int]
    salary_max: Optional[int]
    remote_policy: str
    timezone_signal: str
    contractor_ok: bool


# ── Signal Sets ──────────────────────────────────────────────

AI_ML_STACK = {
    'python', 'pytorch', 'tensorflow', 'keras', 'jax', 'scikit-learn',
    'huggingface', 'transformers', 'langchain', 'llamaindex', 'openai',
    'mlflow', 'wandb', 'mlops', 'kubeflow', 'airflow', 'dbt', 'spark',
    'pandas', 'numpy', 'scipy', 'opencv', 'llm', 'nlp', 'computer vision',
    'deep learning', 'machine learning', 'reinforcement learning', 'rag',
    'fine-tuning', 'embeddings', 'vector database', 'pinecone', 'weaviate',
    'qdrant', 'chromadb', 'cuda', 'gpu', 'distributed training',
    'model serving', 'sagemaker', 'vertex ai', 'bedrock', 'azure ml',
}

ADJACENT_STACK = {
    'sql', 'postgres', 'docker', 'kubernetes', 'aws', 'gcp', 'azure',
    'fastapi', 'flask', 'django', 'node', 'typescript', 'go', 'rust',
    'redis', 'kafka', 'rabbitmq', 'terraform', 'ci/cd', 'github actions',
}

# ── Regex Patterns ───────────────────────────────────────────

SENIOR_SIGNALS = re.compile(
    r'\b(senior|sr\.?|staff|principal|lead|architect|director|head of|vp of|'
    r'manager|10\+|8\+|7\+|6\+)\b', re.IGNORECASE
)
JUNIOR_SIGNALS = re.compile(
    r'\b(junior|jr\.?|entry[- ]level|'
    r'associate(?!\s+(?:director|vice|partner|principal|general))|'
    r'intern|new grad|recent graduate|'
    r'early career|0-[12]|1-[23]|bootcamp|self-taught welcome)\b', re.IGNORECASE
)
MID_YOE = re.compile(r'\b([3-5])\+?\s*(?:years?|yrs?|YoE)\b', re.IGNORECASE)
HIGH_YOE = re.compile(r'\b([6-9]|[1-9]\d)\+?\s*(?:years?|yrs?|YoE)\b', re.IGNORECASE)
LOW_YOE = re.compile(r'\b([0-2])\+?\s*(?:years?|yrs?|YoE)\b', re.IGNORECASE)

REMOTE_WORLDWIDE = re.compile(
    r'\b(worldwide|anywhere|global|fully remote|100% remote|remote.first|'
    r'global\s+team|distributed\s+team|location[- ]agnostic|work\s+from\s+anywhere)\b', re.IGNORECASE
)
REMOTE_AMERICAS = re.compile(
    r'\b(americas|latam|latin america|south america|western hemisphere|'
    r'north america|us/canada|et\.?-\.?pt|eastern\.?-\.?pacific|'
    r'GMT-[345]|UTC-[345]|CT/ET|PT/ET|US\s+time\s?zones?)\b', re.IGNORECASE
)
REMOTE_COLOMBIA = re.compile(
    r'\b(colombia|bogot[aá]|medell[ií]n|cali|barranquilla|COL)\b', re.IGNORECASE
)
GEO_BLOCK = re.compile(
    r'\b(us only|usa only|u\.s\. only|us citizens|us[- ]based only|'
    r'based in (?:the )?(?:us|usa|u\.s\.|united states)|'
    r'eu only|uk only|must be located in (?:the )?(?:us|uk|eu|canada|australia)|'
    r'security clearance|us work authorization|right to work in (?:the )?(?:us|uk)|'
    r'authorized to work in the (?:us|united states)|'
    r'W-2 only|w2 only|'
    r'must reside in (?:the )?(?:us|usa|u\.s\.|united states|uk|eu|canada|australia))\b',
    re.IGNORECASE
)
GEO_BLOCK_TITLE = re.compile(
    r'(?:remote\s*\((?:us|usa|u\.s\.|ny|nyc|sf|la)\)|'
    r'\b(?:new york|san francisco|seattle|austin|boston|chicago|los angeles|'
    r'washington dc|denver|atlanta|portland|miami)\s*(?:/\s*remote|,\s*(?:us|usa))\b)',
    re.IGNORECASE
)
HYBRID_SIGNALS = re.compile(
    r'\b(hybrid|on.?site|in.?office|office.?based|in.?person|'
    r'days?.?(?:in|at).?(?:the)?.?office|return to office|RTO)\b', re.IGNORECASE
)
TIMEZONE_FLEXIBLE = re.compile(
    r'\b(flexible hours|async|asynchronous|any timezone|no timezone)\b', re.IGNORECASE
)
CONTRACTOR_OK = re.compile(
    r'\b(contractor|freelance|contract[- ]to[- ]hire|1099|B2B\s+contract|EOR|'
    r'deel|remote\.com|oyster|papaya global|letsdeel|'
    r'nearshore|latam\s+talent|talent\s+partner)\b', re.IGNORECASE
)
SALARY_PATTERN = re.compile(
    r'\$\s*([\d,]+)\s*(?:k|K)?\s*(?:-|to|–)\s*\$?\s*([\d,]+)\s*(?:k|K)?'
)
COMP_COMPETITIVE = re.compile(r'\bcompetitive\s+(?:salary|compensation|pay)\b', re.IGNORECASE)
FUNDED_SIGNALS = re.compile(
    r'\b(series [A-F]|raised \$|funded|YC\b|Y Combinator|backed by|unicorn|'
    r'IPO|publicly traded|Fortune \d+|Forbes)\b', re.IGNORECASE
)
GROWTH_SIGNALS = re.compile(
    r'\b(mentor|mentorship|learn from|grow with|career development|'
    r'training|onboarding|pair programming|code review culture)\b', re.IGNORECASE
)
RED_FLAGS = re.compile(
    r'\b(crypto|web3|blockchain|NFT|unpaid|equity[- ]only|defi)\b', re.IGNORECASE
)
NON_TECH_ROLES = re.compile(
    r'\b(customer experience|customer support|customer service|account manager|'
    r'sales rep|sales manager|business development|copywriter|copy editor|'
    r'(?:deputy |managing |content |senior )editor|editorial director|'
    r'content writer|social media|marketing manager|'
    r'operations manager|operations intern|office manager|recruiter|'
    r'talent acquisition|hr manager|hr coordinator|people ops|'
    r'it support|helpdesk|help desk|desktop support|'
    r'executive assistant|'
    r'client partner|account executive|relationship manager|'
    r'market insights|booking specialist|travel specialist|'
    r'crypto analyst|crypto trader|insurance.+associate|'
    r'data center.+technician)\b', re.IGNORECASE
)


# ── Extractors ───────────────────────────────────────────────

def extract_tech_stack(text: str) -> tuple[set, set]:
    text_lower = text.lower()
    ai = {t for t in AI_ML_STACK if _tech_match(t, text_lower)}
    adj = {t for t in ADJACENT_STACK if _tech_match(t, text_lower)}
    return ai, adj


def parse_salary(text: str) -> tuple[Optional[int], Optional[int]]:
    m = SALARY_PATTERN.search(text)
    if not m:
        return None, None
    low = int(m.group(1).replace(',', ''))
    high = int(m.group(2).replace(',', ''))
    if low < 1000:
        low *= 1000
    if high < 1000:
        high *= 1000
    return low, high


def parse_yoe(text: str) -> tuple[Optional[int], Optional[int]]:
    # Check specific range patterns first
    range_match = re.search(r'\b(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?|YoE)\b', text, re.IGNORECASE)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))
    if LOW_YOE.search(text):
        m = LOW_YOE.search(text)
        return 0, int(m.group(1))
    if MID_YOE.search(text):
        m = MID_YOE.search(text)
        val = int(m.group(1))
        return val, val + 2
    if HIGH_YOE.search(text):
        m = HIGH_YOE.search(text)
        val = int(m.group(1))
        return val, val + 3
    return None, None


def detect_seniority(title: str, description: str) -> str:
    if JUNIOR_SIGNALS.search(title):
        return 'junior'
    if re.search(r'\b(staff|principal)\b', title, re.IGNORECASE):
        return 'staff'
    if SENIOR_SIGNALS.search(title):
        return 'senior'
    if JUNIOR_SIGNALS.search(description):
        return 'junior'
    if HIGH_YOE.search(description):
        return 'senior'
    if LOW_YOE.search(description):
        return 'junior'
    if MID_YOE.search(description):
        return 'mid'
    return 'unknown'


def detect_remote_policy(text: str, title: str = "") -> str:
    combined = f"{title} {text}"
    # Positive worldwide/LATAM signals override geo-block when both present
    # (e.g., "US-based company, hiring worldwide")
    has_worldwide = bool(REMOTE_WORLDWIDE.search(combined))
    has_americas = bool(REMOTE_AMERICAS.search(combined))
    has_colombia = bool(REMOTE_COLOMBIA.search(combined))
    has_geo_block = bool(GEO_BLOCK.search(combined)) or bool(GEO_BLOCK_TITLE.search(title))

    if has_geo_block and not (has_worldwide or has_americas or has_colombia):
        return 'us_only'
    if HYBRID_SIGNALS.search(combined) and not (has_worldwide or has_americas or has_colombia):
        return 'hybrid'
    if has_colombia:
        return 'colombia'
    if has_americas:
        return 'americas'
    if has_worldwide:
        return 'worldwide'
    if re.search(r'\bremote\b', combined, re.IGNORECASE):
        return 'remote_unspecified'
    return 'unknown'


def detect_timezone(text: str) -> str:
    if TIMEZONE_FLEXIBLE.search(text):
        return 'flexible'
    if REMOTE_AMERICAS.search(text):
        return 'americas'
    if re.search(r'\b(us business|est|pst|cst|mst)\b', text, re.IGNORECASE):
        return 'us_business'
    if re.search(r'\b(emea|cet|gmt|bst)\b', text, re.IGNORECASE):
        return 'emea'
    return 'unknown'


def count_requirements(text: str) -> int:
    lines = text.split('\n')
    req_count = 0
    in_req_section = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'(?:requirements?|qualifications?|what you.?ll need|must have)', stripped, re.IGNORECASE):
            in_req_section = True
            continue
        if in_req_section and re.match(r'^[-•▪*]\s', stripped):
            req_count += 1
        elif in_req_section and stripped and not re.match(r'^[-•▪*]\s', stripped):
            if re.match(r'(?:nice to have|preferred|bonus|plus)', stripped, re.IGNORECASE):
                break
            if not stripped.startswith((' ', '\t')):
                in_req_section = False
    return req_count if req_count > 0 else len(re.findall(r'^[-•*]\s', text, re.MULTILINE))


# ── Scoring Functions ────────────────────────────────────────

def score_opportunity(title: str, description: str, company_name: str) -> tuple[int, int]:
    score = 50
    signals = 0
    combined = f"{title} {description}"
    ai_stack, adj_stack = extract_tech_stack(combined)

    # Non-tech role penalty (applied to title only for precision)
    if NON_TECH_ROLES.search(title):
        score -= 30
        signals += 1

    if len(ai_stack) >= 3:
        score += 18
        signals += 1
    elif len(ai_stack) >= 1:
        score += 10
        signals += 1
    elif len(adj_stack) >= 2:
        score += 3
    else:
        score -= 15

    if FUNDED_SIGNALS.search(description):
        score += 12
        signals += 1
    if RED_FLAGS.search(combined) and not ai_stack:
        score -= 20

    if len(description) > 500 and ai_stack:
        score += 8
        signals += 1
    elif len(description) < 150:
        score -= 10

    sal_low, sal_high = parse_salary(description)
    if sal_low and sal_high:
        score += 12
        signals += 1
    elif COMP_COMPETITIVE.search(description):
        score += 3

    if GROWTH_SIGNALS.search(description):
        score += 8
        signals += 1

    return max(0, min(100, score)), signals


def score_junior(title: str, description: str) -> tuple[int, int]:
    score = 50
    signals = 0

    # Check title first (stronger signal) — senior title overrides junior body
    if JUNIOR_SIGNALS.search(title):
        score += 30
        signals += 1
    elif SENIOR_SIGNALS.search(title):
        score -= 35
        signals += 1
    elif JUNIOR_SIGNALS.search(description):
        score += 20  # Weaker than title signal
        signals += 1
    elif SENIOR_SIGNALS.search(description):
        score -= 20
        signals += 1

    if LOW_YOE.search(description):
        score += 25
        signals += 1
    elif HIGH_YOE.search(description):
        score -= 30
        signals += 1
    elif MID_YOE.search(description):
        score -= 10
        signals += 1
    else:
        score += 5

    req_count = count_requirements(description)
    if req_count <= 5:
        score += 12
        signals += 1
    elif req_count <= 8:
        score += 3
    elif req_count > 10:
        score -= 15
        signals += 1

    if GROWTH_SIGNALS.search(description):
        score += 8
        signals += 1

    return max(0, min(100, score)), signals


def score_colombia(description: str, title: str = "") -> tuple[int, int]:
    score = 35  # Base — most AI/ML remote jobs are accessible from Colombia
    signals = 0
    combined = f"{title} {description}"

    has_worldwide = bool(REMOTE_WORLDWIDE.search(combined))
    has_americas = bool(REMOTE_AMERICAS.search(combined))
    has_colombia = bool(REMOTE_COLOMBIA.search(combined))

    # Hard block: US-only (but worldwide/LATAM override)
    if GEO_BLOCK.search(combined) or GEO_BLOCK_TITLE.search(title):
        if not (has_worldwide or has_americas or has_colombia):
            return 0, 2

    # Hybrid/onsite penalty (but worldwide/LATAM override)
    if HYBRID_SIGNALS.search(combined):
        if not (has_worldwide or has_americas or has_colombia):
            return 10, 2

    if has_colombia:
        score += 50  # Explicit Colombia mention (rare but strongest)
        signals += 1
    elif has_worldwide:
        score += 50  # Worldwide includes Colombia by definition
        signals += 1
    elif has_americas:
        score += 48  # LATAM/Americas — the primary Colombia-accessible signal
        signals += 1
    elif re.search(r'\bremote\b', combined, re.IGNORECASE):
        score += 30  # Bare "remote" — most remote jobs ARE worldwide
        signals += 1

    if TIMEZONE_FLEXIBLE.search(combined):
        score += 18
        signals += 1

    if CONTRACTOR_OK.search(combined):
        score += 20  # Deel/EOR = strong LATAM accessibility signal
        signals += 1

    sal_low, _ = parse_salary(description)
    if sal_low:
        score += 8
        signals += 1

    return max(0, min(100, score)), signals


def compute_composite(opp: int, junior: int, colombia: int,
                       weights: tuple[float, float, float] | None = None) -> int:
    w_opp, w_jr, w_col = weights or (0.30, 0.30, 0.40)
    return max(0, min(100, round(opp * w_opp + junior * w_jr + colombia * w_col)))


def confidence_level(signal_count: int) -> str:
    if signal_count >= 3:
        return 'high'
    elif signal_count >= 1:
        return 'medium'
    return 'low'


def is_hidden_junior(title: str, description: str, ja_score: int) -> bool:
    has_seniority_in_title = bool(
        re.search(r'\b(junior|senior|staff|lead|principal|intern)\b', title, re.IGNORECASE)
    )
    req_count = count_requirements(description)
    return (
        not has_seniority_in_title
        and ja_score >= 55
        and req_count <= 7
        and not HIGH_YOE.search(description)
    )


def score_job(title: str, description: str, company_name: str,
              weights: tuple[float, float, float] | None = None) -> ScoreResult:
    """Full deterministic scoring pipeline. Zero LLM cost."""
    title = title or ""
    description = description or ""
    company_name = company_name or ""
    opp, opp_signals = score_opportunity(title, description, company_name)
    junior, junior_signals = score_junior(title, description)
    col, col_signals = score_colombia(description, title)
    composite = compute_composite(opp, junior, col, weights)
    total_signals = opp_signals + junior_signals + col_signals

    ai_stack, adj_stack = extract_tech_stack(f"{title} {description}")
    all_tech = sorted(ai_stack | adj_stack)

    sal_min, sal_max = parse_salary(description)
    yoe_min, yoe_max = parse_yoe(description)

    return ScoreResult(
        opportunity=opp,
        junior=junior,
        colombia=col,
        composite=composite,
        confidence=confidence_level(total_signals),
        hidden_junior=is_hidden_junior(title, description, junior),
        method='rules',
        tech_stack=all_tech,
        seniority_signal=detect_seniority(title, description),
        yoe_min=yoe_min,
        yoe_max=yoe_max,
        salary_min=sal_min,
        salary_max=sal_max,
        remote_policy=detect_remote_policy(description, title),
        timezone_signal=detect_timezone(description),
        contractor_ok=bool(CONTRACTOR_OK.search(description)),
    )
