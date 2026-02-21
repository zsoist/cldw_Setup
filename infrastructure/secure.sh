#!/usr/bin/env bash
# Security hardening script for Hetzner CPX22
# Run as root on first VPS setup
set -euo pipefail

echo "=== [1/6] System update ==="
apt-get update && apt-get upgrade -y

echo "=== [2/6] Install essentials ==="
apt-get install -y ufw fail2ban curl git ca-certificates unattended-upgrades

echo "=== [3/6] Configure UFW firewall ==="
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
# Do NOT open 18789 — access via SSH tunnel only
echo "y" | ufw enable
ufw status verbose

echo "=== [4/6] Configure fail2ban ==="
cat > /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
EOF
systemctl enable fail2ban
systemctl restart fail2ban

echo "=== [5/6] SSH hardening ==="
# Disable password auth (SSH key only)
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/#PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config

SSH_SERVICE=""
if systemctl cat ssh >/dev/null 2>&1; then
    SSH_SERVICE="ssh"
elif systemctl cat sshd >/dev/null 2>&1; then
    SSH_SERVICE="sshd"
else
    echo "Error: could not find ssh.service or sshd.service"
    exit 1
fi

if ! sshd -t; then
    echo "Error: sshd configuration validation failed. Aborting restart."
    exit 1
fi

systemctl restart "$SSH_SERVICE"

echo "=== [6/6] Enable automatic security updates ==="
dpkg-reconfigure -plow unattended-upgrades

echo ""
echo "Security hardening complete."
echo "   - UFW: active (SSH only)"
echo "   - fail2ban: active (3 attempts, 1h ban)"
echo "   - SSH: key-only auth"
echo "   - Auto-updates: enabled"
