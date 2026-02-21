# Tools Policy

## Allowed Tools
- **Web search:** for current info, source validation, news, job postings
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

## Sub-Agent Tool Inheritance
- Sub-agents inherit only the tools relevant to their role
- Researcher: web search + read-only docs
- Chief of Staff: file read/write (tasks.md, memory files) + Telegram send
- Job Search Agent: web search + file read/write (job tracker)
- Academic Assistant: web search + file read/write (coursework notes)
