#!/usr/bin/env bash
# Runs after every Plesk Git deploy, as the domain's system user.
# Plesk → Git → (repo) → Repository settings → "Enable additional deployment actions":
#     bash deploy/post_deploy.sh
#
# 1. creates/updates the Python virtualenv from requirements.txt
# 2. copies the login settings (secrets.toml) from the private folder
# 3. signals systemd (encalm-restart.path) to restart the app
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PRIVATE_DIR="${PRIVATE_DIR:-$(dirname "$APP_DIR")/private}"
PYTHON="${PYTHON:-python3}"

cd "$APP_DIR"

if [ ! -x venv/bin/python ]; then
    echo "Creating virtualenv…"
    "$PYTHON" -m venv venv
fi
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt

mkdir -p .streamlit
if [ -f "$PRIVATE_DIR/secrets.toml" ]; then
    cp "$PRIVATE_DIR/secrets.toml" .streamlit/secrets.toml
    chmod 600 .streamlit/secrets.toml
else
    echo "WARNING: $PRIVATE_DIR/secrets.toml not found — nobody will be able to sign in." >&2
fi

# Quick sanity check before restarting (fails the deploy on a broken commit)
venv/bin/python -m py_compile Home.py modules/*.py pages/*.py

touch "$APP_DIR/.deployed"     # encalm-restart.path restarts encalm.service
echo "Deploy finished: $(git -C "$APP_DIR" log -1 --format='%h %s' 2>/dev/null || date)"
