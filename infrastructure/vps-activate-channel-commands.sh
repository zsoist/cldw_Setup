#!/usr/bin/env bash
# VPS activation script for AI Daily Brief channel commands + v3 improvements.
#
# What this does:
#   1. Pulls the latest config branch onto the VPS
#   2. Guides through BotFather privacy mode setup (manual step, prompted)
#   3. Discovers and registers the supergroup chat ID
#   4. Registers OPENCLAW_TELEGRAM_INTERACTIVE_CHATS in .env
#   5. Runs full vps-rollout-aibrief.sh (syncs configs, merges state v3, restarts services)
#   6. Runs aibrief-smoke-test.sh and prints final report
#
# Usage (run as root on VPS):
#   bash /root/openclaw-project/infrastructure/vps-activate-channel-commands.sh
#
# Optional env overrides:
#   BRANCH=main                                 (default)
#   PROJECT_DIR=/root/openclaw-project          (default)
#   OPENCLAW_DIR=/root/openclaw                 (default)
#   ENV_FILE=/root/openclaw/.env                (default)
#   SKIP_GIT=1                                  skip git pull (use local state)
#   SKIP_BOTFATHER_PROMPT=1                     skip the BotFather interactive prompt
#   SUPERGROUP_CHAT_ID=<id>                     set chat ID directly (skip discovery)
#   DRY_RUN=1                                   print what would change without writing

set -euo pipefail

BRANCH="${BRANCH:-main}"
PROJECT_DIR="${PROJECT_DIR:-/root/openclaw-project}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/root/openclaw}"
ENV_FILE="${ENV_FILE:-/root/openclaw/.env}"
SKIP_GIT="${SKIP_GIT:-0}"
SKIP_BOTFATHER_PROMPT="${SKIP_BOTFATHER_PROMPT:-0}"
SUPERGROUP_CHAT_ID="${SUPERGROUP_CHAT_ID:-}"
DRY_RUN="${DRY_RUN:-0}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { printf "${BOLD}[channel-activate]${NC} %s\n" "$*"; }
ok()    { printf "${GREEN}[OK]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[WARN]${NC} %s\n" "$*"; }
fail()  { printf "${RED}[FAIL]${NC} %s\n" "$*" >&2; }
step()  { printf "\n${BOLD}━━━ %s ━━━${NC}\n" "$*"; }
dryrun(){ [ "$DRY_RUN" = "1" ] && printf "${YELLOW}[DRY-RUN]${NC} would: %s\n" "$*" || true; }

# ─── Step 0: Preflight ───────────────────────────────────────────────────────
step "0/6  Preflight"

if [ "$(id -u)" -ne 0 ]; then
  fail "Must run as root (sudo -i or SSH as root)"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  fail "Env file not found: $ENV_FILE"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  fail "docker not found — is Docker installed?"
  exit 1
fi
ok "Preflight passed"

# ─── Step 1: Pull latest branch ──────────────────────────────────────────────
step "1/6  Pull branch: ${BRANCH}"

if [ "$SKIP_GIT" = "1" ]; then
  warn "SKIP_GIT=1 — skipping git pull, using local working tree"
else
  cd "$PROJECT_DIR"
  git fetch origin
  if git ls-remote --heads origin "$BRANCH" | grep -q "$BRANCH"; then
    git checkout "$BRANCH"
    git reset --hard "origin/${BRANCH}"
    ok "Pulled $(git rev-parse --short HEAD) from origin/${BRANCH}"
  else
    # Branch not on remote yet — try local-only checkout
    if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
      git checkout "$BRANCH"
      warn "Branch ${BRANCH} exists locally only — remote not found"
    else
      fail "Branch ${BRANCH} not found locally or on remote. Ensure the branch was pushed."
      exit 1
    fi
  fi
fi

# ─── Step 2: BotFather privacy mode ──────────────────────────────────────────
step "2/6  BotFather privacy mode"

cat <<'MSG'
Telegram bots have privacy mode ON by default.
In this mode, bots only receive commands addressed by name:
  /command@BotName arg

