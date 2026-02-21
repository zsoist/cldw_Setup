<!-- config-version: 2026.02.21-main-hardening -->

# Sandbox Policy

## Overview
Sandboxing isolates agents in containerized environments, preventing direct host access.
This is the primary security control for agents handling untrusted inputs or risky operations.

## Agent Sandbox Assignments

### Main Agent (Claw) — No Sandbox
- **Reason:** runs inside Docker container already (docker-compose isolation)
- **Risk level:** low — conservative tool policy, trusted input (Daniel only)
- **Elevated exec:** NOT granted
- **Workspace access:** read/write within `/home/node/.openclaw/workspace`

### Work Agent (Claw Work) — Agent-Scope Sandbox
- **Reason:** handles professional data that should be isolated from personal
- **Risk level:** medium — processes work content, potential for sensitive data
- **Elevated exec:** NOT granted — never grant for work agent
- **Workspace access:** read/write within work sandbox only
- **Sandbox scope:** agent (one sandbox per agent — recommended default)

### Future Agents — Default Sandbox Policy
Any new agent should be sandboxed by default. Remove sandbox only if:
- Agent handles exclusively trusted input (from Daniel directly)
- Agent has no tool/command execution capability
- Explicit review confirms low risk

## Sandbox Scope Options

| Scope | Isolation | Overhead | Use When |
|-------|-----------|----------|----------|
| **Session** | New sandbox per session | Highest | Handling untrusted external content |
| **Agent** | One sandbox per agent | Medium | Default for most agents (recommended) |
| **Shared** | Shared across agents | Lowest | Only when agents need file sharing |

**Default:** Agent scope for all sandboxed agents.

## Workspace Access Levels

| Level | Permissions | Use When |
|-------|-------------|----------|
| **None** | No workspace access | Agent only needs API/web access |
| **Read-only** | Can read, cannot write | Research agents, reviewers |
| **Read/write** | Full workspace access | Task management, drafting |

**Default for new agents:** Read-only. Upgrade to read/write only if needed.

## Critical Warning: Elevated Execution
Elevated exec can bypass sandbox and run commands on the host.

**Rules:**
- NEVER grant elevated exec to agents handling untrusted input
- NEVER grant elevated exec to agents in group chats or public channels
- Only consider elevated exec for the main agent with Daniel's explicit approval
- Document the reason if elevated exec is ever granted

## Post-Config Security Checks
After changing sandbox settings:
1. Run security audit
2. Run health check
3. Test with a harmless tool call to verify isolation
4. Verify workspace access boundaries are enforced
5. Check that cross-agent file access is denied
