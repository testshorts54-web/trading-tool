#!/usr/bin/env bash
# Restart predict_scan.py if its process is gone or its heartbeat is stale (copy of tools/price-alert/watchdog.sh).
#   while sleep 120; do /workspace/trading-tool/predict_watchdog.sh; done &
set -u
D=$(cd "$(dirname "$0")" && pwd); O=$D/out/predict; mkdir -p "$O"; PIDF=$O/scan.pid; INTERVAL=${INTERVAL:-300}; STALE=$((INTERVAL * 3 + 120))
pid=$(cat "$PIDF" 2>/dev/null || true)
alive=0; [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && grep -q predict_scan.py "/proc/$pid/cmdline" 2>/dev/null && alive=1
age=$(( $(date +%s) - $(stat -c %Y "$O/heartbeat" 2>/dev/null || echo 0) ))
if [ "$alive" = 1 ] && [ "$age" -le "$STALE" ]; then exit 0; fi
[ "$alive" = 1 ] && kill "$pid" 2>/dev/null && sleep 2
touch "$O/heartbeat"
nohup python3 "$D/predict_scan.py" --interval "$INTERVAL" >>"$O/scan.log" 2>&1 &
echo $! >"$PIDF"
echo "$(date '+%F %T %Z') restarted predict_scan.py pid $! (was alive=$alive, heartbeat age ${age}s)" >>"$O/watchdog.log"
