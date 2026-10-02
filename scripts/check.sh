#!/usr/bin/env bash
# The gate every change passes before it is pushed: lint, tests, a secret
# scan, and a real boot of the app. Run it directly, or let the pre-push
# hook (scripts/install-hooks.sh) run it for you.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -x .venv/bin/python ]; then DEFAULT_PY=.venv/bin/python; else DEFAULT_PY=python3; fi
PY="${PYTHON:-$DEFAULT_PY}"
PORT="${CHECK_PORT:-5099}"

step() { printf '\n== %s\n' "$1"; }

step "lint (ruff: pyflakes + syntax errors)"
"$PY" -m ruff check --select F,E9 .

step "tests"
"$PY" -m pytest -q

step "secret scan"
if git grep -nIE 'AIza[0-9A-Za-z_-]{35}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY' -- . ':!scripts/check.sh'; then
  echo "Possible secret committed. Remove it before pushing." >&2
  exit 1
fi
echo "clean"

step "boot (no API key, production settings)"
env -u GEMINI_API_KEY -u FLASK_DEBUG PORT="$PORT" "$PY" main.py >/tmp/growthscope-check.log 2>&1 &
APP=$!
trap 'kill $APP 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/login" || true)
  [ "$code" = 200 ] && break
  sleep 0.5
done
[ "$code" = 200 ] || { echo "app did not serve /login (got $code)"; cat /tmp/growthscope-check.log; exit 1; }
grep -q 'Debug mode: off' /tmp/growthscope-check.log || { echo "debug mode is on"; exit 1; }
echo "serves /login, debug off"

printf '\nAll checks passed.\n'
