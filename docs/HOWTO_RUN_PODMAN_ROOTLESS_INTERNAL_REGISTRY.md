# How-To: CloudShift mit Rootless Podman über die interne Registry betreiben

Dieses Dokument beschreibt die Neuinstallation von CloudShift auf einer Oracle Linux / RHEL VM unter einem unprivilegierten (rootless) Benutzer. Die Container-Images kommen über die interne Firmen-Registry (`docker.registry.it.internal` / Artifactory).

Für ein **Update einer bestehenden Installation** (Stand vor dem 25.09.2026) siehe [Abschnitt 10](#10-bestehende-installation-aktualisieren).

---

## Inhalt

1. [Architektur](#1-architektur)
2. [Voraussetzungen auf der VM (root)](#2-voraussetzungen-auf-der-vm-root)
3. [Projekt bereitstellen](#3-projekt-bereitstellen)
4. [Geheimnisse und Konfiguration anlegen](#4-geheimnisse-und-konfiguration-anlegen)
5. [Images holen und Stack starten](#5-images-holen-und-stack-starten)
6. [Prüfen](#6-prüfen)
7. [Autostart nach Reboot](#7-autostart-nach-reboot)
8. [Netzwerk und Firewall](#8-netzwerk-und-firewall)
9. [Betrieb](#9-betrieb)
10. [Bestehende Installation aktualisieren](#10-bestehende-installation-aktualisieren)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Architektur

```
+------------------+         +-------------------------------+         +----------------------------+
|    Docker Hub    |  <---   | Interne Registry (Proxy)      |  <---   | Linux VM (Zielsystem)      |
|  (docker.io)     |         | (docker.registry.it.internal) |         | Rootless User: 'container' |
+------------------+         +-------------------------------+         +----------------------------+
  Images liegen hier           Cacht Images on-demand                     Zieht Images via Proxy:
  - thesolution/cloudshift     (Artifactory Remote Repo)                  - docker.registry.it.internal/
  - thesolution/...-dashboard                                               thesolution/cloudshift:...
```

1. Neue Images werden vom Entwickler-Mac nach **Docker Hub** gepusht (siehe [HOWTO_BUILD_AND_PUSH_DOCKERHUB.md](HOWTO_BUILD_AND_PUSH_DOCKERHUB.md)).
2. Die VM fragt die **interne Registry** an: `docker.registry.it.internal/thesolution/...`.
3. Die Registry lädt das Image von Docker Hub nach, cacht es und liefert es an die VM aus.

**Was nicht im Image und nicht im Git liegt** (wird auf der VM angelegt und zur Laufzeit eingebunden):

| Datei | Inhalt | Vorlage |
|---|---|---|
| `.env` | Passwörter MariaDB/RabbitMQ, Erlang-Cookie | `.env.example` |
| `docker/coriolis.conf` | Hauptkonfiguration inkl. DB-/RabbitMQ-URL, JWT-Schlüssel, VMware-Worker-Passwort | `docker/coriolis.conf.example` |
| `docker/users.yaml` | Dashboard-/API-Benutzer mit Passwort-Hashes | `docker/users.yaml.example` |
| `docker/dashboard/ssl/cert.crt`, `cert.key` | TLS-Zertifikat für das Dashboard | – (interne CA) |
| `secrets/olvm_minion_ssh_key` | Privater SSH-Key für die OLVM-Minions | – |

---

## 2. Voraussetzungen auf der VM (root)

Gemäß der Unternehmensrichtlinie (*PODMAN rootless setup on Linux*):

* **OS:** Oracle Linux / RHEL 8 oder neuer (mit RHCK-Kernel und cgroup v2).
* **Pakete:** `podman`, `podman-compose` (aktuelle Version, unterstützt `secrets:`), `git`, `openssl`.
* **Benutzer:** Eigener unprivilegierter OS-User, standardmäßig **`container`**.
* **Filesystem:** Dediziertes Filesystem unter **`/appl/containers`** (10–50 GB).
* **Linger-Modus:** `loginctl enable-linger container` (Container laufen nach dem SSH-Logout weiter, User-Units starten beim Boot).
* **Port-Regel:** `net.ipv4.ip_unprivileged_port_start=443`
  - Der Rootless-User darf Ports **>= 443** binden (z. B. 443, 7667, 13306).
  - Ports **unter 443 (wie Port 80)** sind gesperrt, HTTP läuft deshalb auf `8080`.

---

## 3. Projekt bereitstellen

```bash
sudo su - container

# Temp-Verzeichnis im großen Filesystem (vermeidet "no space left on device" beim Pull)
mkdir -p /appl/containers/tmp
echo 'export TMPDIR=/appl/containers/tmp' >> ~/.bashrc
export TMPDIR=/appl/containers/tmp

# Projekt holen
git clone https://github.com/foozy74/cloudshift.git /appl/containers/cloudshift
cd /appl/containers/cloudshift
```

Benötigt werden aus dem Repository nur: `docker-compose.podman.yml`, `.env.example`, `docker/` (Vorlagen, `dashboard/nginx.conf`) und `etc/coriolis/` (`api-paste.ini`, `policy.yaml`). Ohne Git-Zugang können diese Dateien auch kopiert werden.

---

## 4. Geheimnisse und Konfiguration anlegen

> **Neue Werte verwenden.** Passwörter, JWT-Schlüssel und Zertifikate, die früher im Repository standen, gelten als kompromittiert und dürfen nicht wiederverwendet werden.

> **Alle Dateien vor dem ersten Start anlegen.** Fehlt eine eingebundene Datei, legt Podman an ihrer Stelle ein leeres Verzeichnis an und die Dienste starten nicht.

### 4.1 Compose-Secrets (`.env`)

```bash
cp .env.example .env
chmod 600 .env
openssl rand -hex 24      # je einmal für DB_ROOT_PASSWORD, DB_PASSWORD, RABBITMQ_PASSWORD, RABBITMQ_ERLANG_COOKIE
vi .env
```

### 4.2 Hauptkonfiguration (`docker/coriolis.conf`)

```bash
cp docker/coriolis.conf.example docker/coriolis.conf
vi docker/coriolis.conf
```

Diese Werte müssen **zur `.env` passen**:

| Option | Wert |
|---|---|
| `[DEFAULT] transport_url`, `messaging_transport_url` | `rabbit://<RABBITMQ_USER>:<RABBITMQ_PASSWORD>@rabbitmq:5672/` |
| `[database] connection` | `mysql+pymysql://coriolis:<DB_PASSWORD>@database/coriolis?charset=utf8` |

Außerdem setzen:

| Option | Wert |
|---|---|
| `[auth] jwt_secret_key` | neu erzeugen: `openssl rand -hex 32` |
| `[vmware] worker_ip`, `worker_vm_name`, `worker_ssh_password` | VMware-Worker-VM (HotAdd-Proxy) |
| `[olvm] minion_template_name` | Name des Minion-Templates in OLVM |
| `[olvm] minion_ssh_key_path` | unverändert lassen: `/run/secrets/olvm_minion_ssh_key` |

### 4.3 Benutzer (`docker/users.yaml`)

```bash
cp docker/users.yaml.example docker/users.yaml

# Hash pro Benutzer erzeugen (Passwort wird verdeckt abgefragt)
podman run --rm -it -w / docker.registry.it.internal/thesolution/cloudshift:latest \
  python3 -c "import getpass; from coriolis.auth.local_backend import hash_password; print(hash_password(getpass.getpass()))"

vi docker/users.yaml      # <PBKDF2_HASH> je Benutzer ersetzen
```

Rollen: `admin`, `operator`, `viewer`. Mit `enabled: false` wird ein Benutzer gesperrt.

### 4.4 TLS-Zertifikat (`docker/dashboard/ssl/`)

nginx erwartet genau zwei Dateien:

* `cert.crt`: Serverzertifikat **plus** Zwischenzertifikat(e), das Serverzertifikat zuerst
* `cert.key`: privater Schlüssel **ohne Passphrase**

```bash
mkdir -p docker/dashboard/ssl
cd docker/dashboard/ssl

# Schlüssel und CSR erzeugen (alle Hostnamen/IPs des Dashboards in den SAN)
openssl req -new -newkey rsa:3072 -nodes -keyout cert.key -out cloudshift.csr \
  -subj "/CN=<fqdn>/O=Drei" \
  -addext "subjectAltName=DNS:<fqdn>,DNS:<hostname>,IP:<vm-ip>"
chmod 600 cert.key

# cloudshift.csr bei der internen CA einreichen, danach die Kette zusammenbauen:
cat server.crt intermediate.crt > cert.crt

# Prüfen: beide Hashes müssen gleich sein
openssl x509 -noout -pubkey -in cert.crt | openssl sha256
openssl pkey -pubout -in cert.key | openssl sha256
cd -
```

Nur für Tests: ein selbstsigniertes Zertifikat, siehe `DASHBOARD_README.md`.

### 4.5 SSH-Key für die OLVM-Minions (`secrets/`)

Coriolis verbindet sich als `root` per SSH-Key mit den Minion-VMs.

```bash
# Schlüsselpaar ohne Passphrase (RSA, Ed25519 oder ECDSA)
mkdir -p secrets
ssh-keygen -t ed25519 -N "" -f secrets/olvm_minion_ssh_key
chmod 600 secrets/olvm_minion_ssh_key
```

Den **öffentlichen** Schlüssel (`secrets/olvm_minion_ssh_key.pub`) im OLVM-Minion-Template hinterlegen: `/root/.ssh/authorized_keys` (Rechte 600, `.ssh` 700, `restorecon -Rv /root/.ssh`). Anschließend das Template neu erzeugen. Details: [MIGRATION_HOWTO.md](MIGRATION_HOWTO.md), Abschnitt B.

Ein anderer Ort für den privaten Schlüssel lässt sich über `OLVM_MINION_SSH_KEY_FILE` in `.env` setzen.

### 4.6 Kontrolle

```bash
ls -l .env docker/coriolis.conf docker/users.yaml docker/dashboard/ssl/cert.crt \
      docker/dashboard/ssl/cert.key secrets/olvm_minion_ssh_key
grep -c '<CHANGE_ME>\|<PBKDF2_HASH>' .env docker/coriolis.conf docker/users.yaml   # überall 0
```

---

## 5. Images holen und Stack starten

```bash
podman login docker.registry.it.internal      # falls die Registry eine Anmeldung verlangt
podman-compose -f docker-compose.podman.yml pull
podman-compose -f docker-compose.podman.yml up -d
```

Hinweise:

* `.env` wird aus dem Projektverzeichnis gelesen. Den Befehl deshalb immer aus `/appl/containers/cloudshift` starten.
* **Version:** `CLOUDSHIFT_VERSION` in `.env` legt fest, welche Image-Version läuft (Core und Dashboard). Für den Betrieb einen Release-Tag eintragen (z. B. `1.4.0`), nicht `latest`: nur so sind Updates und Rollbacks nachvollziehbar. `CLOUDSHIFT_REGISTRY` ist standardmäßig `docker.registry.it.internal`.
* Alle Dienste außer `db-sync` haben `restart: unless-stopped`, Abstürze beim Start (z. B. wenn der Conductor noch nicht bereit ist) behebt Podman damit selbst.
* Besonderheiten der Compose-Datei: Images von `docker.registry.it.internal`, keine Build-Schritte, `label:disable` bzw. `:z` für SELinux, Ports `443`, `8080`, `7667`, `13306`.

---

## 6. Prüfen

```bash
podman ps -a                                   # coriolis-db-sync: Exited (0), alle anderen: Up
podman logs coriolis-db-sync | tail

curl -sk -o /dev/null -w '%{http_code}\n' https://localhost/                          # 200
curl -s  -o /dev/null -w '%{http_code}\n' http://localhost:7667/v1/admin/transfers    # 401 (ohne Login erwartet)
podman exec coriolis-worker ls -l /run/secrets/olvm_minion_ssh_key                   # Secret vorhanden
openssl s_client -connect localhost:443 </dev/null 2>/dev/null | openssl x509 -noout -issuer   # interne CA
```

Danach im Browser `https://<VM-IP-oder-Hostname>/` öffnen und mit einem der neu angelegten Benutzer anmelden.

---

## 7. Autostart nach Reboot

Die `restart:`-Policy greift nur, solange Podman läuft; nach einem Neustart der VM startet rootless Podman die Container nicht von selbst. Dafür eine systemd-User-Unit anlegen (als `container`, Linger muss aktiv sein):

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/cloudshift.service <<'EOF'
[Unit]
Description=CloudShift (podman-compose)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/appl/containers/cloudshift
Environment=TMPDIR=/appl/containers/tmp
ExecStart=/usr/bin/podman-compose -f docker-compose.podman.yml up -d
ExecStop=/usr/bin/podman-compose -f docker-compose.podman.yml down
TimeoutStartSec=600

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable cloudshift.service
```

Den Pfad zu `podman-compose` bei Bedarf mit `command -v podman-compose` anpassen.

---

## 8. Netzwerk und Firewall

| Richtung | Ziel | Port | Zweck |
|---|---|---|---|
| eingehend | VM | 443 | Dashboard (HTTPS) |
| eingehend | VM | 8080 | Dashboard (HTTP) |
| eingehend | VM | 7667 | REST-API |
| ausgehend | vCenter | 443 | VMware-API |
| ausgehend | ESXi-Hosts | 902 | Disk-Zugriff |
| ausgehend | OLVM-Engine | 443 | oVirt-API |
| ausgehend | Minion-VMs auf OLVM | 22, 6677, 4433 | SSH, Backup-Writer, Replicator |

**MariaDB (`13306`) und RabbitMQ (`5672`, `15672`)** werden von der Compose-Datei ebenfalls auf dem Host freigegeben. Die Dienste brauchen das nicht, sie sprechen über das interne Container-Netz. Diese Ports per Firewall sperren.

Interne Netze (`172.23.0.0/16`, `.internal`, `.three.com`) sind in der Compose-Datei bereits als `NO_PROXY` gesetzt.

---

## 9. Betrieb

```bash
# Logs
podman-compose -f docker-compose.podman.yml logs -f
podman logs -f coriolis-api

# Einzelnen Dienst neu starten (z. B. nach Änderung von coriolis.conf)
podman restart coriolis-conductor

# Stack stoppen / starten
podman-compose -f docker-compose.podman.yml down
podman-compose -f docker-compose.podman.yml up -d

```

### 9.1 Update auf eine neue Version

Updates immer mit `docker/upgrade.sh`, nie per `pull` + `up` von Hand:

```bash
cd /appl/containers/cloudshift
git pull                                   # neue Vorlagen, Changelog und Skripte
sh docker/upgrade.sh 1.4.0                 # Zielversion = Release-Tag
```

Das Skript
1. prüft vorab: Images der Zielversion verfügbar, **keine laufende Migration** (`RUNNING`, `CANCELLING`, `AWAITING_MINION_ALLOCATIONS`), mindestens 2 GB frei, Compose-Konfiguration gültig,
2. vergleicht `.env` und `docker/coriolis.conf` mit den Vorlagen (fehlende `.env`-Schlüssel brechen ab, fehlende Konfig-Optionen werden angezeigt) und zeigt die **Upgrade-Hinweise** aus `CHANGELOG.md`,
3. sichert nach `backups/upgrade-<Zeit>-<alt>-to-<neu>/`: Datenbank-Dump, `.env`, `coriolis.conf`, `users.yaml`, und pinnt die laufenden Images unter `rollback-<Zeit>`,
4. setzt `CLOUDSHIFT_VERSION`, erstellt den Stack neu (`db-sync` migriert die Datenbank),
5. prüft: `db-sync` Exit 0, alle Container laufen, API und Dashboard antworten, API läuft mit der neuen Version,
6. rollt bei einem Fehler **automatisch zurück**: alte Images, und bei geändertem Schema der Datenbank-Dump.

Ohne Rückfrage (z. B. in Automatisierung): `sh docker/upgrade.sh 1.4.0 --yes`. Wartezeit für den Healthcheck: `HEALTH_TIMEOUT=600 sh docker/upgrade.sh …`.

Ein **Downgrade** auf eine ältere Version ist nur über das Backup möglich (die ältere Version kennt neuere Migrationen nicht): `backups/…/database.sql.gz` einspielen und `CLOUDSHIFT_VERSION` auf die alte Version setzen.

`backups/` enthält Zugangsdaten und Datenbank-Dumps: nur für `container` lesbar (700), alte Backups regelmäßig löschen.

**Passwort ändern:** neue Werte in `.env` **und** `docker/coriolis.conf` eintragen. MariaDB übernimmt `DB_PASSWORD` nur bei der Erstinitialisierung, bei einer bestehenden Datenbank zusätzlich `ALTER USER 'coriolis'@'%' IDENTIFIED BY '<neu>';` ausführen. Danach den Stack neu starten.

---

## 10. Bestehende Installation aktualisieren

Für Installationen mit dem Stand **vor dem 25.09.2026**: `main` wurde neu geschrieben, und `coriolis.conf`, `users.yaml` und `ssl/` sind nicht mehr im Git. Ein `git pull` schlägt fehl, ein `git reset --hard` würde die Dateien löschen. Stattdessen:

```bash
cd /appl/containers/cloudshift
git fetch origin
git show origin/main:docker/migrate-untracked-config.sh > /tmp/migrate.sh
sh /tmp/migrate.sh                     # sichert die Konfiguration, legt .env an, aktualisiert, stellt wieder her
podman-compose -f docker-compose.podman.yml up -d
rm -rf .config-backup-*                # erst wenn alles läuft (enthält Zugangsdaten)
```

Danach die Abschnitte [4.5](#45-ssh-key-für-die-olvm-minions-secrets) (Minion-Key als Secret statt `~/.ssh`) und [7](#7-autostart-nach-reboot) ergänzen und die früher veröffentlichten Zugangsdaten tauschen.

---

## 11. Troubleshooting

### `no image found in image index for architecture "amd64"`
* **Ursache:** Das Image wurde nur für ARM64 gebaut, oder die interne Registry hat noch ein altes Manifest im Cache.
* **Lösung:** Multi-Arch bauen (`--platform linux/amd64,linux/arm64`), mit neuem Versions-Tag pushen und diesen Tag ziehen:
  ```bash
  podman pull docker.registry.it.internal/thesolution/cloudshift:<neuer-tag>
  ```

### `no space left on device` beim Image-Pull
* **Ursache:** `/var/tmp` auf der Root-Partition ist voll.
* **Lösung:**
  ```bash
  rm -rf /var/tmp/container_images_storage*
  export TMPDIR=/appl/containers/tmp
  podman system prune -a
  ```

### `permission denied` beim Binden von Port 80
* **Ursache:** Rootless darf erst Ports ab 443 binden.
* **Lösung:** Für das Dashboard `443:443` oder `8080:80` verwenden, nie `80:80`.

### `required variable DB_ROOT_PASSWORD is missing a value`
* **Ursache:** `.env` fehlt oder der Befehl wurde nicht im Projektverzeichnis gestartet.
* **Lösung:** `cd /appl/containers/cloudshift` und `.env` nach [4.1](#41-compose-secrets-env) anlegen.

### Dienst startet nicht, `is a directory` im Log
* **Ursache:** Eine eingebundene Datei (`coriolis.conf`, `users.yaml`, Zertifikat) fehlte beim Start, und Podman hat stattdessen ein Verzeichnis angelegt.
* **Lösung:** Stack stoppen, das leere Verzeichnis löschen, die Datei nach [Abschnitt 4](#4-geheimnisse-und-konfiguration-anlegen) anlegen, neu starten.

### Dashboard: `cannot load certificate` (nginx startet nicht)
* **Ursache:** `docker/dashboard/ssl/cert.crt` oder `cert.key` fehlt, der Schlüssel hat eine Passphrase oder passt nicht zum Zertifikat.
* **Lösung:** Dateien nach [4.4](#44-tls-zertifikat-dockerdashboardssl) prüfen und `podman restart coriolis-dashboard`.

### Login schlägt fehl
* **Ursache:** In `users.yaml` steht Klartext oder ein falsch kopierter Hash, oder `jwt_secret_key` wurde geändert (bestehende Sitzungen werden ungültig).
* **Lösung:** Hash neu erzeugen ([4.3](#43-benutzer-dockerusersyaml)), `podman restart coriolis-api`, im Browser neu anmelden.

### Migration hängt beim Minion (SSH)
* **Ursache:** Der öffentliche Schlüssel fehlt im Minion-Template, oder das Secret ist nicht im Worker angekommen.
* **Lösung:** `podman exec coriolis-worker ls -l /run/secrets/olvm_minion_ssh_key` prüfen und das Template nach [4.5](#45-ssh-key-für-die-olvm-minions-secrets) kontrollieren.
