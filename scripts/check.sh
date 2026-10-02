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

step "README links"
"$PY" - <<'PYCHECK'
import re, os, sys
text = open('README.md').read()
targets = re.findall(r'!?\[[^\]]*\]\(([^)#]+)\)', text) + re.findall(r'<img src="([^"]+)"', text)
local = [t for t in targets if not t.startswith(('http://', 'https://', 'mailto:'))]
missing = [t for t in local if not os.path.exists(t)]
if missing:
    sys.exit('README links to missing files: ' + ', '.join(missing))
print(f'{len(local)} local links ok')
PYCHECK

step "boot under gunicorn, as deployed (2 workers, no API key)"
COOKIES=$(mktemp)
env -u GEMINI_API_KEY -u FLASK_DEBUG -u GROWTHSCOPE_DEBUG_ROUTES SESSION_SECRET=check-secret \
  "$(dirname "$PY")/gunicorn" main:app --workers 2 --bind "127.0.0.1:$PORT" >/tmp/growthscope-check.log 2>&1 &
APP=$!
trap 'kill $APP 2>/dev/null || true; rm -f "$COOKIES"' EXIT
for _ in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/healthz" || true)
  [ "$code" = 200 ] && break
  sleep 0.5
done
[ "$code" = 200 ] || { echo "/healthz did not answer (got $code)"; cat /tmp/growthscope-check.log; exit 1; }
curl -s -c "$COOKIES" -o /dev/null -d 'username=check&password=check' "http://127.0.0.1:$PORT/login"
curl -s -b "$COOKIES" -c "$COOKIES" -o /dev/null -d 'demo_type=synthetic_sales_100&date_filter=all' "http://127.0.0.1:$PORT/load-demo-data"
# Twenty requests land on both workers; each must still see the session.
for _ in $(seq 1 20); do
  code=$(curl -s -b "$COOKIES" -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/dashboard/executive")
  [ "$code" = 200 ] || { echo "dashboard returned $code: session lost between workers?"; exit 1; }
done
[ "$(curl -s -b "$COOKIES" -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/debug/session")" = 404 ] \
  || { echo "debug routes are exposed"; exit 1; }
echo "healthz ok, session holds across 20 requests on 2 workers, debug routes hidden"

printf '\nAll checks passed.\n'
