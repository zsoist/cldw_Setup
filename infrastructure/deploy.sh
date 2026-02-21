#!/usr/bin/env bash
# Full deployment script — run on the VPS after scp'ing the project
set -euo pipefail

PROJECT_DIR="/root/openclaw-project"
OPENCLAW_DIR="/root/openclaw"
SENTINEL_DIR="/opt/sentinel"
OPENCLAW_CONFIG="/root/.openclaw"
OPENCLAW_REPO="https://github.com/openclaw/openclaw.git"
OPENCLAW_REF="${OPENCLAW_REF:-58f7b7638a997ebb7da3a4877e6c64c40bc20e7e}"

echo "=== [1/9] Install Docker ==="
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
mkdir -p "$OPENCLAW_CONFIG/memory/weekly"
mkdir -p /root/backups
chown -R 1000:1000 "$OPENCLAW_CONFIG"

echo "=== [4/9] Copy OpenClaw config files (main agent) ==="
for f in SOUL.md USER.md AGENTS.md TOOLS.md HEARTBEAT.md MEMORY.md \
         IDENTITY.md BOOTSTRAP.md BOOT.md CRON.md CHANNELS.md SANDBOX.md; do
    cp "$PROJECT_DIR/openclaw/config/$f" "$OPENCLAW_CONFIG/"
done
cp "$PROJECT_DIR/openclaw/openclaw-config.json" "$OPENCLAW_CONFIG/openclaw-config.json"

echo "=== [5/9] Copy work agent files ==="
for f in SOUL.md TOOLS.md USER.md MEMORY.md HEARTBEAT.md; do
    cp "$PROJECT_DIR/openclaw/agents/work/$f" "$OPENCLAW_CONFIG/agents/work/"
done

echo "=== [6/9] Copy workspace content + skills ==="
cp "$PROJECT_DIR/openclaw/workspace/personal/goals.md" "$OPENCLAW_CONFIG/workspace/personal/"
cp "$PROJECT_DIR/openclaw/workspace/personal/routines.md" "$OPENCLAW_CONFIG/workspace/personal/"
cp "$PROJECT_DIR/openclaw/workspace/business/goals-okrs.md" "$OPENCLAW_CONFIG/workspace/business/"
cp "$PROJECT_DIR/openclaw/workspace/business/operating-rules.md" "$OPENCLAW_CONFIG/workspace/business/"
cp "$PROJECT_DIR/openclaw/workspace/logs/change-log.md" "$OPENCLAW_CONFIG/workspace/logs/"
cp "$PROJECT_DIR/openclaw/workspace/logs/cron-job-results.md" "$OPENCLAW_CONFIG/workspace/logs/"
cp -r "$PROJECT_DIR/openclaw/skills/"* "$OPENCLAW_CONFIG/skills/" 2>/dev/null || true

echo "=== [7/9] Copy infrastructure files + setup Sentinel ==="
cp "$PROJECT_DIR/infrastructure/Dockerfile" "$OPENCLAW_DIR/"
cp "$PROJECT_DIR/infrastructure/docker-compose.yml" "$OPENCLAW_DIR/"
cp "$PROJECT_DIR/openclaw/openclaw-config.json" "$OPENCLAW_DIR/openclaw-config.json"

mkdir -p "$SENTINEL_DIR"
cp "$PROJECT_DIR/sentinel/"*.py "$SENTINEL_DIR/"
cp "$PROJECT_DIR/sentinel/requirements.txt" "$SENTINEL_DIR/"
cp "$PROJECT_DIR/sentinel/sentinel.service" /etc/systemd/system/

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

echo "=== [9/9] Enable Sentinel service ==="
systemctl daemon-reload
systemctl enable sentinel

echo ""
echo "Deployment staged. NOT yet running."
echo ""
echo "Files deployed:"
echo "   OpenClaw:  pinned to $OPENCLAW_REF"
echo "   Config:    12 main agent files + openclaw-config.json"
echo "   Work:      5 work agent files (sandbox enabled)"
echo "   Workspace: personal/, business/, outputs/, logs/"
echo "   Skills:    3 skills (daily-briefing, research, task-tracker)"
echo "   Sentinel:  Python bot + systemd service"
echo ""
echo "Next steps:"
echo "  1. Edit secrets:    nano /root/openclaw/.env"
echo "  2. Start OpenClaw:  cd /root/openclaw && docker compose up -d"
echo "  3. Start Sentinel:  systemctl start sentinel"
echo "  4. SSH tunnel:      ssh -N -L 18789:127.0.0.1:18789 root@YOUR_VPS_IP"
echo "  5. Open browser:    http://127.0.0.1:18789/"
echo "  6. Run health check: /root/openclaw-project/infrastructure/health-check.sh"
