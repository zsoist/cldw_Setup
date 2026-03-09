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

# 3b. HTTP fallback endpoint (probe inside container; host curl is not reliable on this bind setup)
HTTP_FALLBACK_CODE=$(docker exec openclaw-openclaw-gateway-1 sh -lc "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18789/" 2>/dev/null || true)
if [ "$HTTP_FALLBACK_CODE" = "200" ] || [ "$HTTP_FALLBACK_CODE" = "301" ] || [ "$HTTP_FALLBACK_CODE" = "302" ] || [ "$HTTP_FALLBACK_CODE" = "401" ]; then
    check "OpenClaw HTTP fallback endpoint reachable in container (status: $HTTP_FALLBACK_CODE)" 0
else
    warn "OpenClaw HTTP fallback endpoint not reachable in container (status: ${HTTP_FALLBACK_CODE:-000})"
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

# 5b. UFW has explicit SSH allow rule
if ufw status numbered | grep -Eq '22/tcp.*ALLOW'; then
    check "UFW SSH allow rule present" 0
else
    check "UFW SSH allow rule present" 1
fi

# 5c. fail2ban sshd jail active
if fail2ban-client status sshd 2>/dev/null | grep -q "Status for the jail: sshd"; then
    check "fail2ban sshd jail active" 0
else
    check "fail2ban sshd jail active" 1
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

# 9. SSH authorized_keys permissions
if [ -f /root/.ssh/authorized_keys ]; then
    AUTH_KEYS_PERM=$(stat -c %a /root/.ssh/authorized_keys)
    if [ "$AUTH_KEYS_PERM" = "600" ]; then
        check "SSH authorized_keys permissions (600)" 0
    else
        check "SSH authorized_keys permissions (currently $AUTH_KEYS_PERM)" 1
    fi
else
    warn "SSH authorized_keys not found at /root/.ssh/authorized_keys"
fi

# 10. OpenClaw config readability for runtime user
if [ -f /root/.openclaw/openclaw.json ]; then
    OPENCLAW_CFG_PERM=$(stat -c %a /root/.openclaw/openclaw.json)
    if docker exec openclaw-openclaw-gateway-1 sh -lc 'test -r /home/node/.openclaw/openclaw.json' 2>/dev/null; then
        check "OpenClaw config readable by runtime user (host mode $OPENCLAW_CFG_PERM)" 0
    else
        check "OpenClaw config readable by runtime user (host mode $OPENCLAW_CFG_PERM)" 1
    fi
else
    check "OpenClaw config file exists" 1
fi

# 11. API cost tracking artifacts
if [ -f /var/log/sentinel/api-cost-summary.json ]; then
    check "Sentinel API cost summary present" 0
else
    warn "Sentinel API cost summary missing (/var/log/sentinel/api-cost-summary.json)"
fi

if [ -f /root/.openclaw/workspace/logs/api-cost-rollup.json ]; then
    check "Unified API cost rollup present" 0
else
    warn "Unified API cost rollup missing (/root/.openclaw/workspace/logs/api-cost-rollup.json)"
fi

echo ""
echo "=== Summary: $PASS passed, $FAIL failed, $WARN warnings ==="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
