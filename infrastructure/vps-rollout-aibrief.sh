#!/usr/bin/env bash
# Update cldw_Setup on VPS, sync AI Daily Brief assets, restart services, and validate health.
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/root/openclaw-project}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/root/openclaw}"
OPENCLAW_CFG="${OPENCLAW_CFG:-/root/.openclaw}"
BRANCH="${BRANCH:-main}"
WAIT_ATTEMPTS="${WAIT_ATTEMPTS:-18}"
WAIT_SECONDS="${WAIT_SECONDS:-10}"

log() {
  printf '[aibrief-rollout] %s\n' "$*"
}

require_file() {
  local path="$1"
  if [ ! -f "$path" ]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
}

log "Syncing repository to origin/${BRANCH}"
cd "$PROJECT_DIR"
git fetch origin
git checkout "$BRANCH"
git reset --hard "origin/${BRANCH}"
CURRENT_REF="$(git rev-parse --short HEAD)"
log "Using project ref: ${CURRENT_REF}"

log "Syncing AI Daily Brief config and skill assets"
mkdir -p \
  "$OPENCLAW_CFG/workspace/logs"

cp "$PROJECT_DIR/openclaw/config/AGENTS.md" "$OPENCLAW_CFG/AGENTS.md"
cp "$PROJECT_DIR/openclaw/config/SOUL.md" "$OPENCLAW_CFG/SOUL.md"
cp "$PROJECT_DIR/openclaw/config/CRON.md" "$OPENCLAW_CFG/CRON.md"
cp "$PROJECT_DIR/openclaw/config/HEARTBEAT.md" "$OPENCLAW_CFG/HEARTBEAT.md"
# Sync all skills recursively to keep alias commands current.
if [ -d "$PROJECT_DIR/openclaw/skills" ]; then
  while IFS= read -r -d '' skill_file; do
    rel_path="${skill_file#$PROJECT_DIR/openclaw/skills/}"
    mkdir -p "$(dirname "$OPENCLAW_CFG/skills/$rel_path")"
    cp "$skill_file" "$OPENCLAW_CFG/skills/$rel_path"
  done < <(find "$PROJECT_DIR/openclaw/skills" -type f -print0)
fi

# Remove deprecated alias skill folders to avoid confusing/duplicate command surfaces.
for deprecated in \
  aibrief \
  aibrief_morning \
  aibrief_evening \
  aibrief_top5 \
  aibrief_builder \
  aibrief_watchlist \
  aibrief_status; do
  rm -rf "$OPENCLAW_CFG/skills/$deprecated"
done
bash "$PROJECT_DIR/infrastructure/merge-ai-brief-state.sh" \
  "$PROJECT_DIR/openclaw/workspace/logs/ai-brief-state.json" \
  "$OPENCLAW_CFG/workspace/logs/ai-brief-state.json"

require_file "$OPENCLAW_CFG/openclaw.json"
require_file "$OPENCLAW_CFG/openclaw-config.json"

log "Aligning ownership with container runtime user"
OC_UID="$(docker compose -f "$OPENCLAW_DIR/docker-compose.yml" run --rm --no-deps --entrypoint sh openclaw-gateway -c 'id -u openclaw' | tr -d '\r' | tail -n 1)"
OC_GID="$(docker compose -f "$OPENCLAW_DIR/docker-compose.yml" run --rm --no-deps --entrypoint sh openclaw-gateway -c 'id -g openclaw' | tr -d '\r' | tail -n 1)"
if ! [[ "$OC_UID" =~ ^[0-9]+$ ]] || ! [[ "$OC_GID" =~ ^[0-9]+$ ]]; then
  echo "Failed to resolve openclaw uid/gid from image (uid='${OC_UID}' gid='${OC_GID}')." >&2
  exit 1
fi
chown -R "${OC_UID}:${OC_GID}" "$OPENCLAW_CFG"
chmod 600 "$OPENCLAW_CFG/openclaw.json" "$OPENCLAW_CFG/openclaw-config.json"

log "Syncing runtime envs"
/usr/local/sbin/sync-sentinel-env.sh
/usr/local/sbin/sync-openclaw-config.sh

log "Restarting services"
cd "$OPENCLAW_DIR"
docker compose up -d --force-recreate
systemctl daemon-reload
systemctl restart sentinel

log "Waiting for OpenClaw gateway health"
for i in $(seq 1 "$WAIT_ATTEMPTS"); do
  HS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' openclaw-openclaw-gateway-1 2>/dev/null || echo unknown)"
  log "attempt ${i}/${WAIT_ATTEMPTS}: gateway health=${HS}"
  if [ "$HS" = "healthy" ]; then
    break
  fi
  sleep "$WAIT_SECONDS"
done

log "Final health check"
"$PROJECT_DIR/infrastructure/health-check.sh"

log "Rollout complete for ref ${CURRENT_REF}."
log "Telegram smoke test: send /ai_daily_brief status then /ai_daily_brief top5 (or /ai_daily_brief_top5 compatibility alias)."
log "Set/update channel routing: $PROJECT_DIR/infrastructure/set-aibrief-output-channel.sh @dandailybriefAI"
log "Optional local test: $PROJECT_DIR/infrastructure/aibrief-smoke-test.sh"