You have two options:

  Option A — Disable privacy mode (recommended for a dedicated AI brief supergroup):
    ✓ Users can type /ai_daily_brief status  (no @botname needed)
    ✓ Best UX for a private group you control
    ✗ Bot receives ALL group messages (more Telegram API traffic)

  Option B — Keep privacy mode ON (default):
    ✓ Bot receives less traffic
    ✗ Users MUST type /ai_daily_brief@MangenkyoBot status
    ✓ @BotName suffix is stripped automatically by the normalizer

  To disable via BotFather (Option A):
    1. Open Telegram → message @BotFather
    2. Send /setprivacy
    3. Select your OpenClaw bot
    4. Select "Disable"

MSG

if [ "$SKIP_BOTFATHER_PROMPT" = "1" ]; then
  warn "SKIP_BOTFATHER_PROMPT=1 — skipping BotFather confirmation prompt"
  BOTFATHER_DONE="y"
else
  printf "Have you configured BotFather privacy mode? (y = yes / n = skip for now): "
  read -r BOTFATHER_DONE
fi

if [[ "${BOTFATHER_DONE:-n}" =~ ^[Yy]$ ]]; then
  ok "BotFather privacy mode step confirmed"
else
  warn "BotFather step skipped — channel commands will require /command@MangenkyoBot format"
fi

# ─── Step 3: Supergroup chat ID discovery ────────────────────────────────────
step "3/6  Supergroup chat ID"

TG_TOKEN="$(grep '^OPENCLAW_TELEGRAM_TOKEN=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//' || true)"
if [ -z "$TG_TOKEN" ]; then
  TG_TOKEN="$(grep '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//' || true)"
fi

if [ -z "$TG_TOKEN" ] || [[ "$TG_TOKEN" == REPLACE_* ]]; then
  fail "OPENCLAW_TELEGRAM_TOKEN not set in $ENV_FILE — cannot discover chat ID"
  exit 1
fi

if [ -z "$SUPERGROUP_CHAT_ID" ]; then
  info "Fetching recent updates from Telegram to discover chat IDs..."
  info "Make sure you (or someone) has sent a message in the target supergroup after adding the bot."
  echo ""

  CHATS_FOUND="$(curl -s "https://api.telegram.org/bot${TG_TOKEN}/getUpdates" | python3 -c "
import json, sys
data = json.load(sys.stdin)
seen = set()
for u in (data.get('result') or []):
    for key in ('message', 'channel_post', 'my_chat_member', 'chat_member'):
        msg = u.get(key) or {}
        chat = msg.get('chat', {})
        cid = chat.get('id')
        if cid and cid not in seen:
            seen.add(cid)
            ctype = chat.get('type', '?')
            ctitle = chat.get('title', chat.get('username', ''))
            print(f'  chat_id={cid}  type={ctype}  name={ctitle}')
" 2>/dev/null || true)"

  if [ -n "$CHATS_FOUND" ]; then
    echo "Chats found in recent Telegram updates:"
    echo "$CHATS_FOUND"
    echo ""
  else
    warn "No recent chat updates found. Send a message in your supergroup first, then rerun."
    warn "Or set SUPERGROUP_CHAT_ID=<id> directly and rerun."
  fi

  printf "Enter the supergroup chat ID to register (or leave blank to skip): "
  read -r SUPERGROUP_CHAT_ID_INPUT
  SUPERGROUP_CHAT_ID="$(printf '%s' "${SUPERGROUP_CHAT_ID_INPUT:-}" | tr -d '[:space:]')"
fi

if [ -n "$SUPERGROUP_CHAT_ID" ]; then
  # Validate format: numeric, optionally prefixed with -100
  if [[ "$SUPERGROUP_CHAT_ID" =~ ^-100[0-9]{6,}$ ]] || \
     [[ "$SUPERGROUP_CHAT_ID" =~ ^-[0-9]{6,}$ ]] || \
     [[ "$SUPERGROUP_CHAT_ID" =~ ^[0-9]{6,}$ ]]; then
    ok "Chat ID format valid: ${SUPERGROUP_CHAT_ID}"
  else
    fail "Chat ID '${SUPERGROUP_CHAT_ID}' looks invalid. Expected numeric like -1001234567890"
    exit 1
  fi
else
  warn "No supergroup chat ID provided — skipping OPENCLAW_TELEGRAM_INTERACTIVE_CHATS setup"
  warn "Channel commands will remain DM-only. Re-run with SUPERGROUP_CHAT_ID=<id> to enable."
fi

