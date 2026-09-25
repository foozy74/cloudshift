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

### 2.2 Artifactory-Zugangsdaten und Geheimnisse
* **Artifactory:** Ohne Zugangsdaten nutzt der Build den anonymen PyPI-Proxy von `artifactory.three.com`. Werden Zugangsdaten gebraucht, **nur als BuildKit-Secret** übergeben, nie als `--build-arg` (Build-Args landen in `docker history` und die frühere Variante schrieb sie in `/etc/pip.conf` im Image):
  ```bash
  export ARTIFACTORY_USER=<user>
  read -s -p "Artifactory-Passwort: " ARTIFACTORY_PW; export ARTIFACTORY_PW; echo
  docker build \
    --secret id=artifactory_user,env=ARTIFACTORY_USER \
    --secret id=artifactory_pw,env=ARTIFACTORY_PW \
    -t thesolution/cloudshift:latest .
  # Podman: --secret id=artifactory_user,src=<datei> --secret id=artifactory_pw,src=<datei>
  ```
  `docker/pip-artifactory.sh` liest die Secrets nur während der `pip`-Schritte; im fertigen Image bleibt nichts davon.
* **Nicht im Image:** `.dockerignore` schließt `.git`, `docker/users.yaml`, `docker/coriolis.conf`, `docker/dashboard/ssl/`, `secrets/` und Schlüsseldateien aus. Diese Dateien werden zur Laufzeit per Volume eingebunden (siehe `docker-compose.yml`). Vor jedem Push prüfen:
  ```bash
  docker run --rm --entrypoint sh thesolution/cloudshift:latest -c \
    'ls /app/docker/users.yaml /app/docker/coriolis.conf /app/.git 2>&1 | grep -c "No such file"'
  # Soll-Ausgabe: 3
  ```

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

## 6. Verifikation vor dem Push (Pflicht)

Vor **jedem** Push, auch bei manuellen Builds:

```bash
sh docker/verify-images.sh thesolution/cloudshift:<tag> thesolution/cloudshift-dashboard:<tag>
# Soll-Ausgabe: OK: ... verified
```

Das Skript bricht ab, wenn Geheimnisse oder lokale Dateien im Image stecken (`.git`, `.env`, `users.yaml`, `coriolis.conf`, TLS-Schlüssel, Artifactory-Zugangsdaten) oder Laufzeitdateien fehlen (`migrate.cfg`, Python-Module ohne `__init__.py`, Einstiegspunkte). Beides ist schon einmal passiert.

Architektur prüfen:
```bash
docker buildx imagetools inspect thesolution/cloudshift:<tag>
# Soll-Ausgabe: linux/amd64 und linux/arm64
```

---

## 7. Release über GitHub Actions (Standardweg)

Releases werden nur noch über `.github/workflows/docker-build.yml` gebaut, manuelle Pushes sind die Ausnahme.

**Einmalig:** im GitHub-Repository unter **Settings → Secrets and variables → Actions** hinterlegen:
- `DOCKERHUB_USERNAME`: Docker-Hub-Account
- `DOCKERHUB_TOKEN`: Docker-Hub-Access-Token (Read/Write für `thesolution/*`)

**Pro Release:**
1. In `CHANGELOG.md` einen Abschnitt `## [1.4.0] - <Datum>` mit `### Upgrade-Hinweise` anlegen (neue Optionen, manuelle Schritte, Breaking Changes; `docker/upgrade.sh` zeigt ihn vor dem Update an).
2. Tag setzen und pushen:
   ```bash
   git tag 1.4.0 && git push origin 1.4.0
   ```
3. Der Workflow baut amd64 zur Prüfung, führt `docker/verify-images.sh` aus und pusht erst danach Multi-Arch-Images mit den Tags `1.4.0`, `1.4` und `sha-<commit>` nach Docker Hub. `latest` wird bei jedem Release-Tag automatisch mitgesetzt.
4. Server aktualisieren: `sh docker/upgrade.sh 1.4.0` (siehe [HOWTO_RUN_PODMAN_ROOTLESS_INTERNAL_REGISTRY.md](HOWTO_RUN_PODMAN_ROOTLESS_INTERNAL_REGISTRY.md), Abschnitt 9.1).

Auf GitHub ist Artifactory nicht erreichbar; der Workflow baut deshalb mit `PIP_INDEX_URL=https://pypi.org/simple`.
