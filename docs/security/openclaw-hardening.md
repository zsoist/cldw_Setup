# OpenClaw Security Hardening

Operational security practices specific to the OpenClaw gateway. Complements `access-boundaries.md` (agent/channel matrix) and Sentinel's whitelist model.

## 1. Run Security Audits Continuously

Use `openclaw security audit` as part of the ops loop — not just post-deploy. The audit checks:

- Auth exposure (token leaks, pairing misconfig)
- Browser exposure (public bind, missing auth)
- Elevated allowlists (tools.elevated escape hatches)
- Filesystem permissions (workspace, config, secrets)
- Policy drift (runtime config vs declared config)

Use `--deep` for full scan. Use `--fix` to auto-remediate known safe fixes. Run after every config or network change.

## 2. Keep Gateway Local and Locked

Baseline security posture (enforced in our deployment):

| Control | Setting | Reference |
|---------|---------|-----------|
| Network bind | Loopback only (127.0.0.1:18789) | docker-compose.yml |
| Auth | Token required | env.template |
| Tools | Strict profile | openclaw/config/TOOLS.md |
| Channels | DM isolation (no groups) | openclaw/config/CHANNELS.md |

OpenClaw blocks binding beyond loopback without auth as a built-in guardrail. Do not disable this.

## 3. DM Scope as Data-Leak Control

DM scope controls context sharing between conversations:

| Setting | Behavior | Use When |
|---------|----------|----------|
| `dmScope: "main"` | All DMs share context with main session | Single-user (our default) |
| `dmScope: "per-channel-peer"` | Each sender gets isolated context | Multi-user inbox |
| `dmScope: "per-account-channel-peer"` | Per-account + per-channel + per-sender isolation | Multi-account setups |

For our single-user Telegram setup, `"main"` is correct. If the bot ever becomes reachable by multiple senders, switch to `"per-channel-peer"` immediately to prevent cross-user context bleed.

## 4. DM Pairing and Allowlists

- Pairing codes are **short-lived (1 hour)** — do not pre-generate
- Pending pairing requests are capped by default
- Telegram user ID allowlist is enforced at the handler level (both OpenClaw and Sentinel)
- If the bot is reachable by unknown senders, unauthorized requests are rejected before any API call

## 5. Sandbox ≠ Trust

OpenClaw docs are explicit: **sandboxing reduces blast radius but is not a perfect boundary**.

Critical points for our deployment:

| Risk | Mitigation |
|------|-----------|
| Sandbox off → tools run on host | Our work agent has sandbox enabled (agent-scope) |
| `tools.elevated` is an escape hatch to host execution | We do not use elevated tools in any agent profile |
| Workspace is default cwd, not a hard sandbox | Sandbox mode makes workspace the enforced boundary |
| Write access when not needed | Use `workspaceAccess: "none"` or `"ro"` by default |

**Rule:** Never enable `tools.elevated` unless you understand it bypasses sandbox isolation entirely.

## 6. Constrain Tool Surface Aggressively

Tool profiles control what's available:

| Profile | Available Tools | Risk Level |
|---------|----------------|------------|
| `minimal` | `session_status` only | Lowest |
| `strict` | Limited set, no shell, no elevated | Low (our default) |
| `standard` | Standard tools including shell | Medium |
| `full` | Everything including elevated | Highest |

Additional controls:
- `tools.allow` / `tools.deny` — deny always wins over allow
- Layer deny lists on top of profile for defense-in-depth
- Sentinel has its own separate whitelist (see `sentinel/tools.py`)

## 7. Plugin Supply Chain

OpenClaw plugin security model:

- **Install path:** npm registry only — git/url/file specs are rejected
- **Dependency install:** runs `npm install --ignore-scripts` (blocks postinstall attacks)
- **Trust model:** only enable plugins you have explicitly reviewed

Even with these guardrails, treat all third-party plugins as untrusted code until manually reviewed.

## 8. Patch Management

**Active advisories (as of Feb 2026):**

| Advisory | Severity | Issue |
|----------|----------|-------|
| GHSA-82g8-464f-2mv7 | Critical | Env var injection |
| GHSA-jjgj-cpp9-cvpv | High | MCP MEDIA local file exfiltration path |

Affected versions: <= 2026.2.19-2. Patched: >= 2026.2.21.

**Operational practice:**
- Monitor GitHub advisories, tags, and releases together — not releases alone
- Advisories may reference patched versions before the release is published
- Pin to known-good versions in Dockerfile; update deliberately after reviewing changelogs
- Run `openclaw security audit --deep` after every version upgrade

## 9. Checklist Summary

Before go-live and after any config change:

- [ ] Gateway bound to loopback only
- [ ] Token auth enabled
- [ ] DM scope appropriate for user count
- [ ] Pairing codes not pre-generated
- [ ] Telegram allowlist populated
- [ ] No `tools.elevated` in any agent profile
- [ ] `workspaceAccess` set to minimum needed
- [ ] Tool profile is `strict` or `minimal`
- [ ] No untrusted plugins enabled
- [ ] OpenClaw version >= 2026.2.21 (patches critical advisories)
- [ ] `openclaw security audit --deep` passes clean
