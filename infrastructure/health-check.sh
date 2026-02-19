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
        ((PASS++))
    else
        echo "[FAIL] $name"
        ((FAIL++))
    fi
}

warn() {
    local name="$1"
    echo "[WARN] $name"
    ((WARN++))
}

echo "=== OpenClaw + Sentinel Health Check ==="
echo "Date: $(date)"
echo ""

# 1. Docker running
docker info &>/dev/null
check "Docker daemon running" $?

# 2. OpenClaw container running
OPENCLAW_STATUS=$(docker inspect -f '{{.State.Running}}' openclaw-openclaw-gateway-1 2>/dev/null || echo "false")
if [ "$OPENCLAW_STATUS" = "true" ]; then
    check "OpenClaw container running" 0
else
    check "OpenClaw container running" 1
fi

# 3. OpenClaw HTTP response
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18789/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "000" ]; then
    check "OpenClaw HTTP reachable (status: $HTTP_CODE)" 0
else
    check "OpenClaw HTTP reachable" 1
fi

# 4. Sentinel service running
systemctl is-active sentinel &>/dev/null
check "Sentinel service running" $?

# 5. UFW active
ufw status | grep -q "Status: active"
check "UFW firewall active" $?

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
LATEST_BACKUP=$(ls -t /root/backups/openclaw-*.tar.gz 2>/dev/null | head -1)
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
