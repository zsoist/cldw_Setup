#!/usr/bin/env bash
# System health verification script
# Run manually or via cron to check overall system status
set -euo pipefail

PASS=0
FAIL=0
WARN=0

check() {
    local name="$1"
    local result="$2"
    if [ "$result" -eq 0 ]; then
        echo "[PASS] $name"
        PASS=$((PASS + 1))
    else
        echo "[FAIL] $name"
        FAIL=$((FAIL + 1))
    fi
}

warn() {
    local name="$1"
    echo "[WARN] $name"
    WARN=$((WARN + 1))
}

echo "=== OpenClaw + Sentinel Health Check ==="
echo "Date: $(date)"
echo ""

# 1. Docker running
if docker info &>/dev/null; then
    check "Docker daemon running" 0
else
    check "Docker daemon running" 1
fi

# 2. OpenClaw container running
OPENCLAW_STATUS=$(docker inspect -f '{{.State.Running}}' openclaw-openclaw-gateway-1 2>/dev/null || echo "false")
if [ "$OPENCLAW_STATUS" = "true" ]; then
    check "OpenClaw container running" 0
else
    check "OpenClaw container running" 1
fi

# 3. OpenClaw gateway health (WebSocket gateway, not HTTP root)
OPENCLAW_HEALTH=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' openclaw-openclaw-gateway-1 2>/dev/null || echo "unknown")
if [ "$OPENCLAW_HEALTH" = "healthy" ]; then
    check "OpenClaw gateway healthy" 0
else
    check "OpenClaw gateway healthy (status: $OPENCLAW_HEALTH)" 1
fi

# 4. Sentinel service running
if systemctl is-active sentinel &>/dev/null; then
    check "Sentinel service running" 0
else
    check "Sentinel service running" 1
fi

# 5. UFW active
if ufw status | grep -q "Status: active"; then
    check "UFW firewall active" 0
else
    check "UFW firewall active" 1
fi

# 6. Disk space (warn if >80%)
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 90 ]; then
    check "Disk usage under 90% (currently ${DISK_USAGE}%)" 1
elif [ "$DISK_USAGE" -gt 80 ]; then
    warn "Disk usage at ${DISK_USAGE}% (threshold: 80%)"
    check "Disk usage under 90%" 0
else
    check "Disk usage healthy (${DISK_USAGE}%)" 0
fi

# 7. Memory (warn if >85%)
MEM_USAGE=$(free | awk '/Mem:/ {printf("%.0f", $3/$2 * 100)}')
if [ "$MEM_USAGE" -gt 90 ]; then
    check "Memory usage under 90% (currently ${MEM_USAGE}%)" 1
elif [ "$MEM_USAGE" -gt 85 ]; then
    warn "Memory usage at ${MEM_USAGE}% (threshold: 85%)"
    check "Memory usage under 90%" 0
else
    check "Memory usage healthy (${MEM_USAGE}%)" 0
fi

# 8. Recent backups exist
shopt -s nullglob
BACKUPS=(/root/backups/openclaw-*.tar.gz)
shopt -u nullglob
LATEST_BACKUP=""
if [ "${#BACKUPS[@]}" -gt 0 ]; then
    LATEST_BACKUP=$(ls -t "${BACKUPS[@]}" | head -1)
fi
if [ -n "$LATEST_BACKUP" ]; then
    BACKUP_AGE=$(( ($(date +%s) - $(stat -c %Y "$LATEST_BACKUP")) / 86400 ))
    if [ "$BACKUP_AGE" -gt 7 ]; then
        warn "Latest backup is ${BACKUP_AGE} days old"
    fi
    check "Backup exists" 0
else
    check "Backup exists" 1
fi

echo ""
echo "=== Summary: $PASS passed, $FAIL failed, $WARN warnings ==="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
