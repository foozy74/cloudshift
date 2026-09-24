# How-To: CloudShift mit Rootless Podman über die interne Registry betreiben

Dieses Dokument beschreibt, wie die CloudShift-Container auf einer Oracle Linux / RHEL VM unter einem unprivilegierten (rootless) Benutzer betrieben werden, wobei die Container-Images über die interne Firmen-Registry (`docker.registry.it.internal` / Artifactory) bezogen werden.

---

## 1. Architektur & Funktionsweise

```
+------------------+         +-------------------------------+         +----------------------------+
|    Docker Hub    |  <---   | Interne Registry (Proxy)      |  <---   | Linux VM (Zielsystem)      |
|  (docker.io)     |         | (docker.registry.it.internal) |         | Rootless User: 'container' |
+------------------+         +-------------------------------+         +----------------------------+
  Images liegen hier           Cacht Images on-demand                     Zieht Images via Proxy:
  - thesolution/cloudshift     (Artifactory Remote Repo)                  - docker.registry.it.internal/
  - thesolution/...-dashboard                                               thesolution/cloudshift:...
```

1. Neue Images werden vom Entwickler-Mac nach **Docker Hub** gepusht.
2. Die VM im Firmennetz fragt die **interne Registry** an: `docker.registry.it.internal/thesolution/...`.
3. Die interne Registry lädt das Image automatisch von Docker Hub nach, speichert es im Cache und liefert es an die VM aus.

---

## 2. System-Voraussetzungen auf der VM

Gemäß der Unternehmensrichtlinie (*PODMAN rootless setup on Linux*):

* **OS:** Oracle Linux / RHEL 8 oder neuer (mit RHCK-Kernel und cgroup v2).
* **Benutzer:** Eigener unprivilegierter OS-User, standardmäßig: **`container`**.
* **Filesystem:** Dediziertes Filesystem gemountet unter **`/appl/containers`** (10–50 GB).
* **Linger-Modus:** Aktiviert via `loginctl enable-linger container` (Container laufen auch nach SSH-Logout weiter).
* **Port-Regel:** `net.ipv4.ip_unprivileged_port_start=443`
  - Der Rootless-User darf Ports **>= 443** binden (z. B. 443, 7667, 13306).
  - Ports **unter 443 (wie Port 80)** sind für Rootless-User gesperrt!

---

## 3. Vorbereitung auf der VM

### 3.1 Als Container-User anmelden
```bash
sudo su - container
# oder direkt per SSH als Benutzer 'container' einloggen
```

### 3.2 Temporäres Verzeichnis für Image-Downloads einrichten
Um den Fehler `no space left on device` beim Entpacken großer Container-Blobs unter `/var/tmp` zu vermeiden, legen wir einen Temp-Ordner im großen `/appl/containers`-Dateisystem an:

```bash
mkdir -p /appl/containers/tmp
export TMPDIR=/appl/containers/tmp

# Dauerhaft in ~/.bashrc des Users 'container' hinterlegen:
echo 'export TMPDIR=/appl/containers/tmp' >> ~/.bashrc
```

### 3.3 SSH-Verzeichnis für den Worker vorbereiten
Der `coriolis-worker` Container bindet standardmäßig `~/.ssh` ein:
```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
```

---

## 4. Projektverzeichnis & Dateien bereitstellen

Das Projektverzeichnis gehört in das dedizierte Filesystem unter `/appl/containers/`:

```bash
mkdir -p /appl/containers/cloudshift
cd /appl/containers/cloudshift
```

### Benötigte Dateistruktur:
Kopiere folgende Dateien aus dem Repository auf die VM:

```text
/appl/containers/cloudshift/
├── docker-compose.podman.yml     <-- Speziell angepasste Compose-Datei
├── docker/
│   ├── coriolis.conf            <-- Coriolis Hauptkonfiguration
│   ├── users.yaml               <-- Benutzer/Auth-Konfiguration
│   └── dashboard/
│       ├── nginx.conf           <-- Nginx Konfiguration
│       ├── ssl/                 <-- Zertifikate (cert.crt, cert.key)
│       └── ...                  <-- Dashboard Web-Assets
└── etc/
    └── coriolis/
        ├── api-paste.ini        <-- Paste-Deploy Pipeline
        └── policy.yaml          <-- RBAC Berechtigungen
```

