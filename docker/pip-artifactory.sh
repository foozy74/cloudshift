#!/bin/sh
# Runs pip against the Artifactory PyPI proxy. Credentials come from the
# BuildKit secrets artifactory_user / artifactory_pw, which exist only
# during the RUN step and never end up in an image layer or in
# `docker history`. Without secrets, /etc/pip.conf (anonymous) is used.
set -e

SECRETS_DIR=/run/secrets
PYPI_BASE=artifactory.three.com/artifactory/api/pypi

if [ -s "$SECRETS_DIR/artifactory_user" ] && [ -s "$SECRETS_DIR/artifactory_pw" ]; then
    auth=$(python3 - "$SECRETS_DIR" <<'EOF'
import sys
from urllib.parse import quote
secrets_dir = sys.argv[1]
user = open(f"{secrets_dir}/artifactory_user").read().strip()
password = open(f"{secrets_dir}/artifactory_pw").read().strip()
print(f"{quote(user, safe='')}:{quote(password, safe='')}")
EOF
)
    PIP_INDEX_URL="https://${auth}@${PYPI_BASE}/pypi-remote/simple"
    PIP_EXTRA_INDEX_URL="https://${auth}@${PYPI_BASE}/pypi-local/simple"
    export PIP_INDEX_URL PIP_EXTRA_INDEX_URL
fi

exec pip "$@"
