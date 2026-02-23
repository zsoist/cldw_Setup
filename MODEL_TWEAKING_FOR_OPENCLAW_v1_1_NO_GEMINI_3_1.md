# Model Tweaking for OpenClaw

## Production Routing, Safety, Cost Control, and Git/VPS Operations Guide

**Version:** 1.1 (Gemini 3.1 removed)  
**Audience:** OpenClaw operators using API-based model routing (Gemini + Claude)  
**Primary Goal:** Build a cost-efficient, reliable, and safe OpenClaw setup with progressive escalation and strict premium-model controls.

---

## Table of Contents

1. Purpose and Scope
2. Target Model Hierarchy
3. Design Principles
4. Detailed Role Definition by Model
5. Escalation Policy
6. Opus Manual-Only Safety Protocol
7. Task Routing Matrix
8. Token, Cost, and Retry Controls
9. OpenClaw Gateway Considerations
10. VPS Deployment Considerations
11. Security and Secret Management
12. Git Workflow and Main Branch Protection
13. Safe Deployment and Release Process
14. Observability and Logging
15. Operational Checklists
16. Incident and Rollback Guidance
17. Reference Policy Templates
18. Implementation Notes for Claude Code / Codex
19. Final Recommendations

---

## Purpose and Scope

This document defines a **production-grade model routing and operational policy** for an OpenClaw deployment that prioritizes:

- low default cost
- high throughput
- controlled escalations
- safety for premium model usage
- operational discipline (VPS + Git + deployment)
- auditability and repeatability

### Stack covered
- **Gemini 2.5 Flash** as default/main
- **Gemini 2.5 Pro** as first escalation
- **Claude Sonnet 4.6** as high-quality escalation
- **Claude Opus 4.6** as manual-only final tier

This is an **operations and routing playbook**, not a benchmark report.

---

## Target Model Hierarchy

1. **Gemini 2.5 Flash** — default worker / orchestrator  
2. **Gemini 2.5 Pro** — first escalation for harder tasks  
3. **Claude Sonnet 4.6** — premium-quality escalation for production-grade outcomes  
4. **Claude Opus 4.6** — manual-only, explicit invocation, safety-gated  

### Why this hierarchy is effective
- Flash keeps daily cost low.
- Pro catches many “hard but not premium” tasks.
- Sonnet provides reliability for high-quality outputs and code.
- Opus is reserved for high-value situations and never triggered by frustration or loops.

---

## Design Principles

### 1) Default cheap, escalate selectively
Do not pay premium rates for routine orchestration work.

### 2) Escalate on objective criteria, not intuition
Use measurable triggers such as:
- failure count
- patch size
- context size
- number of tool outputs to synthesize
- confidence score
- user-declared criticality

### 3) Compress before escalation
Before moving to a more expensive model:
- trim history
- remove duplicates
- summarize tool outputs
- convert raw logs/pages into structured intermediate data

### 4) Premium models require explicit governance
Claude Opus 4.6 should be:
- manual-only
- explicit request
- preflight checks
- safe mode
- cost visibility
- call limits

### 5) Routing is part of operations, not just prompting
A working OpenClaw setup depends on:
- model policy
- system reliability
- secret handling
- deployment discipline
- branch protection
- rollback readiness

---

## Detailed Role Definition by Model

## Gemini 2.5 Flash (Default/Main)

### Role
**Tier 0 default worker and orchestrator**

### Intended Uses
- task triage
- summarization
- extraction/parsing
- formatting/transformation
- lightweight coding
- routing/tool selection
- context compression
- intermediate drafts
- structured outputs (JSON, bullet summaries, tables)

### Strengths in an OpenClaw context
- cost-efficient high-volume throughput
- suitable for repetitive tool loops
- ideal for first-pass thinking and orchestration

### Known Failure Patterns
- repeated retries on complex tasks without progress
- shallow handling of nuanced multi-file code changes
- lower reliability on difficult strategic synthesis

