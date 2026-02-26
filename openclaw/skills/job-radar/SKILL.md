---
name: job-radar
description: AI/ML remote job radar with junior-accessibility scoring and Colombia viability analysis
triggers:
  - "job search"
  - "job radar"
  - "job leads"
  - "vacantes"
  - "buscar trabajo"
  - "/job_radar"
  - "/job_search"
  - "/job_why"
  - "/job_trends"
  - "/job_skills"
  - "/job_hidden"
  - "/job_save"
  - "/job_dismiss"
  - "/job_mark"
  - "/job_timeline"
  - "/job_profile"
  - "/job_sync"
  - "/job_health"
  - "/job_keys"
model: google/gemini-2.5-flash
cost_tier: cheap
state_file: /home/node/.openclaw/workspace/logs/job-radar-state.json
backend_url: http://job-radar-api:8080
---

# Job Radar Skill

## Role
Provide high-signal AI/ML remote job discovery with explicit scoring context:
- Opportunity score
- Junior accessibility score
- Colombia viability score
- Hidden junior opportunity flag

## Response Discipline (mandatory)
- Return final answer only.
- Never output `Reasoning:`, chain-of-thought, or process narration.
- Never send pre-execution messages like "I will now..." or "checking...".
- If command is ambiguous, ask one concise clarifying question.

## Retrieval and Search Policy
- All web discovery/search is delegated to Job Radar backend (`{backend_url}`).
- Backend discovery is Brave LLM Context-only in production (`/res/v1/llm/context`).
- Do not use `web_search` or `web_fetch` for job discovery.
- For backend calls, use `exec` with `curl`.

Canonical backend call patterns:
```bash
# GET
curl -sS --max-time 20 "http://job-radar-api:8080/<path>?<query>"

# POST JSON
curl -sS --max-time 20 -X POST "http://job-radar-api:8080/<path>" \
  -H "Content-Type: application/json" \
  -d '{"key":"value"}'
```

## Backend Unavailability Protocol
- If backend is unreachable or times out, return:
  - `⚠️ Job Radar backend is offline (http://job-radar-api:8080 unreachable). Use /job_health.`
- Retry at most once.
- Never fabricate job results.

## State File
Read `{state_file}` for status-oriented commands:
- `last_sync_at`
- `last_digest_at`
- `active_profile`
- `new_jobs`
- `health`

## Commands

### `/job_radar [brief|full]`
Default `brief`: top 5 jobs.
`GET /api/v1/jobs?limit=5`

### `/job_search <query>`
`GET /api/v1/jobs/search?q=<query>&limit=10`

### `/job_why <job_id>`
`GET /api/v1/jobs/<job_id>/why`

### `/job_trends [7d|30d|90d]`
Map window to days and call:
`GET /api/v1/trends/summary?days=<days>`

### `/job_skills [7d|30d|90d]`
`GET /api/v1/trends/skills?days=<days>`

### `/job_hidden [n]`
`GET /api/v1/jobs?hidden_junior_only=true&limit=<n>` (default `n=10`)

### `/job_save <job_id>`
`POST /api/v1/jobs/<job_id>/save`

### `/job_dismiss <job_id>`
`POST /api/v1/jobs/<job_id>/dismiss`

### `/job_mark <job_id> <status>`
Valid status: `applied|interviewing|offered|rejected|closed`
`POST /api/v1/jobs/<job_id>/mark` body `{"status":"<status>"}`

### `/job_timeline <job_id>`
`GET /api/v1/jobs/<job_id>/timeline`

### `/job_profile list`
`GET /api/v1/profiles`

### `/job_profile set <name>`
`POST /api/v1/profiles/set-active` body `{"name":"<name>"}`

### `/job_profile show`
`GET /api/v1/profiles/active`

### `/job_sync`
`POST /api/v1/ingestion/sync`
Reply concise ack: `Sync started. New jobs should appear in ~1-2 minutes.`

### `/job_health`
`GET /health/full`

### `/job_keys`
Alias of `/job_health`, but focus output on API key checks:
- `brave_api`
- `anthropic_api`
- `telegram_bot`

## Model Escalation Policy
- Default: Gemini Flash (routing, list formatting, status).
- Escalate to Gemini Pro for:
  - `/job_why` explanation synthesis
  - `/job_trends` interpretation
  - detailed recommendation rationale
- Sonnet 4.6: only when user explicitly requests `think harder`.
- Opus: manual-only, explicit user request.

## Output Format
For list-style responses, keep compact structure:
```text
1) <title> @ <company>
   Opp: <score> | JA: <score> | COL: <score> | <scope>
   <url>
```

## Constraints
- Max 10 tool calls per command.
- Never expose secrets.
- Never hardcode IDs/scores.
- Require clear user intent before write actions if context is ambiguous.