---

## 5. Besonderheiten der `docker-compose.podman.yml`

Die Datei [`docker-compose.podman.yml`](../docker-compose.podman.yml) ist bereits für diese Umgebung vorkonfiguriert:

1. **Image-Quellen:** Alle Images verweisen auf `docker.registry.it.internal/...`.
2. **Ports:** 
   - Dashboard HTTPS: Port `443:443` (erlaubt da >= 443).
   - Dashboard HTTP: Auf Port `8080:80` umgeleitet (Port 80 wird vermieden).
   - API: Port `7667:7667`.
   - MariaDB: Port `13306:3306`.
3. **Keine lokalen Build-Schritte:** Vorkompilierte Images werden direkt bezogen.
4. **SELinux-Flags:** Alle gemounteten Volumes besitzen das `:z`-Flag.

---

## 6. Container-Betrieb

### 6.1 Images vorab manuell testen / pullen (optional)
```bash
podman pull docker.registry.it.internal/thesolution/cloudshift:latest
podman pull docker.registry.it.internal/thesolution/cloudshift-dashboard:latest
```

### 6.2 Stack starten
```bash
cd /appl/containers/cloudshift

podman-compose -f docker-compose.podman.yml up -d
# Alternativ, falls podman compose als Plugin vorhanden ist:
# podman compose -f docker-compose.podman.yml up -d
```

### 6.3 Status und Healthchecks überprüfen
```bash
podman ps
```
Alle Container sollten den Status `Up` (und MariaDB/RabbitMQ `healthy`) aufweisen.

### 6.4 Logs überwachen
```bash
# Alle Logs mitverfolgen:
podman-compose -f docker-compose.podman.yml logs -f

# Spezifische Logs (z. B. DB-Sync oder API):
podman logs -f coriolis-db-sync
podman logs -f coriolis-api
```

### 6.5 Stack stoppen / neustarten
```bash
# Stoppen:
podman-compose -f docker-compose.podman.yml down

# Neustart eines einzelnen Dienstes (z. B. Conductor):
podman restart coriolis-conductor
```

---

## 7. Zugriff auf CloudShift

* **Web Dashboard:** `https://<VM-IP-oder-Hostname>`
  *(bzw. HTTP unter `http://<VM-IP-oder-Hostname>:8080`)*
* **REST API:** `http://<VM-IP-oder-Hostname>:7667`

---

## 8. Troubleshooting

### Problem 1: `no image found in image index for architecture "amd64"`
* **Ursache:** Das Image wurde auf dem Entwickler-Mac als ARM64 gebaut und zu Docker Hub geladen, oder die interne Registry hat noch das alte ARM64-Manifest im Cache.
* **Lösung:** 
  1. Auf dem Mac mit `--platform linux/amd64` neu bauen und mit einem Versions-Tag (z. B. `v1.0.1`) nach Docker Hub pushen.
  2. Auf der VM das Image mit dem neuen Tag ziehen:
     ```bash
     podman pull docker.registry.it.internal/thesolution/cloudshift:v1.0.1
     ```

### Problem 2: `no space left on device` beim Image-Pull
* **Ursache:** `/var/tmp` auf der Root-Partition (`/`) ist voll.
* **Lösung:**
  ```bash
  rm -rf /var/tmp/container_images_storage*
  export TMPDIR=/appl/containers/tmp
  podman system prune -a
  ```

### Problem 3: `permission denied` beim Binden von Port 80
* **Ursache:** Der Rootless-Modus erlaubt laut Kernel-Konfiguration erst Ports ab 443.
* **Lösung:** Sicherstellen, dass in `docker-compose.podman.yml` für das Dashboard Port `443:443` oder `8080:80` verwendet wird, keinesfalls `80:80`.
