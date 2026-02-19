#!/usr/bin/env bash
# Full deployment script — run on the VPS after scp'ing the project
set -euo pipefail

PROJECT_DIR="/root/openclaw-project"
OPENCLAW_DIR="/root/openclaw"
SENTINEL_DIR="/opt/sentinel"

echo "=== [1/8] Install Docker ==="
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
docker --version
docker compose version

echo "=== [2/8] Clone OpenClaw ==="
if [ ! -d "$OPENCLAW_DIR" ]; then
    git clone https://github.com/openclaw/openclaw.git "$OPENCLAW_DIR"
fi
cd "$OPENCLAW_DIR"
git pull

echo "=== [3/8] Create persistent directories ==="
mkdir -p /root/.openclaw/workspace /root/.openclaw/skills /root/backups
chown -R 1000:1000 /root/.openclaw

echo "=== [4/8] Copy OpenClaw config files ==="
cp "$PROJECT_DIR/openclaw/config/SOUL.md" /root/.openclaw/
cp "$PROJECT_DIR/openclaw/config/USER.md" /root/.openclaw/
cp "$PROJECT_DIR/openclaw/config/AGENTS.md" /root/.openclaw/
cp "$PROJECT_DIR/openclaw/config/HEARTBEAT.md" /root/.openclaw/
cp "$PROJECT_DIR/openclaw/config/MEMORY.md" /root/.openclaw/
cp -r "$PROJECT_DIR/openclaw/skills/"* /root/.openclaw/skills/ 2>/dev/null || true

echo "=== [5/8] Copy infrastructure files ==="
cp "$PROJECT_DIR/infrastructure/Dockerfile" "$OPENCLAW_DIR/"
cp "$PROJECT_DIR/infrastructure/docker-compose.yml" "$OPENCLAW_DIR/"

echo "=== [6/8] Setup Sentinel ==="
mkdir -p "$SENTINEL_DIR"
cp "$PROJECT_DIR/sentinel/"*.py "$SENTINEL_DIR/"
cp "$PROJECT_DIR/sentinel/requirements.txt" "$SENTINEL_DIR/"
cp "$PROJECT_DIR/sentinel/sentinel.service" /etc/systemd/system/

# Create Python venv for Sentinel
python3 -m venv "$SENTINEL_DIR/venv"
"$SENTINEL_DIR/venv/bin/pip" install -r "$SENTINEL_DIR/requirements.txt"

echo "=== [7/8] Build OpenClaw Docker image ==="
cd "$OPENCLAW_DIR"
# Copy .env (must be created manually with secrets)
if [ ! -f .env ]; then
    cp "$PROJECT_DIR/infrastructure/env.template" .env
    echo ""
    echo "IMPORTANT: Edit /root/openclaw/.env and fill in all secrets before starting!"
    echo "   Run: nano /root/openclaw/.env"
    echo ""
fi
docker compose build

echo "=== [8/8] Enable Sentinel service ==="
systemctl daemon-reload
systemctl enable sentinel

echo ""
echo "Deployment staged. NOT yet running."
echo ""
echo "Next steps:"
echo "  1. Edit secrets:    nano /root/openclaw/.env"
echo "  2. Start OpenClaw:  cd /root/openclaw && docker compose up -d"
echo "  3. Start Sentinel:  systemctl start sentinel"
echo "  4. SSH tunnel:      ssh -N -L 18789:127.0.0.1:18789 root@YOUR_VPS_IP"
echo "  5. Open browser:    http://127.0.0.1:18789/"
