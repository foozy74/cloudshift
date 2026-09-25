#!/bin/sh
# Safe upgrade of a CloudShift installation to a given image version.
#
#   sh docker/upgrade.sh <version> [--yes]
#
# Run from the repository root after `git pull` (so that the templates and
# the changelog match the new version). Steps:
#   1. preflight: image available, no running transfers, compose config valid
#   2. config check: options/keys present in the templates but missing locally
#   3. backup: database dump, .env, coriolis.conf, users.yaml, current images
#   4. update: set CLOUDSHIFT_VERSION in .env, recreate the stack (db-sync
#      applies the DB migrations)
#   5. health check: db-sync exit code, all containers running, API/dashboard
#   6. automatic rollback on failure: previous images, and the database dump
#      if the schema version changed
#
# Overrides (mainly for testing): COMPOSE, RT, CONTAINER_PREFIX, API_URL,
# DASHBOARD_URL, HEALTH_TIMEOUT, BACKUP_ROOT.
set -eu

usage() { echo "usage: sh docker/upgrade.sh <version> [--yes]" >&2; exit 2; }
[ $# -ge 1 ] || usage
NEW_VERSION=$1
ASSUME_YES=0
[ "${2:-}" = "--yes" ] && ASSUME_YES=1
case $NEW_VERSION in
    ''|*[!A-Za-z0-9._-]*) echo "ERROR: invalid version '$NEW_VERSION'" >&2; exit 2 ;;
esac

PREFIX=${CONTAINER_PREFIX:-coriolis-}
API_URL=${API_URL:-http://localhost:7667/}
DASHBOARD_URL=${DASHBOARD_URL:-https://localhost/}
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-300}
BACKUP_ROOT=${BACKUP_ROOT:-backups}
TS=$(date +%Y%m%d-%H%M%S)
APP_SERVICES="api conductor worker scheduler minion-manager deployer-manager transfer-cron dashboard"

log() { printf '%s %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

confirm() {
    [ "$ASSUME_YES" -eq 1 ] && return 0
    printf '%s [y/N] ' "$1"
    read -r answer
    case $answer in y|Y|yes|j|J|ja) return 0 ;; *) die "aborted by user" ;; esac
}

[ -f .env ] || die ".env not found; run from the repository root (see .env.example)"

if [ -z "${COMPOSE:-}" ]; then
    if command -v podman-compose >/dev/null 2>&1 && [ -f docker-compose.podman.yml ]; then
        COMPOSE="podman-compose -f docker-compose.podman.yml"
        RT=${RT:-podman}
    elif command -v docker >/dev/null 2>&1; then
        COMPOSE="docker compose -f docker-compose.yml"
        RT=${RT:-docker}
    else
        die "neither podman-compose nor docker found"
    fi
fi
RT=${RT:-podman}

env_get() { sed -n "s/^$1=//p" .env | tail -1; }

env_set() {
    tmp=$(mktemp .env.XXXXXX)
    if grep -q "^$1=" .env; then
        sed "s|^$1=.*|$1=$2|" .env > "$tmp"
    else
        cat .env > "$tmp"
        printf '%s=%s\n' "$1" "$2" >> "$tmp"
    fi
    chmod 600 "$tmp"
    mv "$tmp" .env
}

# SQL runs inside the database container with its own credentials, so no
# password ever appears on the host command line.
db_query() {
    $RT exec "${PREFIX}db" sh -c \
        'MYSQL_PWD="$MYSQL_PASSWORD" mariadb -u "$MYSQL_USER" -N -B "$MYSQL_DATABASE" -e "$0"' "$1"
}

db_dump() {
    $RT exec "${PREFIX}db" sh -c \
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mariadb-dump -u root --single-transaction --routines --triggers --databases "$MYSQL_DATABASE"'
}

db_restore() {
    $RT exec "${PREFIX}db" sh -c \
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mariadb -u root -e "DROP DATABASE IF EXISTS \`$MYSQL_DATABASE\`"'
    gunzip -c "$1" | $RT exec -i "${PREFIX}db" sh -c \
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mariadb -u root'
}

schema_version() { db_query "SELECT version FROM migrate_version" 2>/dev/null || echo unknown; }

container_state() {
    $RT inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$1" 2>/dev/null || echo "missing -"
}

container_status() { state=$(container_state "$1"); echo "${state% *}"; }

http_code() {
    code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 "$1" 2>/dev/null) || true
    echo "${code:-000}"
}

image_ref() { echo "$REGISTRY/thesolution/$1:$2"; }

