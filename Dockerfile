FROM python:3.11-slim

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

# Upgrade pip and tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

# Copy dependency specifications
COPY requirements.txt /app/
COPY test-requirements.txt /app/

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy codebase
COPY . /app/

# Install the CloudShift application (compiles resources via setup.py/make)
RUN pip install --no-cache-dir .

# Create configuration directory
RUN mkdir -p /etc/coriolis

# Expose API port
EXPOSE 7667

# Default CMD (can be overridden in docker-compose.yml for specific services)
CMD ["cloudshift-api", "--config-file", "/etc/coriolis/coriolis.conf"]
