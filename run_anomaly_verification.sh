#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$HOME/ONC/hydrophone-labeling-verification-app"
VENV_DIR="$HOME/ONC/hydrophonedashboard/venv"
PYTHON_BIN="$VENV_DIR/bin/python"
MOUNT_DIR="$HOME/whalestor_mount"
DATA_DIR="$MOUNT_DIR/HydrophoneData/CIOOS_Anomaly_detection_work/daily-data-pipeline"
PREDICTIONS_FILE="$DATA_DIR/2026-04-08/predictions.json"
SSHFS_BIN="$HOME/.local/bin/sshfs"
SSHFS_SOURCE="sbialek@142.104.198.24:/home/sbialek/whalestor_mount"
PORT=18051
SCREEN_NAME="verify"
LOG_DIR="$HOME/ONC/verification_logs"
LOCK_FILE="$HOME/.cache/anomaly-verification.lock"

mkdir -p "$LOG_DIR" "$(dirname "$LOCK_FILE")" "$MOUNT_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

timestamp() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

mount_is_healthy() {
    mountpoint -q "$MOUNT_DIR" &&
        timeout 20 test -r "$PREDICTIONS_FILE"
}

if ! mount_is_healthy; then
    if mountpoint -q "$MOUNT_DIR"; then
        fusermount3 -uz "$MOUNT_DIR" || true
    fi

    echo "[$(timestamp)] mounting Whalestor proxy at $MOUNT_DIR"
    "$SSHFS_BIN" "$SSHFS_SOURCE" "$MOUNT_DIR" \
        -o reconnect \
        -o ServerAliveInterval=15 \
        -o ServerAliveCountMax=3 \
        -o ConnectTimeout=10 \
        -o BatchMode=yes \
        -o StrictHostKeyChecking=yes \
        -o idmap=user

    if ! mount_is_healthy; then
        echo "[$(timestamp)] Whalestor proxy mount is not readable" >&2
        exit 1
    fi
fi

screen_session() {
    screen -ls 2>/dev/null |
        awk -v name="$SCREEN_NAME" '$1 ~ ("^[0-9]+[.]" name "$") { print $1; exit }'
}

http_is_healthy() {
    "$PYTHON_BIN" -c \
        'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=20).read(1)' \
        "http://127.0.0.1:$PORT/"
}

session="$(screen_session || true)"
if [[ -n "$session" ]] &&
    http_is_healthy >/dev/null 2>&1; then
    exit 0
fi

if [[ -n "$session" ]]; then
    echo "[$(timestamp)] restarting unhealthy screen session $session"
    screen -S "$session" -X quit || true
    for _ in $(seq 1 10); do
        ss -ltn | grep -q ":$PORT " || break
        sleep 1
    done
fi

if ss -ltn | grep -q ":$PORT "; then
    echo "[$(timestamp)] port $PORT is occupied outside screen $SCREEN_NAME" >&2
    exit 1
fi

log_file="$LOG_DIR/anomaly-verify-$(date -u +%Y%m%dT%H%M%SZ).log"
echo "[$(timestamp)] starting anomaly verifier in screen $SCREEN_NAME"
TERM=xterm screen -dmS "$SCREEN_NAME" -L -Logfile "$log_file" \
    "$PYTHON_BIN" "$APP_DIR/run.py" \
    --host 0.0.0.0 \
    --port "$PORT" \
    --data-dir "$DATA_DIR" \
    --mode verify

for _ in $(seq 1 20); do
    if http_is_healthy >/dev/null 2>&1; then
        echo "[$(timestamp)] anomaly verifier is healthy on port $PORT"
        exit 0
    fi
    sleep 1
done

echo "[$(timestamp)] anomaly verifier failed its startup health check" >&2
exit 1