ensure_image() {
    $RT image inspect "$1" >/dev/null 2>&1 || $RT pull "$1" >/dev/null 2>&1
}

ini_keys() {
    awk '/^\[/ { s = $0; gsub(/[][ \t]/, "", s); next }
         /^[A-Za-z0-9_.-]+[ \t]*=/ { k = $0; sub(/[ \t]*=.*/, "", k); print s "." k }' "$1" | sort -u
}

env_keys() { sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' "$1" | sort -u; }

wait_healthy() {
    expected=$1
    deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        problems=""
        sync=$(container_state "${PREFIX}db-sync")
        case $sync in
            "exited 0") ;;
            exited*) echo "    db-sync failed (exit ${sync#* })"; return 1 ;;
            *) problems="$problems db-sync:${sync% *}" ;;
        esac
        for s in $APP_SERVICES; do
            status=$(container_status "$PREFIX$s")
            [ "$status" = running ] || problems="$problems $s:$status"
        done
        image=$($RT inspect -f '{{.Config.Image}}' "${PREFIX}api" 2>/dev/null || true)
        case $image in *":$expected") ;; *) problems="$problems api-image:${image:-none}" ;; esac
        api=$(http_code "$API_URL")
        case $api in [234]??) ;; *) problems="$problems api-http:$api" ;; esac
        dash=$(http_code "$DASHBOARD_URL")
        [ "$dash" = 200 ] || problems="$problems dashboard-http:$dash"
        [ -z "$problems" ] && return 0
        sleep 5
    done
    echo "    still unhealthy after ${HEALTH_TIMEOUT}s:$problems"
    return 1
}

REGISTRY=$(env_get CLOUDSHIFT_REGISTRY)
REGISTRY=${REGISTRY:-docker.registry.it.internal}
CURRENT_VERSION=$(env_get CLOUDSHIFT_VERSION)
CURRENT_VERSION=${CURRENT_VERSION:-latest}
[ "$CURRENT_VERSION" != "$NEW_VERSION" ] || die "already on version $NEW_VERSION"

log "CloudShift upgrade: $CURRENT_VERSION -> $NEW_VERSION ($COMPOSE)"

# ---------------------------------------------------------------- 1. preflight
log "1/6 Preflight"
for img in cloudshift cloudshift-dashboard; do
    ensure_image "$(image_ref $img "$NEW_VERSION")" || \
        die "image $(image_ref $img "$NEW_VERSION") not available"
done
echo "    images for $NEW_VERSION available"

[ "$(container_status "${PREFIX}db")" = running ] || die "database container ${PREFIX}db is not running; start the stack first"

active=$(db_query "SELECT COUNT(*) FROM tasks_execution WHERE status IN ('RUNNING','CANCELLING','AWAITING_MINION_ALLOCATIONS')") || \
    die "cannot query running executions"
[ "$active" -eq 0 ] || die "$active transfer/deployment execution(s) still active; wait until they finish"
echo "    no active executions"

avail_kb=$(df -Pk . | awk 'NR==2 {print $4}')
[ "$avail_kb" -ge 2097152 ] || die "less than 2 GB free in $(pwd)"

# ------------------------------------------------------------ 2. config check
log "2/6 Config check"
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
env_keys .env.example > "$tmpdir/env.example"
env_keys .env > "$tmpdir/env.local"
missing_env=$(comm -23 "$tmpdir/env.example" "$tmpdir/env.local" | grep -vxE 'CLOUDSHIFT_VERSION|CLOUDSHIFT_REGISTRY' || true)
[ -z "$missing_env" ] || die "missing in .env (see .env.example): $(echo $missing_env)"

ini_keys docker/coriolis.conf.example > "$tmpdir/conf.example"
ini_keys docker/coriolis.conf > "$tmpdir/conf.local"
missing_conf=$(comm -23 "$tmpdir/conf.example" "$tmpdir/conf.local" || true)
if [ -n "$missing_conf" ]; then
    echo "    options in coriolis.conf.example that are not set locally (code defaults apply):"
    echo "$missing_conf" | sed 's/^/      /'
else
    echo "    coriolis.conf has all template options"
fi