# ─── Step 4: Write OPENCLAW_TELEGRAM_INTERACTIVE_CHATS to .env ───────────────
step "4/6  Register interactive chat in .env"

if [ -n "$SUPERGROUP_CHAT_ID" ]; then
  # Merge with any existing interactive chats (comma-separated)
  EXISTING_CHATS="$(grep '^OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | sed -E 's/[[:space:]]+$//' || true)"

  # Build merged list (deduplicated)
  MERGED_CHATS="$(python3 -c "
import re, sys
existing = sys.argv[1]
new_id   = sys.argv[2]
items = []
seen  = set()
for raw in re.split(r'[\s,]+', existing):
    v = raw.strip()
    if v and v not in seen:
        items.append(v)
        seen.add(v)
if new_id and new_id not in seen:
    items.append(new_id)
print(','.join(items))
" "$EXISTING_CHATS" "$SUPERGROUP_CHAT_ID")"

  if [ "$DRY_RUN" = "1" ]; then
    dryrun "write OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=${MERGED_CHATS} to ${ENV_FILE}"
  else
    # Atomic update: remove old line, append new
    sed -i '/^OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=/d' "$ENV_FILE"
    printf 'OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=%s\n' "$MERGED_CHATS" >> "$ENV_FILE"
    ok "Wrote OPENCLAW_TELEGRAM_INTERACTIVE_CHATS=${MERGED_CHATS}"
  fi
else
  info "Skipped — no chat ID registered"
fi

# ─── Step 5: Full rollout ─────────────────────────────────────────────────────
step "5/6  Run vps-rollout-aibrief.sh"

ROLLOUT_SCRIPT="${PROJECT_DIR}/infrastructure/vps-rollout-aibrief.sh"
if [ ! -x "$ROLLOUT_SCRIPT" ]; then
  chmod +x "$ROLLOUT_SCRIPT"
fi

if [ "$DRY_RUN" = "1" ]; then
  dryrun "BRANCH=${BRANCH} bash ${ROLLOUT_SCRIPT}"
else
  BRANCH="$BRANCH" SKIP_GIT=1 bash "$ROLLOUT_SCRIPT"
fi

# ─── Step 6: Smoke test ───────────────────────────────────────────────────────
step "6/6  Smoke test"

SMOKE_SCRIPT="${PROJECT_DIR}/infrastructure/aibrief-smoke-test.sh"
if [ ! -x "$SMOKE_SCRIPT" ]; then
  chmod +x "$SMOKE_SCRIPT"
fi

if [ "$DRY_RUN" = "1" ]; then
  dryrun "bash ${SMOKE_SCRIPT}"
else
  bash "$SMOKE_SCRIPT" || SMOKE_EXIT=$?
  if [ "${SMOKE_EXIT:-0}" -ne 0 ]; then
    fail "Smoke test reported failures — check output above"
  else
    ok "Smoke test passed"
  fi
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
step "Done"

cat <<MSG

${BOLD}Channel command verification steps:${NC}

  1. Go to your registered supergroup on Telegram.

  2. If you disabled BotFather privacy mode (Option A):
       /ai_daily_brief status

  3. If privacy mode is still ON (Option B):
       /ai_daily_brief@MangenkyoBot status

  4. Expected response: status diagnostics with system model info block.

${BOLD}New commands available:${NC}
  /ai_daily_brief help                        — full command reference
  /ai_daily_brief watchlist add "mistral ai"  — add to watchlist
  /ai_daily_brief watchlist remove "topic"    — remove from watchlist
  /ai_daily_brief history 5                   — last 5 runs
  /ai_daily_brief diff                        — story delta between last 2 runs
  /ai_daily_brief feedback <run_id> 4 great   — rate a brief

${BOLD}If commands are still silent in supergroup:${NC}
  1. Confirm bot is a member or admin of the supergroup.
  2. Send any message in the group so Telegram delivers updates.
  3. Check BotFather privacy mode: /mybots → Bot Settings → Group Privacy.
  4. Re-run smoke test: ${SMOKE_SCRIPT}
  5. See: docs/TROUBLESHOOTING.md → "Channel commands not working"

${BOLD}Brave provider health probe:${NC}
  Probes automatically at 08:00, 14:00, 20:00 COT via heartbeat (job 15).
  Check status: /ai_daily_brief status → "Brave LLM Context" section.

MSG
