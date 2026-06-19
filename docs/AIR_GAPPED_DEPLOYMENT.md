# Offline & Air-Gapped Deployment Guide

This guide details how to deploy CloudShift in network-isolated (air-gapped) enterprise environments.

---

## The Offline Challenge

Standard Docker/Podman deployments require internet access to:
1. Pull base images (`python:3.11-slim`, `mariadb:10-jammy`, `rabbitmq:3-management`).
2. Run `apt-get` commands inside Dockerfiles.
3. Install Python dependencies from PyPI (`pip install`).
4. Pull git-based dependencies (e.g. `pywinrm`).

In an air-gapped environment, these actions will fail. 

---

## Phase 1: Build & Export (On Internet-Connected Host)

Execute these steps on a machine with internet access.

### 1. Build CloudShift Custom Image
```bash
# Clone the repository
git clone git@github.com:foozy74/cloudshift.git
cd cloudshift

# Build the custom image
docker build --no-cache -t ghcr.io/thesolution/cloudshift:latest .
```

### 2. Pull Third-Party Dependencies
```bash
docker pull mariadb:10-jammy
docker pull rabbitmq:3-management
docker pull nginx:alpine
```

### 3. Save Images to Tar Archives
```bash
mkdir -p offline-images

docker save ghcr.io/thesolution/cloudshift:latest -o offline-images/cloudshift.tar
docker save mariadb:10-jammy -o offline-images/mariadb.tar
docker save rabbitmq:3-management -o offline-images/rabbitmq.tar
docker save nginx:alpine -o offline-images/nginx.tar
```

### 4. Package Config and Codebase
Create a deployment bundle containing the `docker-compose.yml`, `docker/` folder, and the exported `.tar` images.

---

## Phase 2: Transfer

Transfer the deployment bundle (including the `.tar` files) to the target control plane VM via USB, secure SFTP, or internal repository mirrors.

---

## Phase 3: Import & Deploy (On Air-Gapped Target)

Run these steps on the offline control plane machine.

### 1. Load the Container Images
```bash
docker load -i offline-images/cloudshift.tar
docker load -i offline-images/mariadb.tar
docker load -i offline-images/rabbitmq.tar
docker load -i offline-images/nginx.tar
```

### 2. Configure Local docker-compose.yml
Modify your `docker-compose.yml` to ensure no `build:` directives are triggered, and references point to the loaded images.

```yaml
  api:
    image: ghcr.io/thesolution/cloudshift:latest
    # Remove 'build:' blocks so compose does not attempt offline rebuilds
```

### 3. Launch Stack
```bash
docker-compose --profile dashboard up -d
```