if [ -f CHANGELOG.md ]; then
    notes=$(awk -v v="$NEW_VERSION" '
        index($0, "## [" v "]") == 1 { p = 1; print; next }
        p && /^## \[/ { exit }
        p { print }' CHANGELOG.md)
    if [ -n "$notes" ]; then
        echo "    changelog for $NEW_VERSION:"
        echo "$notes" | sed 's/^/      /'
    else
        echo "    no CHANGELOG.md entry for $NEW_VERSION"
    fi
fi

cp -p .env "$tmpdir/env.new"
( env_set CLOUDSHIFT_VERSION "$NEW_VERSION" && $COMPOSE config >/dev/null 2>&1 ) || {
    cp -p "$tmpdir/env.new" .env
    die "compose configuration invalid for $NEW_VERSION"
}
cp -p "$tmpdir/env.new" .env

confirm "Upgrade $CURRENT_VERSION -> $NEW_VERSION now?"

# ----------------------------------------------------------------- 3. backup
BACKUP_DIR="$BACKUP_ROOT/upgrade-$TS-$CURRENT_VERSION-to-$NEW_VERSION"
log "3/6 Backup to $BACKUP_DIR/"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_ROOT" "$BACKUP_DIR"
cp -p .env "$BACKUP_DIR/env"
cp -p docker/coriolis.conf docker/users.yaml "$BACKUP_DIR/"
SCHEMA_BEFORE=$(schema_version)
db_dump | gzip > "$BACKUP_DIR/database.sql.gz"
gunzip -t "$BACKUP_DIR/database.sql.gz" || die "database dump is corrupt"
echo "    database schema $SCHEMA_BEFORE, dump $(du -h "$BACKUP_DIR/database.sql.gz" | cut -f1)"

# Pin the currently running images under a rollback tag, so that a mutable
# tag like "latest" cannot change underneath the rollback.
ROLLBACK_VERSION="rollback-$TS"
for img in cloudshift:api cloudshift-dashboard:dashboard; do
    name=${img%%:*}
    id=$($RT inspect -f '{{.Image}}' "$PREFIX${img#*:}" 2>/dev/null || true)
    [ -n "$id" ] || die "cannot determine the running $name image"
    $RT tag "$id" "$(image_ref "$name" "$ROLLBACK_VERSION")"
done
printf 'from=%s\nto=%s\nrollback_tag=%s\nschema_before=%s\n' \
    "$CURRENT_VERSION" "$NEW_VERSION" "$ROLLBACK_VERSION" "$SCHEMA_BEFORE" > "$BACKUP_DIR/versions"

# ---------------------------------------------------------------- 4. update
log "4/6 Updating to $NEW_VERSION"
env_set CLOUDSHIFT_VERSION "$NEW_VERSION"
update_ok=1
$COMPOSE up -d --force-recreate >"$BACKUP_DIR/update.log" 2>&1 || update_ok=0

# ------------------------------------------------------------ 5. health check
log "5/6 Health check (up to ${HEALTH_TIMEOUT}s)"
if [ "$update_ok" -eq 1 ] && wait_healthy "$NEW_VERSION"; then
    log "Upgrade to $NEW_VERSION successful (schema $SCHEMA_BEFORE -> $(schema_version))"
    echo "    Backup: $BACKUP_DIR/ (contains secrets; remove old backups regularly)"
    echo "    Rollback image tag kept: $ROLLBACK_VERSION"
    exit 0
fi

# --------------------------------------------------------------- 6. rollback
SCHEMA_AFTER=$(schema_version)
log "6/6 Upgrade failed, rolling back to $CURRENT_VERSION (schema now $SCHEMA_AFTER)"
env_set CLOUDSHIFT_VERSION "$ROLLBACK_VERSION"
if [ "$SCHEMA_AFTER" != "$SCHEMA_BEFORE" ]; then
    echo "    schema changed, restoring the database dump"
    for s in $APP_SERVICES db-sync; do $RT stop "$PREFIX$s" >/dev/null 2>&1 || true; done
    db_restore "$BACKUP_DIR/database.sql.gz" || die "database restore failed; dump: $BACKUP_DIR/database.sql.gz"
fi
$COMPOSE up -d --force-recreate >"$BACKUP_DIR/rollback.log" 2>&1 || true
if wait_healthy "$ROLLBACK_VERSION"; then
    # A pinned release tag points to the same images again; a mutable tag
    # like "latest" may already point to the new images, so keep the
    # rollback tag in that case.
    if [ "$CURRENT_VERSION" != latest ]; then
        env_set CLOUDSHIFT_VERSION "$CURRENT_VERSION"
    fi
    log "Rolled back to $CURRENT_VERSION (image tag $ROLLBACK_VERSION, schema $(schema_version))"
    echo "    CLOUDSHIFT_VERSION in .env: $(env_get CLOUDSHIFT_VERSION)"
    echo "    Logs: $BACKUP_DIR/update.log"
    exit 1
fi
die "rollback unhealthy; manual action needed. Backup: $BACKUP_DIR/"
