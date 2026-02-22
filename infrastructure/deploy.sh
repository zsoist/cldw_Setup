#!/usr/bin/env bash
# Full deployment script — run on the VPS after scp'ing the project
set -euo pipefail

PROJECT_DIR="/root/openclaw-project"
OPENCLAW_DIR="/root/openclaw"
SENTINEL_DIR="/opt/sentinel"
OPENCLAW_CONFIG="/root/.openclaw"
OPENCLAW_REPO="https://github.com/openclaw/openclaw.git"
OPENCLAW_REF="${OPENCLAW_REF:-58f7b7638a997ebb7da3a4877e6c64c40bc20e7e}"
PROJECT_EXPECTED_REF="${PROJECT_EXPECTED_REF:-}"

hash_file() {
    sha256sum "$1" | awk '{print $1}'
}

copy_checked() {
    local src="$1"
    local dest="$2"
    if [ ! -f "$src" ]; then
        echo "Missing source file: $src"
        exit 1
    fi
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    local src_hash dst_hash
    src_hash="$(hash_file "$src")"
    dst_hash="$(hash_file "$dest")"
    if [ "$src_hash" != "$dst_hash" ]; then
        echo "Checksum mismatch after copy: $src -> $dest"
        exit 1
    fi
}

echo "=== [1/9] Install Docker ==="
echo "Installing Python venv prerequisites..."
apt-get update
apt-get install -y python3 python3-venv

if [ ! -d "$PROJECT_DIR/.git" ]; then
    echo "Error: $PROJECT_DIR is not a git checkout. Clone the project first."
    exit 1
fi

PROJECT_HEAD="$(git -C "$PROJECT_DIR" rev-parse HEAD)"
if [ -n "$PROJECT_EXPECTED_REF" ] && [ "$PROJECT_HEAD" != "$PROJECT_EXPECTED_REF" ]; then
    echo "Error: project HEAD ($PROJECT_HEAD) does not match PROJECT_EXPECTED_REF ($PROJECT_EXPECTED_REF)."
    exit 1
fi

if ! git -C "$PROJECT_DIR" diff --quiet || ! git -C "$PROJECT_DIR" diff --cached --quiet; then
    echo "Error: deployment source has uncommitted changes at $PROJECT_DIR."
    echo "Commit/stash changes first or deploy a clean checkout."
    exit 1
fi

if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
docker --version
docker compose version

echo "=== [2/9] Clone OpenClaw (pinned ref: $OPENCLAW_REF) ==="
if [ ! -d "$OPENCLAW_DIR/.git" ]; then
    git clone "$OPENCLAW_REPO" "$OPENCLAW_DIR"
fi
cd "$OPENCLAW_DIR"
git fetch --tags origin
git checkout "$OPENCLAW_REF"

echo "=== [3/9] Create persistent directories ==="
mkdir -p "$OPENCLAW_CONFIG/workspace/personal/projects"
mkdir -p "$OPENCLAW_CONFIG/workspace/business/projects/active"
mkdir -p "$OPENCLAW_CONFIG/workspace/business/projects/archived"
mkdir -p "$OPENCLAW_CONFIG/workspace/outputs/summaries"
mkdir -p "$OPENCLAW_CONFIG/workspace/outputs/reports"
mkdir -p "$OPENCLAW_CONFIG/workspace/outputs/drafts"
mkdir -p "$OPENCLAW_CONFIG/workspace/outputs/exports"
mkdir -p "$OPENCLAW_CONFIG/workspace/logs"
mkdir -p "$OPENCLAW_CONFIG/skills"
mkdir -p "$OPENCLAW_CONFIG/agents/work"
mkdir -p "$OPENCLAW_CONFIG/agents/main/sessions"
mkdir -p "$OPENCLAW_CONFIG/credentials"
mkdir -p "$OPENCLAW_CONFIG/memory/weekly"
mkdir -p /root/backups

echo "=== [4/9] Copy OpenClaw config files (main agent) ==="
for f in SOUL.md USER.md AGENTS.md TOOLS.md HEARTBEAT.md MEMORY.md \
         IDENTITY.md BOOTSTRAP.md BOOT.md CRON.md CHANNELS.md SANDBOX.md; do
    copy_checked "$PROJECT_DIR/openclaw/config/$f" "$OPENCLAW_CONFIG/$f"
