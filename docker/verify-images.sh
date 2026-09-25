#!/bin/sh
# Verifies built images before they are published:
#   - no secrets or local state baked in (.git, .env, users.yaml,
#     coriolis.conf, TLS material, SSH keys, Artifactory credentials)
#   - runtime files present (migrate.cfg, every tracked Python module,
#     service entry points)
#
#   sh docker/verify-images.sh <core-image> <dashboard-image>
#
# Run from the repository root (compares against `git ls-files`).
set -eu

[ $# -eq 2 ] || { echo "usage: sh docker/verify-images.sh <core-image> <dashboard-image>" >&2; exit 2; }
CORE=$1
DASHBOARD=$2
RT=${RT:-docker}
PKG=/usr/local/lib/python3.11/site-packages/coriolis

fail() { echo "FAIL: $*" >&2; exit 1; }

# shellcheck disable=SC2016  # the script runs inside the container
$RT run --rm -w / --entrypoint sh -e PKG="$PKG" "$CORE" -c '
    set -eu
    for f in /app/.git /app/.env /app/docker/users.yaml /app/docker/coriolis.conf \
             /app/docker/dashboard/ssl /app/secrets /app/offline-bundle; do
        [ ! -e "$f" ] || { echo "FAIL: secret/local file in image: $f"; exit 1; }
    done
    keys=$(find /app \( -name "*.key" -o -name "*.pem" \) | wc -l)
    [ "$keys" -eq 0 ] || { echo "FAIL: $keys key file(s) under /app"; exit 1; }
    if grep -q "@" /etc/pip.conf 2>/dev/null; then
        echo "FAIL: credentials in /etc/pip.conf"; exit 1
    fi
    [ -f "$PKG/db/sqlalchemy/migrate_repo/migrate.cfg" ] || { echo "FAIL: migrate.cfg missing"; exit 1; }
    python3 -c "import coriolis.api.middleware.auth, coriolis.api.middleware.fault" || \
        { echo "FAIL: coriolis.api.middleware not importable"; exit 1; }
    for cmd in coriolis-api coriolis-conductor coriolis-worker coriolis-scheduler \
               coriolis-minion-manager coriolis-deployer-manager coriolis-transfer-cron coriolis-dbsync; do
        command -v "$cmd" >/dev/null || { echo "FAIL: entry point $cmd missing"; exit 1; }
    done
' || fail "core image checks"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# shellcheck disable=SC2016
$RT run --rm --entrypoint sh -e PKG="$PKG" "$CORE" -c \
    'cd "$PKG" && find . -name "*.py" ! -path "./tests/*" | sed "s#^\./##" | sort' > "$tmp/installed"
git ls-files 'coriolis/*.py' | grep -vE '^coriolis/(tests|api-refs)/' | sed 's#^coriolis/##' | sort > "$tmp/tracked"
missing=$(comm -23 "$tmp/tracked" "$tmp/installed")
[ -z "$missing" ] || fail "Python modules missing in image (package without __init__.py?):
$missing"

$RT run --rm --entrypoint sh "$DASHBOARD" -c '[ ! -e /etc/nginx/ssl ]' || \
    fail "TLS material baked into the dashboard image"

echo "OK: $CORE and $DASHBOARD verified"
