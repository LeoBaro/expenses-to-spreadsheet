#!/usr/bin/env bash
# Copy the files the container needs to the Raspberry Pi:
#   .env, secrets/, deploy/docker-compose.yml and (first time only) state/.
#
# Usage:  deploy/copy-to-pi.sh [--overwrite-state] [-i <ssh-key>] [user@pi-address]
#
# Defaults (override with the arguments or the env vars):
#   PI_HOST     pi4@192.168.0.125
#   PI_SSH_KEY  ~/.ssh/id_pi4access   (used only if the file exists)
#   PI_DIR      /home/pi4/Workspace/expenses-to-spreadsheet
# See docs/raspberry-pi-deployment.md.
set -euo pipefail

PI_DIR="${PI_DIR:-/home/pi4/Workspace/expenses-to-spreadsheet}"
STATE_FILE="state/processed_transactions.log"
OVERWRITE_STATE=false
PI_HOST="${PI_HOST:-pi4@192.168.0.125}"
PI_SSH_KEY="${PI_SSH_KEY:-$HOME/.ssh/id_pi4access}"

usage() {
    echo "Usage: $0 [--overwrite-state] [-i <ssh-key>] [user@pi-address]" >&2
    exit 2
}

while (($#)); do
    case "$1" in
        --overwrite-state) OVERWRITE_STATE=true ;;
        -i) [[ $# -ge 2 ]] || usage; PI_SSH_KEY="$2"; shift ;;
        -h|--help) usage ;;
        -*) echo "Unknown option: $1" >&2; usage ;;
        *) PI_HOST="$1" ;;
    esac
    shift
done

# Run from the repo root, wherever the script is called from.
cd "$(dirname "$0")/.."

# --- local checks -------------------------------------------------------------
missing=()
[[ -f .env ]] || missing+=(".env")
compgen -G "secrets/*.pem" >/dev/null || missing+=("secrets/*.pem (Enable Banking key)")
compgen -G "secrets/*.json" >/dev/null || missing+=("secrets/*.json (Google service-account key)")
if ((${#missing[@]})); then
    printf 'Missing: %s\n' "${missing[@]}" >&2
    exit 1
fi

# Only one instance may run: two would both poll the bank and Telegram.
if pgrep -f "expenses-serve" >/dev/null \
    || { command -v docker >/dev/null && [[ -n "$(docker ps -q -f name='^expenses$' 2>/dev/null)" ]]; }; then
    echo "The app is still running on this computer. Stop it first, so the state file" >&2
    echo "is complete and the Pi isn't a second instance." >&2
    exit 1
fi

# --- copy -----------------------------------------------------------------------
# Reuse one SSH connection, so a password is asked at most once.
control_dir="$(mktemp -d)"
trap 'ssh -o ControlPath="$control_dir/ssh" -O exit "$PI_HOST" 2>/dev/null || true; rm -rf "$control_dir"' EXIT
SSH=(ssh -o ControlMaster=auto -o ControlPath="$control_dir/ssh" -o ControlPersist=60)
if [[ -f "$PI_SSH_KEY" ]]; then
    SSH+=(-i "$PI_SSH_KEY" -o IdentitiesOnly=yes)
fi
RSYNC=(rsync -a --chmod=D700,F600 -e "${SSH[*]}")

# The container runs as uid 1000 and reads secrets/ / writes state/ through the
# mounts, so the files must belong to uid 1000 on the Pi too. That's the first user
# Raspberry Pi OS creates.
remote_uid="$("${SSH[@]}" "$PI_HOST" 'id -u')"
if [[ "$remote_uid" != "1000" ]]; then
    echo "$PI_HOST has uid $remote_uid, but the container runs as uid 1000 and could not" >&2
    echo "read the copied secrets. Use the Pi's uid-1000 user (usually the first one)." >&2
    exit 1
fi

echo "→ Preparing $PI_HOST:$PI_DIR"
"${SSH[@]}" "$PI_HOST" "mkdir -p '$PI_DIR/secrets' '$PI_DIR/state'"

echo "→ Copying .env, secrets/ and docker-compose.yml"
"${RSYNC[@]}" .env "$PI_HOST:$PI_DIR/.env"
"${RSYNC[@]}" secrets/ "$PI_HOST:$PI_DIR/secrets/"
rsync -a --chmod=F644 -e "${SSH[*]}" deploy/docker-compose.yml "$PI_HOST:$PI_DIR/docker-compose.yml"

# The Pi's state file is newer than ours once the app has run there; overwriting it
# with ours would reprocess transactions and write duplicate rows.
if [[ ! -f "$STATE_FILE" ]]; then
    echo "→ No local $STATE_FILE; the Pi starts with an empty history."
elif "${SSH[@]}" "$PI_HOST" "test -s '$PI_DIR/$STATE_FILE'" && ! $OVERWRITE_STATE; then
    echo "→ Pi already has $STATE_FILE; leaving it alone (use --overwrite-state to replace it)."
else
    echo "→ Copying $STATE_FILE"
    rsync -a --chmod=F644 -e "${SSH[*]}" "$STATE_FILE" "$PI_HOST:$PI_DIR/$STATE_FILE"
fi

cat <<EOF

Done. On the Pi:
  cd $PI_DIR
  docker compose pull && docker compose up -d
EOF