### Operational Rule
- **One meaningful attempt**
- If complexity/failure triggers fire, **escalate**
- Do **not** let Flash churn through repeated retries

---

## Gemini 2.5 Pro (First Escalation)

### Role
**Tier 1 escalator for harder tasks**

### Intended Uses
- harder reasoning
- medium/large coding tasks
- architecture suggestions
- source synthesis
- robustness improvements
- failure recovery after Flash

### When to Route Here
- Flash fails once
- user requests “production-ready,” “robust,” or “deep analysis”
- patch size or scope exceeds Flash threshold
- task involves multiple interdependent constraints

### Operational Rule
- Pro is an **escalation tier**, not the default
- Prefer one good Pro pass over multiple Flash retries

---

## Claude Sonnet 4.6 (High-Quality Escalation)

### Role
**Tier 2 premium-quality escalation**

### Intended Uses
- multi-file refactors
- difficult debugging
- production-grade patches
- final polished deliverables
- nuanced tradeoff analysis
- high-confidence final output generation

### Why this tier exists
It is often cheaper operationally to do:
- one high-quality Sonnet pass  
than
- several lower-tier retries + one eventual premium pass

### Operational Rule
Use Sonnet when:
- correctness matters more than cost
- output quality is critical
- prior tiers are unstable

---

## Claude Opus 4.6 (Manual-Only Premium Final Tier)

### Role
**Tier 3 manual-only premium model**

### Intended Uses
- high-stakes reasoning
- critical strategic synthesis
- final review on sensitive or high-impact deliverables
- exceptionally difficult tasks after prior tiers are insufficient

### Strict Policy
- **Never auto-route**
- **Never invoke due to repeated frustration**
- **Require explicit user instruction**

### Operational Rule
Opus is a deliberate escalation, not a convenience fallback.

---

## Escalation Policy

## Flash → Pro Escalation Triggers

Escalate from Gemini 2.5 Flash to Gemini 2.5 Pro if **any** of the following are true:

- Flash failed once (non-transient failure)
- Task complexity score is medium/high
- Code patch exceeds threshold (e.g., 120–200 LOC)
- More than 3 tool outputs need synthesis
- Confidence score is low
- User requests:
  - “robust”
  - “production-ready”
  - “deep”
  - “thorough”
  - “high confidence”
- Multi-constraint formatting requirements + non-trivial logic

### Non-trigger examples (stay on Flash)
- simple summaries
- extraction
- formatting conversions
- short shell commands
- basic code snippets

---

## Pro → Sonnet 4.6 Escalation Triggers

Escalate to Sonnet 4.6 if:
- code spans multiple files/modules
- correctness and reliability are top priority
- prior outputs are inconsistent
- final client-facing or production deliverable is required
- patch quality is unstable across Gemini tiers
- nuanced reasoning/tradeoffs exceed acceptable error tolerance
- Gemini 2.5 Pro failed once on a hard task

### Practical rule
Prefer one Sonnet escalation over repeated Pro retries on the same failure mode.

---

## Sonnet → Opus 4.6 Escalation Triggers (Manual-Only)

Only allow if:
- user explicitly requests Opus
- task is high-value or high-risk
- safety preflight passes
- cost estimate is available and within cap

---

## Opus Manual-Only Safety Protocol

### Required Conditions Before Any Opus Call
1. **Explicit Invocation**
2. **Task Classification**
3. **Cost Preflight**
4. **Context Compression**
5. **Safe Mode Enabled**
6. **Call Limits**
7. **Retry Limit**

### Approved task classes
- `high_stakes_reasoning`
- `critical_code_review`
- `final_synthesis`
- `sensitive_action_planning`

### Recommended limits
- `max_opus_calls_per_task = 1`
- `max_opus_calls_per_day = 2`

### Preflight checklist (recommended)
- [ ] Explicit Opus keyword detected
- [ ] Task class is approved
- [ ] Estimated cost within soft/hard cap
- [ ] Context compressed and deduplicated
- [ ] Safe mode enabled
- [ ] No destructive actions without confirmation

