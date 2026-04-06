#!/usr/bin/env bash
#
# Launch the DB Viewer with an SSH tunnel to an EC2 PostgreSQL instance.
#
# Usage:
#   ./connect.sh                                    # uses env vars or prompts
#   ./connect.sh -k ~/.ssh/my-key.pem -h 3.14.15.92 -u ubuntu
#
# Environment variables (all optional, CLI flags take precedence):
#   EC2_SSH_KEY_PATH  -- path to .pem file
#   EC2_HOST          -- EC2 public IP or hostname
#   EC2_SSH_USER      -- SSH username (default: ubuntu)

set -euo pipefail

LOCAL_PORT=15432
REMOTE_PORT=5432
PG_USER="root"
PG_PASSWORD="example"
PG_DATABASE="postgres"
SSH_KEY="${EC2_SSH_KEY_PATH:-}"
EC2_HOST_VAL="${EC2_HOST:-}"
EC2_USER="${EC2_SSH_USER:-ubuntu}"

while getopts "k:h:u:p:P:d:" opt; do
    case $opt in
        k) SSH_KEY="$OPTARG" ;;
        h) EC2_HOST_VAL="$OPTARG" ;;
        u) EC2_USER="$OPTARG" ;;
        p) LOCAL_PORT="$OPTARG" ;;
        P) REMOTE_PORT="$OPTARG" ;;
        d) PG_DATABASE="$OPTARG" ;;
        *) echo "Usage: $0 [-k ssh_key] [-h ec2_host] [-u ec2_user] [-p local_port] [-P remote_port] [-d pg_database]"; exit 1 ;;
    esac
done

if [ -z "$SSH_KEY" ]; then
    read -rp "Path to SSH .pem key file: " SSH_KEY
fi
if [ ! -f "$SSH_KEY" ]; then
    echo "Error: SSH key not found: $SSH_KEY" >&2
    exit 1
fi

if [ -z "$EC2_HOST_VAL" ]; then
    read -rp "EC2 host (IP or hostname): " EC2_HOST_VAL
fi

echo "Opening SSH tunnel: localhost:${LOCAL_PORT} -> ${EC2_HOST_VAL}:${REMOTE_PORT}"

ssh -i "$SSH_KEY" \
    -L "${LOCAL_PORT}:localhost:${REMOTE_PORT}" \
    -N \
    -o StrictHostKeyChecking=no \
    -o ExitOnForwardFailure=yes \
    "${EC2_USER}@${EC2_HOST_VAL}" &
TUNNEL_PID=$!

sleep 2

if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo "Error: SSH tunnel failed to start. Check your key, host, and network." >&2
    exit 1
fi

echo "SSH tunnel running (PID: ${TUNNEL_PID})"

export DB_VIEWER_DSN="postgresql://${PG_USER}:${PG_PASSWORD}@localhost:${LOCAL_PORT}/${PG_DATABASE}"
echo "DSN: ${DB_VIEWER_DSN}"

cleanup() {
    echo "Shutting down SSH tunnel (PID: ${TUNNEL_PID})..."
    kill "$TUNNEL_PID" 2>/dev/null || true
    wait "$TUNNEL_PID" 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

echo "Starting Streamlit viewer..."
streamlit run app.py
