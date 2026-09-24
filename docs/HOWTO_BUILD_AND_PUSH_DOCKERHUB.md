# How-To: CloudShift Container auf macOS (Apple Silicon) bauen und auf Docker Hub veröffentlichen

Dieses Dokument beschreibt die Schritte, um die CloudShift-Container (`cloudshift` Core und `cloudshift-dashboard`) auf einem Mac (Apple Silicon M1/M2/M3/M4) korrekt für Intel/AMD64-Zielsysteme zu bauen und auf Docker Hub bereitzustellen.

---

## 1. Voraussetzungen

1. **Docker Desktop** oder **OrbStack** auf macOS installiert und gestartet.
2. **Docker Hub Account** mit Zugriff auf die Organisation / das Repository (z. B. `thesolution`).
3. **Docker Hub Personal Access Token (PAT)**:
   - Erstellbar unter [Docker Hub Account Settings → Security → Personal access tokens](https://hub.docker.com/settings/security).

---

## 2. Vorbereitung der Dockerfiles

### 2.1 Basis-Images und PyPI-Konfiguration
Für offizielle Docker Hub Releases dürfen keine internen Firmen-Mirrors fest im Dockerfile fest verdrahtet sein:

* **Core Image (`Dockerfile`):**
  Stelle sicher, dass `FROM python:3.11-slim` als Basis-Image definiert ist (bzw. über Build-Args gesteuert wird).
* **Dashboard Image (`docker/dashboard/Dockerfile`):**
  Stelle sicher, dass `FROM nginx:alpine` als Basis-Image verwendet wird.

---

## 3. Login bei Docker Hub

Führe im Terminal deines Macs den Login durch:

```bash
docker login -u DEIN_DOCKERHUB_USERNAME
# Passwort oder Personal Access Token (PAT) eingeben
```
*(Die Meldung `Login Succeeded` bestätigt die erfolgreiche Authentifizierung).*

---

## 4. Das Architektur-Problem (ARM64 vs. AMD64)

Standardmäßig baut Docker auf Apple Silicon Macs Images für die Architektur `linux/arm64`. Wenn dieses Image auf einem Linux x86_64-Server gezogen wird, schlägt der Start mit folgender Fehlermeldung fehl:

> `no image found in image index for architecture "amd64", variant "", OS "linux"`

**Lösung:** Das Image muss explizit mit `--platform linux/amd64` (oder als Multi-Architektur mit `buildx`) gebaut werden.

---

## 5. Bauen und Pushen der Images

Wechsle in das Root-Verzeichnis des CloudShift-Repositories:
```bash
cd /Users/jurgen/dev/thesolution/cloudshift
```

### 5.1 CloudShift Core Backend

#### Variante A: Gezielt für AMD64 (Schnell & direkt)
```bash
# 1. Image für AMD64 kompilieren
docker build --platform linux/amd64 \
  -t thesolution/cloudshift:latest \
  -t thesolution/cloudshift:v1.0.0 .

# 2. Zu Docker Hub hochladen
docker push thesolution/cloudshift:latest
docker push thesolution/cloudshift:v1.0.0
```

#### Variante B: Multi-Architektur mit Buildx (AMD64 & ARM64 in einem Manifest)
```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t thesolution/cloudshift:latest \
  -t thesolution/cloudshift:v1.0.0 \
  --push .
```

---

### 5.2 CloudShift Dashboard (Nginx Web UI)

#### Variante A: Gezielt für AMD64
```bash
# 1. Dashboard für AMD64 kompilieren
docker build --platform linux/amd64 \
  -t thesolution/cloudshift-dashboard:latest \
  -t thesolution/cloudshift-dashboard:v1.0.0 \
  -f docker/dashboard/Dockerfile ./docker/dashboard

# 2. Zu Docker Hub hochladen
docker push thesolution/cloudshift-dashboard:latest
docker push thesolution/cloudshift-dashboard:v1.0.0
```

#### Variante B: Multi-Architektur mit Buildx
```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t thesolution/cloudshift-dashboard:latest \
  -t thesolution/cloudshift-dashboard:v1.0.0 \
  -f docker/dashboard/Dockerfile ./docker/dashboard \
  --push
```

---

## 6. Verifikation vor oder nach dem Push

### 6.1 Lokale Architektur prüfen:
```bash
docker inspect thesolution/cloudshift:latest --format '{{.Architecture}} {{.Os}}'
# Soll-Ausgabe: amd64 linux
```

### 6.2 Remote-Manifest auf Docker Hub überprüfen:
```bash
docker buildx imagetools inspect thesolution/cloudshift:latest
# Soll-Ausgabe: Zeigt die unterstützten Architekturen (amd64 / arm64)
```

---

## 7. Automatisierung über GitHub Actions

Im Projekt ist unter `.github/workflows/docker-build.yml` ein automatischer Build-Workflow hinterlegt. 

Um diesen auf Docker Hub umzuleiten:
1. Im GitHub Repository unter **Settings → Secrets and variables → Actions** folgende Secrets hinterlegen:
   - `DOCKERHUB_USERNAME`: Euer Docker Hub Account-Name
   - `DOCKERHUB_TOKEN`: Euer Docker Hub Personal Access Token
2. Im Workflow `REGISTRY: docker.io` eintragen und via `docker/login-action@v3` authentifizieren.
3. Jeder Git-Tag (z. B. `git tag v1.0.0 && git push origin v1.0.0`) baut und pusht automatisch Multi-Arch-Images zu Docker Hub.