---

## Task Routing Matrix

| Task Type | Default | 1st Escalation | Final |
|---|---|---|---|
| Search + summarize | Gemini 2.5 Flash | Gemini 2.5 Pro | Sonnet 4.6 |
| Data extraction / parsing | Gemini 2.5 Flash | Gemini 2.5 Pro | Sonnet 4.6 |
| Light coding / scripts | Gemini 2.5 Flash | Gemini 2.5 Pro | Sonnet 4.6 |
| Multi-file refactor | Gemini 2.5 Pro | Sonnet 4.6 | Opus (manual) |
| Architecture / systems design | Gemini 2.5 Pro | Sonnet 4.6 | Opus (manual) |
| Final polished deliverable | Gemini 2.5 Pro | Sonnet 4.6 | Opus (manual) |
| High-stakes strategic synthesis | Sonnet 4.6 | — | Opus (manual) |

### Note
This matrix is a starting point. Refine it using real logs and failure patterns.

---

## Token, Cost, and Retry Controls

### Token Control Rules
Always:
- trim conversation history
- summarize before escalation
- dedupe tool outputs
- use structured intermediate outputs

Never:
- resend raw logs repeatedly
- paste full pages unnecessarily
- retry identical prompts with bloated context

### Recommended starter budget caps
- `task_soft_cap_usd = 0.25`
- `task_hard_cap_usd = 0.75`
- `opus_soft_cap_usd = 1.50`
- `opus_hard_cap_usd = 3.00`
- `daily_hard_cap_usd = 10.00`

### Retry Policy
- `max_retries_per_step = 1`
- `max_retries_per_task = 2`
- `same_prompt_retry = false`
- `retry_requires_strategy_change = true`

### Valid strategy changes between retries
- reduce scope
- split task into subtasks
- summarize context first
- change output format (JSON before prose)
- escalate to next tier

---

## OpenClaw Gateway Considerations

Treat OpenClaw as the **gateway and control plane**:
- sessions
- routing
- channels
- auth abstractions
- policy enforcement
- logging hooks

### Policy implication
Implement model tweaking as:
- centralized routing policy
- explicit aliases
- preflight checks
- auditable logs

Not scattered prompt hacks.

### Recommended route aliases
- `gemini_fast` → Gemini 2.5 Flash
- `gemini_pro` → Gemini 2.5 Pro
- `claude_sonnet` → Claude Sonnet 4.6
- `claude_opus_manual` → Claude Opus 4.6

---

## VPS Deployment Considerations

## Sizing (API-routed setup, no local LLM inference)
Baseline:
- **2–4 vCPU**
- **4–8 GB RAM**
- SSD
- Ubuntu LTS / Debian stable

Scale up for:
- vector DB
- monitoring
- heavy file processing
- multiple workers

### Practical note
RAM headroom and disk reliability usually matter more than raw CPU for API-routed agents.

## Service Management
Use process supervision (e.g., systemd):
- auto-restart
- start on boot
- log rotation
- health checks

### Test these scenarios
- server reboot
- network interruption
- provider API timeout
- expired/revoked API key
- disk nearly full

## Network Exposure
Prefer:
- localhost binding
- SSH tunnel / private network (e.g., Tailscale)
- minimal public ports

Avoid:
- public control UI exposure without hardening
- password-only SSH on public hosts

## Environment separation
Preferred:
- local / staging / prod

If single VPS initially:
- separate users
- separate env files
- separate logs
- separate service units (if practical)

---

## Security and Secret Management

### Never commit
- `.env`
- live API keys
- Telegram tokens
- OAuth tokens
- auth snapshots
- logs with secrets

### Always do
- least privilege keys
- file permissions (`chmod 600`)
- secret rotation
- logging redaction
- separate keys per environment

### Secret handling rules
- separate runtime secrets from repo
- rotate immediately after suspected compromise
- avoid sending raw config files to models/agents
- redact auth headers and bearer tokens in logs

