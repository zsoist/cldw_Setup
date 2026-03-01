#!/usr/bin/env bash
# Safe OpenClaw config reload wrapper.
# Validates openclaw.json before sending SIGUSR1 to the gateway.
# Usage: /root/.openclaw/reload-config.sh
set -euo pipefail

CONFIG="/root/.openclaw/openclaw.json"

echo "[reload] Validating $CONFIG ..."

# 1. JSON syntax check
if ! python3 -c "import json; json.load(open('$CONFIG'))" 2>/dev/null; then
  echo "FATAL: $CONFIG is not valid JSON. Aborting reload."
  exit 1
fi

# 2. Required fields check
python3 -c "
import json, sys
c = json.load(open('$CONFIG'))
g = c.get('models',{}).get('providers',{}).get('google',{})
if not g.get('baseUrl'):
    print('FATAL: models.providers.google.baseUrl missing'); sys.exit(1)
models = g.get('models',[])
if not models:
    print('FATAL: models.providers.google.models is empty'); sys.exit(1)
for m in models:
    if not m.get('name') or not m.get('id'):
        print(f'FATAL: model missing name/id: {m}'); sys.exit(1)
# Check compaction mode is valid
comp = c.get('agents',{}).get('defaults',{}).get('compaction',{}).get('mode','default')
if comp not in ('default','safeguard'):
    print(f'FATAL: compaction.mode \"{comp}\" is invalid (must be default or safeguard)'); sys.exit(1)
print(f'Config OK: {len(models)} Google models, compaction={comp}')
"
if [ $? -ne 0 ]; then
  echo "[reload] Config validation failed. Aborting reload."
  exit 1
fi

# 3. Fix ownership (Edit tool resets to root:root)
chown sentinel:systemd-journal "$CONFIG"
chmod 640 "$CONFIG"
echo "[reload] Permissions fixed: sentinel:systemd-journal 640"

# 4. Send reload signal
docker kill --signal=SIGUSR1 openclaw-openclaw-gateway-1
echo "[reload] SIGUSR1 sent. Config reloaded successfully."
