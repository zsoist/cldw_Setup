# Job Search Automation with OpenClaw

> Research note, February 2026. OpenClaw does not have a first-party "job search module." Job-search automation is assembled from core tools + cron + skills + hooks.

## What OpenClaw Can Do (Strong Fit)

### 1. Automated Job Discovery Scans

Use Brave LLM Context API (`/res/v1/llm/context`) as the sole web retrieval backend for job search scans.

```
Cron: weekdays 08:00 -> Brave LLM Context retrieval for target roles -> filter -> digest
```

Works well for:
- LinkedIn public job postings (no login required for search results)
- Company career pages (direct URL fetch)
- Job aggregators (Indeed, Glassdoor public listings)
- Niche boards (AngelList, Y Combinator, sector-specific)

### 2. Scheduled Digests

Deliver curated job listings via Telegram at defined windows:

| Schedule | Content | Model |
|----------|---------|-------|
| Weekdays 08:00 | New postings matching criteria | Flash |
| Weekly Friday 17:00 | Week summary + pipeline status | Flash |
| On-demand | Deep research on specific company/role | Pro |

Uses cron (timezone-aware, disk-persistent, retry-capable). Jobs run in isolated mode when clean context is preferred.

### 3. Isolated Analysis Runs

For comparing multiple roles or companies, use isolated cron mode:

- Clean context (no conversation history pollution)
- Optional cheaper model for batch processing
- Results saved to `workspace/outputs/reports/`

### 4. Draft Generation

OpenClaw can generate tailored output for each application:

| Output | Agent | Model |
|--------|-------|-------|
| Outreach messages (LinkedIn, email) | Work | Flash/Pro |
| Tailored resume bullet points | Work | Pro |
| Cover letter variants by company | Work | Pro |
| Interview prep notes | Work | Flash |
| Company research briefs | Work (Researcher sub-agent) | Pro |

All drafts saved to `workspace/outputs/drafts/` for review before sending.

### 5. Pipeline Orchestration

Use the Lobster/hook pattern for deterministic multi-step flows:

```
Trigger → Search → Filter → Score → Draft → Notify
```

Each step is a discrete tool call with defined input/output. The pipeline can:
- Score postings against criteria in `workspace/business/goals-okrs.md`
- Filter by location, seniority, compensation signals
- De-duplicate against previously seen listings
- Route high-priority matches to immediate Telegram notification

### 6. Channel Delivery

Results delivered to Telegram DM (Sentinel bot or OpenClaw bot depending on context). Format:

```
📋 Job Search Digest — Mon Feb 23
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3 new matches | 1 high priority

🔴 Senior AI Engineer — Stripe (SF/Remote)
   Match: 92% | Posted: 2d ago
   → Draft outreach ready in outputs/drafts/

🟡 ML Platform Lead — Notion (NYC)
   Match: 78% | Posted: 1d ago

🟡 Applied AI — Anthropic (SF)
   Match: 85% | Posted: 3d ago
```

## What Requires Caution

### Browser Automation

Only needed for:
- JS-heavy career pages that don't render with `web_fetch`
- Login-required portals (LinkedIn logged-in search, internal job boards)

Higher cost (tokens + time). Keep Brave LLM Context budgets tight first; escalate to browser only when needed.

### Application Submission

OpenClaw can draft but should **not auto-submit** applications. Reasons:
- Many portals require login + CAPTCHA
- Application quality needs human review
- Incorrect submissions damage reputation
- Terms of service considerations

**Flow:** Draft → human review → manual submit.

### Rate Limiting

Job boards may rate-limit or block aggressive scraping. Mitigations:
- Space searches across cron windows (not all at once)
- Use Brave LLM Context grounding rather than ad-hoc scraping
- Rotate search queries to avoid repetitive patterns
- Save results to `docs/research/` to avoid re-searching

## Implementation Plan

### Phase 1: Discovery (Week 1)

1. Define target criteria in `workspace/business/goals-okrs.md`:
   - Target roles (title keywords)
   - Target companies (explicit list)
   - Location preferences
   - Compensation floor
   - Deal-breakers

2. Create a `job-search` skill or add to existing cron jobs in CRON.md:
   - Weekday 08:00 scan (Business Daily Snapshot already exists — extend it)
   - Friday 17:00 weekly digest (Weekly KPI Digest already exists — extend it)

3. Set up output paths:
   - `workspace/outputs/reports/job-search/` — digests
   - `workspace/outputs/drafts/applications/` — outreach drafts

### Phase 2: Drafting (Week 2)

4. Configure the Work agent's Researcher sub-agent for company research
5. Template outreach messages in `docs/templates/`
6. Test draft quality on 3-5 real postings

### Phase 3: Pipeline (Week 3+)

7. Build scoring logic against OKR criteria
8. Add de-duplication (track seen listings in a log file)
9. Tune notification thresholds (only alert for >80% match)

## Relevant Project Files

| File | Role in Job Search |
|------|-------------------|
| `openclaw/config/CRON.md` | Job #8 (Business Daily Snapshot) and #11 (Weekly KPI Digest) — extend these |
| `openclaw/config/AGENTS.md` | Researcher sub-agent handles deep company research |
| `openclaw/agents/work/SOUL.md` | Work agent scope includes job search |
| `openclaw/agents/work/USER.md` | Professional profile for tailoring outreach |
| `workspace/business/goals-okrs.md` | Target criteria and success metrics |
| `workspace/business/operating-rules.md` | Quality standards for outreach |
| `docs/templates/` | Outreach and brief templates |
