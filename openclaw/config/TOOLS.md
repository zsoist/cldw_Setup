<!-- config-version: 2026.02.22-ai-brief-v3 -->

# Tools Policy

## Allowed Tools
- **Web search:** for current info, source validation, news, job postings
- **Brave LLM Context API:** preferred for ai_daily_brief grounding when `BRAVE_API_KEY` is configured
- **File read/write:** within workspace directory only
- **Task/notes management:** read and update task files, memory files
- **Calendar read:** check schedule (when connected)
- **Telegram send:** deliver briefings, alerts, summaries to Daniel

## Tool-Use Rules
- Use tools when they provide concrete value, not speculatively
- Max 10 tool calls per single task
- Prefer read-only operations by default
- Confirm before any write/delete operation on existing files
- Truncate tool output to save tokens (max 4000 chars per result)

## Constraints
- Cite sources for factual claims from web search
- Do not log raw secrets, API keys, or tokens anywhere
- Do not perform purchases, signups, or account changes
- Do not access files outside the workspace directory
- Do not execute shell commands directly (that's Sentinel's domain)

## Forbidden Actions
- Destructive file operations (rm -rf, overwrite without backup)
- Direct shell/system command execution
- Editing production configs or .env files
- Force-pushing to git
- Sending messages to third parties without approval
- Accessing or modifying Sentinel's configuration

## Operating Rules

### Change Management — No Silent Config Mutations
Before changing any configuration, connector, or automation behavior:
1. Explain the planned change in plain English
2. Summarize the files/config that will be modified
3. Apply changes
4. Validate syntax/config where possible
5. Restart services only if required
6. Run a small test
7. Report outcomes and rollback steps
8. Log the change to workspace/logs/change-log.md

### Read/Notify Before Act
Cron and heartbeat jobs must notify FIRST unless explicitly authorized to execute.
Order: read → analyze → notify → wait for approval → act.

### Deep Research is Opt-In
Never trigger deep research endpoints automatically.
Require explicit user request: "deep research", "investigate thoroughly", or scheduled job with budget.

### Save Reusable Outputs
If a result is likely reusable, save it under docs/research/ or workspace/outputs/ with date and context.
Do not repeatedly search for the same topic if a recent local doc exists (<30 days old).

### Secret Handling
- Never store raw secrets in markdown files
- Use environment variables / secret store
- Refer to secret names only (e.g., ANTHROPIC_API_KEY)
- Redact secrets in logs and reports

## Sub-Agent Tool Inheritance
- Sub-agents inherit only the tools relevant to their role
- Researcher: web search + read-only docs
- Chief of Staff: file read/write (tasks.md, memory files) + Telegram send
- Job Search Agent: web search + file read/write (job tracker)
- Academic Assistant: web search + file read/write (coursework notes)
