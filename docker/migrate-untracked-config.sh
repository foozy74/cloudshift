#!/bin/sh
# One-off migration for existing clones/servers after the 2026-09-25 cleanup:
# - main/master were rewritten (force-push), so a plain `git pull` fails
# - docker/coriolis.conf, docker/users.yaml and docker/dashboard/ssl/ are no
#   longer tracked; updating would delete them from the working tree
# - docker-compose now reads DB/RabbitMQ secrets from .env
#
# Run from the repository root BEFORE pulling:
#   sh docker/migrate-untracked-config.sh [remote] [branch]
# The script backs up the local config, creates .env from the current
# compose values, resets the branch to the remote and restores the config.
set -eu

REMOTE=${1:-origin}
BRANCH=${2:-$(git rev-parse --abbrev-ref HEAD)}
BACKUP_DIR=".config-backup-$(date +%Y%m%d-%H%M%S)"
CONFIG_FILES="docker/coriolis.conf docker/users.yaml docker/dashboard/ssl/cert.crt docker/dashboard/ssl/cert.key"

die() { echo "ERROR: $*" >&2; exit 1; }

[ -d .git ] || die "run from the repository root"
[ -z "$(git status --porcelain --untracked-files=no)" ] || \
    die "uncommitted changes in tracked files; commit or stash them first"

# Local commits that were never pushed would be lost by the reset.
if git rev-parse -q --verify "$REMOTE/$BRANCH" >/dev/null; then
    unpushed=$(git rev-list --count "$REMOTE/$BRANCH..HEAD")
    [ "$unpushed" -eq 0 ] || \
        die "$unpushed local commit(s) not on $REMOTE/$BRANCH; push or save them first"
fi

echo "1/5 Backing up local config to $BACKUP_DIR/"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
for f in $CONFIG_FILES; do
    if [ -f "$f" ]; then
        mkdir -p "$BACKUP_DIR/$(dirname "$f")"
        cp -p "$f" "$BACKUP_DIR/$f"
    fi
done

echo "2/5 Creating .env from the current compose values"
if [ -f .env ]; then
    echo "    .env exists, keeping it"
else
    python3 - <<'EOF'
import os, re
src = open("docker-compose.yml").read()
def val(key):
    m = re.search(rf"^\s+{key}:\s*(.+)$", src, re.M)
    if not m:
        raise SystemExit(f"ERROR: {key} not found in docker-compose.yml")
    v = m.group(1).strip().strip("\"'")
    if v.startswith("${"):
        raise SystemExit("ERROR: docker-compose.yml already uses .env; create .env from .env.example")
    return v
values = {
    "DB_ROOT_PASSWORD": val("MYSQL_ROOT_PASSWORD"),
    "DB_PASSWORD": val("MYSQL_PASSWORD"),
    "RABBITMQ_USER": val("RABBITMQ_DEFAULT_USER"),
    "RABBITMQ_PASSWORD": val("RABBITMQ_DEFAULT_PASS"),
    "RABBITMQ_ERLANG_COOKIE": val("RABBITMQ_ERLANG_COOKIE"),
}
fd = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("# Secrets for docker-compose (not tracked in git). Template: .env.example\n")
    for k, v in values.items():
        f.write(f"{k}={v}\n")
EOF
fi

echo "3/5 Fetching $REMOTE and resetting $BRANCH to $REMOTE/$BRANCH"
git fetch "$REMOTE"
git reset --hard "$REMOTE/$BRANCH"

echo "4/5 Restoring local config"
for f in $CONFIG_FILES; do
    if [ -f "$BACKUP_DIR/$f" ] && [ ! -f "$f" ]; then
        mkdir -p "$(dirname "$f")"
        cp -p "$BACKUP_DIR/$f" "$f"
    fi
done
[ -f docker/dashboard/ssl/cert.key ] && chmod 600 docker/dashboard/ssl/cert.key

echo "5/5 Checking"
missing=""
for f in docker/coriolis.conf docker/users.yaml .env; do
    [ -f "$f" ] || missing="$missing $f"
done
[ -z "$missing" ] || die "missing after migration:$missing (see *.example)"
if command -v docker >/dev/null 2>&1; then
    docker compose config -q && echo "    docker compose config ok"
fi

echo "Done. Backup: $BACKUP_DIR/ (contains secrets, delete it once everything runs)."
echo "Rotate the credentials that were public (see DASHBOARD_README.md)."