done
copy_checked "$PROJECT_DIR/openclaw/openclaw-config.json" "$OPENCLAW_CONFIG/openclaw-config.json"
copy_checked "$PROJECT_DIR/openclaw/openclaw-config.json" "$OPENCLAW_CONFIG/openclaw.json"

echo "=== [5/9] Copy work agent files ==="
for f in SOUL.md TOOLS.md USER.md MEMORY.md HEARTBEAT.md; do
    copy_checked "$PROJECT_DIR/openclaw/agents/work/$f" "$OPENCLAW_CONFIG/agents/work/$f"
done

echo "=== [6/9] Copy workspace content + skills ==="
copy_checked "$PROJECT_DIR/openclaw/workspace/personal/goals.md" "$OPENCLAW_CONFIG/workspace/personal/goals.md"
copy_checked "$PROJECT_DIR/openclaw/workspace/personal/routines.md" "$OPENCLAW_CONFIG/workspace/personal/routines.md"
copy_checked "$PROJECT_DIR/openclaw/workspace/business/goals-okrs.md" "$OPENCLAW_CONFIG/workspace/business/goals-okrs.md"
copy_checked "$PROJECT_DIR/openclaw/workspace/business/operating-rules.md" "$OPENCLAW_CONFIG/workspace/business/operating-rules.md"
copy_checked "$PROJECT_DIR/openclaw/workspace/logs/change-log.md" "$OPENCLAW_CONFIG/workspace/logs/change-log.md"
copy_checked "$PROJECT_DIR/openclaw/workspace/logs/cron-job-results.md" "$OPENCLAW_CONFIG/workspace/logs/cron-job-results.md"
copy_checked "$PROJECT_DIR/openclaw/workspace/logs/ai-brief-state.json" "$OPENCLAW_CONFIG/workspace/logs/ai-brief-state.json"
if [ -d "$PROJECT_DIR/openclaw/skills" ]; then
    while IFS= read -r -d '' skill_file; do
        rel_path="${skill_file#$PROJECT_DIR/openclaw/skills/}"
        copy_checked "$skill_file" "$OPENCLAW_CONFIG/skills/$rel_path"
    done < <(find "$PROJECT_DIR/openclaw/skills" -type f -print0)
fi

echo "=== [7/9] Copy infrastructure files + setup Sentinel ==="
copy_checked "$PROJECT_DIR/infrastructure/Dockerfile" "$OPENCLAW_DIR/Dockerfile"
copy_checked "$PROJECT_DIR/infrastructure/docker-compose.yml" "$OPENCLAW_DIR/docker-compose.yml"
copy_checked "$PROJECT_DIR/openclaw/openclaw-config.json" "$OPENCLAW_DIR/openclaw-config.json"

if ! id sentinel >/dev/null 2>&1; then
    useradd --system --home /opt/sentinel --shell /usr/sbin/nologin sentinel
fi
usermod -aG docker,adm sentinel

mkdir -p "$SENTINEL_DIR"
for f in config.py sentinel.py telegram_handler.py tools.py; do
    copy_checked "$PROJECT_DIR/sentinel/$f" "$SENTINEL_DIR/$f"
done
copy_checked "$PROJECT_DIR/sentinel/requirements.txt" "$SENTINEL_DIR/requirements.txt"
copy_checked "$PROJECT_DIR/sentinel/sentinel.service" "/etc/systemd/system/sentinel.service"
copy_checked "$PROJECT_DIR/infrastructure/sync-sentinel-env.sh" "/usr/local/sbin/sync-sentinel-env.sh"
copy_checked "$PROJECT_DIR/infrastructure/sync-openclaw-config.sh" "/usr/local/sbin/sync-openclaw-config.sh"
chmod 750 /usr/local/sbin/sync-sentinel-env.sh
chmod 750 /usr/local/sbin/sync-openclaw-config.sh
chown root:sentinel /usr/local/sbin/sync-sentinel-env.sh
chown root:root /usr/local/sbin/sync-openclaw-config.sh
mkdir -p /etc/sentinel /var/log/sentinel /var/backups/openclaw
chown root:sentinel /etc/sentinel
chmod 750 /etc/sentinel
chown -R sentinel:sentinel "$SENTINEL_DIR" /var/log/sentinel /var/backups/openclaw

# Create Python venv for Sentinel
python3 -m venv "$SENTINEL_DIR/venv"
"$SENTINEL_DIR/venv/bin/pip" install -r "$SENTINEL_DIR/requirements.txt"

