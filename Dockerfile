ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="CloudShift" \
      org.opencontainers.image.description="VMware to OLVM/Hyper-V Workload Migration as a Service" \
      org.opencontainers.image.vendor="thesolution.at" \
      org.opencontainers.image.licenses="Apache-2.0"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    make \
    gcc \
    libc-dev \
    qemu-utils \
    git \
    libmariadb-dev-compat \
    libmariadb-dev \
    pkg-config \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Configure Artifactory PyPI proxy. /etc/pip.conf stays anonymous; the
# credentials are passed as BuildKit secrets and only used by
# pip-artifactory during the RUN steps (they never land in a layer):
#   docker build --secret id=artifactory_user,env=ARTIFACTORY_USER \
#                --secret id=artifactory_pw,env=ARTIFACTORY_PW .
RUN printf "[global]\nindex-url = https://artifactory.three.com/artifactory/api/pypi/pypi-remote/simple\n" > /etc/pip.conf
COPY docker/pip-artifactory.sh /usr/local/bin/pip-artifactory

# Upgrade pip and tools
RUN --mount=type=secret,id=artifactory_user --mount=type=secret,id=artifactory_pw \
    pip-artifactory install --no-cache-dir --upgrade pip setuptools wheel

# Copy dependency specifications
COPY requirements.txt /app/
COPY test-requirements.txt /app/

# Install python dependencies
RUN --mount=type=secret,id=artifactory_user --mount=type=secret,id=artifactory_pw \
    pip-artifactory install --no-cache-dir -r requirements.txt

# Copy codebase
COPY . /app/

# Install the CloudShift application (compiles resources via setup.py/make).
# .git is excluded by .dockerignore, so pbr takes the version from here.
ARG PBR_VERSION=1.3.0
ENV PBR_VERSION=${PBR_VERSION}
RUN --mount=type=secret,id=artifactory_user --mount=type=secret,id=artifactory_pw \
    pip-artifactory install --no-cache-dir .

# Create configuration directory
RUN mkdir -p /etc/coriolis

# Expose API port
EXPOSE 7667

# Default CMD (can be overridden in docker-compose.yml for specific services)
CMD ["cloudshift-api", "--config-file", "/etc/coriolis/coriolis.conf"]