---

## Git Workflow and Main Branch Protection

## Branching Strategy
- `main` = production
- `dev` = integration (optional)
- feature branches for changes

### Feature branch examples
- `feat/routing-thresholds`
- `fix/opus-preflight`
- `ops/vps-hardening`
- `security/log-redaction`

## Commit conventions
- `feat:`
- `fix:`
- `chore:`
- `docs:`
- `refactor:`
- `security:`
- `ops:`

### Commit hygiene
- one logical change per commit
- avoid mixing routing + infra + formatting noise
- include rollback-friendly changes

## Push and merge rule
> **No direct agent-driven pushes to `main`.**

### Preferred flow
1. Feature branch
2. Local checks
3. Push branch
4. PR
5. Review + checks
6. Merge

## Main branch protections (recommended)
- PR required
- status checks required
- conversation resolution required
- block force push
- block deletion
- linear history

### Stronger protections (optional)
- signed commits
- merge queue
- restricted push permissions
- apply protections to admins too

---

## Safe Deployment and Release Process

### Recommended flow
1. Change on feature branch
2. Local validate
3. PR and review
4. Staging deploy
5. Verification
6. Merge/promote to `main`
7. Production deploy
8. Post-deploy validation
9. Tag release / rollback point

### Post-deploy validation
- [ ] Gateway starts
- [ ] Flash default route works
- [ ] Pro escalation works
- [ ] Sonnet route works
- [ ] Opus manual-only gate works
- [ ] logs are healthy
- [ ] no secrets in logs

### Agent limitations for deployment changes
Agent may:
- generate patches
- draft PR descriptions
- run checks/tests
- propose commit messages

Agent should not automatically:
- merge to `main`
- deploy to production
- disable protections
- expose services publicly

---

## Observability and Logging

### Minimum per-task logs
- timestamp
- task ID
- task type
- model alias
- escalation path
- retries
- tokens (estimated/actual)
- cost estimate
- latency
- success/failure
- error type

### Weekly review questions
- Which tasks escalate most?
- Are Sonnet calls reducing retries enough?
- Is Pro overused for work Flash could handle?
- Any unexpected Opus usage?
- Are retry loops causing budget leakage?

### Recommended derived metrics
- escalation rate by task class
- success rate by model tier
- avg cost per completed task
- retry rate by model
- Opus invocations per day/week

---

## Operational Checklists

### Daily
- [ ] Service healthy
- [ ] Spend within cap
- [ ] No auth failures
- [ ] Logs rotating
- [ ] No abnormal Opus calls

### Weekly
- [ ] Review escalations
- [ ] Audit secrets redaction
- [ ] Patch/update host
- [ ] Confirm backups/rollback points
- [ ] Review Flash/Pro/Sonnet threshold effectiveness

### Pre-merge routing change checklist
- [ ] Objective triggers defined
- [ ] No accidental auto-Opus path
- [ ] Cost caps preserved
- [ ] Retry policy explicit
- [ ] Logs include new alias/routes
- [ ] Rollback path documented

---

## Incident and Rollback Guidance

### Common incidents
- runaway cost due to loops
- accidental premium routing
- provider auth failure
- broken alias config
- secret leakage in logs

### Immediate response priorities
1. Stop cost bleed
2. Protect secrets
3. Restore service
4. Preserve logs (redacted)
5. Document root cause and fix

### Rollback rule
If production routing is unstable, revert to:
- Flash default
- Pro escalation only
- Sonnet manual if needed
- Opus disabled until fixed

### Recovery checklist (minimum)
- [ ] Revert to last known-good config
- [ ] Restart service
- [ ] Validate routes and auth
- [ ] Re-enable traffic gradually
- [ ] Monitor cost and errors for 30–60 minutes

---

## Reference Policy Templates

### Routing Policy Template (YAML-like)