echo "=== [8/9] Build OpenClaw Docker image ==="
cd "$OPENCLAW_DIR"
if [ ! -f .env ]; then
    cp "$PROJECT_DIR/infrastructure/env.template" .env
    echo ""
    echo "IMPORTANT: Edit /root/openclaw/.env and fill in all secrets before starting!"
    echo "   Run: nano /root/openclaw/.env"
    echo ""
fi
if ! grep -q '^OPENCLAW_REF=' .env; then
    echo "OPENCLAW_REF=$OPENCLAW_REF" >> .env
fi
docker compose build

echo "Aligning OpenClaw state directory ownership with container runtime user..."
OPENCLAW_UID="$(docker compose run --rm --no-deps --entrypoint sh openclaw-gateway -c 'id -u openclaw' | tr -d '\r' | tail -n 1)"
OPENCLAW_GID="$(docker compose run --rm --no-deps --entrypoint sh openclaw-gateway -c 'id -g openclaw' | tr -d '\r' | tail -n 1)"
if ! [[ "$OPENCLAW_UID" =~ ^[0-9]+$ ]] || ! [[ "$OPENCLAW_GID" =~ ^[0-9]+$ ]]; then
    echo "Error: failed to resolve OpenClaw runtime UID/GID (got uid='$OPENCLAW_UID', gid='$OPENCLAW_GID')."
    exit 1
fi

chown -R "${OPENCLAW_UID}:${OPENCLAW_GID}" "$OPENCLAW_CONFIG"
chmod 700 "$OPENCLAW_CONFIG"
chmod 600 "$OPENCLAW_CONFIG/openclaw.json" "$OPENCLAW_CONFIG/openclaw-config.json"

if [ -x /usr/local/sbin/sync-sentinel-env.sh ]; then
    /usr/local/sbin/sync-sentinel-env.sh || true
fi
if [ -x /usr/local/sbin/sync-openclaw-config.sh ]; then
    /usr/local/sbin/sync-openclaw-config.sh || true
fi

if grep -q 'REPLACE_WITH_VPS_IP' "$PROJECT_DIR/infrastructure/ssh-config-snippet"; then
    echo "WARNING: infrastructure/ssh-config-snippet still has REPLACE_WITH_VPS_IP."
fi

echo "=== [9/9] Enable Sentinel service ==="
systemctl daemon-reload
systemctl enable sentinel

echo ""
echo "Deployment staged. NOT yet running."
echo ""
SKILL_COUNT=0
if [ -d "$PROJECT_DIR/openclaw/skills" ]; then
    SKILL_COUNT="$(find "$PROJECT_DIR/openclaw/skills" -type f -name 'SKILL.md' | wc -l | tr -d ' ')"
fi
echo "Files deployed:"
echo "   OpenClaw:  pinned to $OPENCLAW_REF"
echo "   Config:    12 main agent files + openclaw-config.json"
echo "   Work:      5 work agent files (sandbox enabled)"
echo "   Workspace: personal/, business/, outputs/, logs/"
echo "   Skills:    ${SKILL_COUNT} skills (AI brief via /ai_daily_brief)"
echo "   Sentinel:  Python bot + systemd service"
echo ""
echo "Next steps:"
echo "  1. Edit secrets:    nano /root/openclaw/.env"
echo "  2. Validate secrets: /root/openclaw-project/infrastructure/validate-placeholders.sh /root/openclaw/.env"
echo "  3. Sync Sentinel env: /usr/local/sbin/sync-sentinel-env.sh"
echo "  4. Sync OpenClaw config: /usr/local/sbin/sync-openclaw-config.sh"
echo "  5. Start OpenClaw:  cd /root/openclaw && docker compose up -d"
echo "  6. Start Sentinel:  systemctl start sentinel"
echo "  7. SSH tunnel:      ssh -N -L 18789:127.0.0.1:18789 root@YOUR_VPS_IP"
echo "  8. Open browser:    http://127.0.0.1:18789/"
echo "  9. Run health check: /root/openclaw-project/infrastructure/health-check.sh"
echo " 10. AI brief smoke test: /root/openclaw-project/infrastructure/aibrief-smoke-test.sh"
echo " 11. Future config-only rollout: /root/openclaw-project/infrastructure/vps-rollout-aibrief.sh"
