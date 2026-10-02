#!/usr/bin/env bash
# Installs a pre-push hook so nothing reaches GitHub without passing
# scripts/check.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
cat > .git/hooks/pre-push <<'HOOK'
#!/usr/bin/env bash
exec "$(git rev-parse --show-toplevel)/scripts/check.sh"
HOOK
chmod +x .git/hooks/pre-push
echo "pre-push hook installed"