```yaml
routing_policy:
  default_model: gemini_fast
  aliases:
    gemini_fast: gemini_2_5_flash
    gemini_pro: gemini_2_5_pro
    claude_sonnet: claude_sonnet_4_6
    claude_opus_manual: claude_opus_4_6

  escalation:
    flash_to_pro:
      triggers:
        - flash_failed_once
        - complexity_medium_high
        - patch_gt_150_loc
        - synthesize_gt_3_tool_outputs
        - low_confidence
        - user_requests_production_quality

    to_sonnet:
      triggers:
        - gemini_pro_failed_once
        - multi_file_refactor
        - final_polish_required
        - reliability_priority
        - unstable_outputs_from_prior_tiers

    to_opus:
      manual_only: true
      require_explicit_keyword: true
      explicit_keywords: ["opus", "use opus", "escalate to opus"]
      preflight_required:
        - task_classification
        - cost_estimate
        - context_compression
        - safe_mode_enabled

  budgets:
    task_soft_cap_usd: 0.25
    task_hard_cap_usd: 0.75
    opus_soft_cap_usd: 1.50
    opus_hard_cap_usd: 3.00
    daily_hard_cap_usd: 10.00

  retries:
    max_retries_per_step: 1
    max_retries_per_task: 2
    same_prompt_retry: false
    retry_requires_strategy_change: true

  token_controls:
    summarize_before_escalation: true
    trim_history: true
    dedupe_tool_outputs: true
    prefer_structured_intermediates: true

  safety:
    safe_mode_default: true
    destructive_actions_require_confirmation: true
    publish_send_commit_require_confirmation: true
    secret_redaction_enabled: true
```

### Main Branch Policy Template

```md
## Main Branch Policy
- `main` is always deployable.
- No direct pushes to `main`.
- PR required for production changes.
- Status checks must pass.
- Conversation resolution required.
- Force pushes disabled.
- Branch deletion disabled.
- Linear history required.
- Agents may draft patches/PRs but may not merge to `main` automatically.
```

### Post-Deploy Validation Template

```md
## Post-Deploy Validation Checklist (OpenClaw)

### Routing
- [ ] Default route = Gemini 2.5 Flash
- [ ] Flash -> Pro escalation works
- [ ] Sonnet route reachable
- [ ] Opus route remains manual-only

### Safety
- [ ] Opus preflight required
- [ ] Destructive actions require confirmation
- [ ] No secrets in logs
- [ ] Dashboard not publicly exposed unintentionally

### Operations
- [ ] Service running and auto-restart configured
- [ ] Health checks passing
- [ ] Logs rotating
- [ ] Disk usage acceptable
```

---

## Implementation Notes for Claude Code / Codex

Ask your coding agent to implement:

1. **Routing middleware**
   - alias resolver
   - task classifier
   - escalation evaluator
   - retry controller

2. **Safety preflight module**
   - Opus explicit keyword detector
   - cost estimator
   - context compressor
   - safe mode enforcer

3. **Telemetry module**
   - per-task logs
   - escalation traces
   - cost estimates

4. **Config schema validation**
   - fail closed on invalid route config
   - environment-based loading

5. **Tests**
   - escalation trigger tests
   - Opus gate tests
   - config validation tests

### Implementation constraints
- Do not hard-code secrets
- Use model aliases
- Make Opus auto-route impossible by default
- Add structured logs for routing decisions
- Provide clear threshold comments

---

## Final Recommendations

This guide is effective because it combines:
- **model routing discipline**
- **cost controls**
- **safety gates**
- **VPS reliability**
- **Git deployment hygiene**
- **observability-driven tuning**

### Practical next steps
1. Implement alias-based routing + logs
2. Enforce retry and budget caps
3. Add Opus preflight guard
4. Review logs after 1–2 weeks
5. Tune Flash/Pro/Sonnet thresholds based on real outcomes

### Operating principle
> **Optimize the system, not the model.**

---

## Filename Recommendation

- `MODEL_TWEAKING_FOR_OPENCLAW.md`
