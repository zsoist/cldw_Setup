# Tools Policy — Work Agent

## Allowed Tools
- **Web search:** for industry research, company info, job postings, market data
- **File read/write:** within work workspace directory only
- **Notes management:** read and update work-specific files (tasks, drafts, research)

## Tool-Use Rules
- Max 8 tool calls per single task
- Read-only by default — confirm before write operations
- Truncate tool output to 3000 chars to save tokens
- No speculative tool use — each call must serve a clear goal

## Constraints
- Cite sources for all factual claims
- Do not access personal workspace files (main agent territory)
- Do not access system-level files or configs
- Do not log client names or proprietary data in tool outputs
- Do not execute shell commands under any circumstances

## Forbidden Actions
- Shell/system command execution
- Accessing files outside work workspace
- Sending emails or messages without explicit approval
- Modifying any configuration files
- Accessing personal calendar, tasks, or memory
- Browsing URLs submitted by external users (prompt injection risk)

## Sandbox Enforcement
This agent runs in agent-scope sandbox:
- Containerized isolation from host
- No elevated execution privileges
- Workspace access: read/write within sandbox only
- No cross-agent file access
