# CloudShift Dashboard & Web-UI

Das CloudShift Web-Dashboard bietet eine moderne, reaktive Benutzeroberfläche zur Steuerung von Multi-Hypervisor-Migrationen, Endpunktverwaltung und Echtzeit-Überwachung.

---

## Architektur

Der Stack besteht aus folgenden Docker-Containern:
- **mariadb**: Metadaten-Datenbank
- **rabbitmq**: Nachrichten-Broker für Task- und RPC-Kommunikation
- **api**: Coriolis REST-API mit JWT-TokenAuth & RBAC (Port 7667)
- **conductor, worker, scheduler, minion-manager, deployer-manager**: Migration-Orchestrierung und Task-Execution
- **dashboard**: Nginx-Webserver für das Dashboard & Swagger-Explorer (Port 8080)

---

## Installation & Betrieb

### Voraussetzungen
- Docker & Docker Compose
- Mindestens 4 GB RAM für den vollständigen Stack
- Konfiguration aus den Vorlagen anlegen (die echten Dateien sind nicht im Git) und alle `<CHANGE_ME>`/`<PBKDF2_HASH>` ersetzen:
  ```bash
  cp .env.example .env && chmod 600 .env
  cp docker/coriolis.conf.example docker/coriolis.conf
  cp docker/users.yaml.example docker/users.yaml
  ```
  `.env` enthält die Passwörter für MariaDB und RabbitMQ. Sie müssen zu den URLs in `docker/coriolis.conf` passen (`[database] connection`, `transport_url`).
  Fehlt eine der Dateien, legt Docker beim Start an ihrer Stelle ein leeres Verzeichnis an und die Dienste starten nicht.
- TLS-Zertifikat für das Dashboard in `docker/dashboard/ssl/` (nicht im Git, wird zur Laufzeit eingebunden):
  - `cert.crt`: Serverzertifikat inkl. Zwischenzertifikat(e), Serverzertifikat zuerst
  - `cert.key`: privater Schlüssel ohne Passphrase (`chmod 600`)

  Für Tests genügt ein selbstsigniertes Zertifikat:
  ```bash
  mkdir -p docker/dashboard/ssl
  openssl req -x509 -newkey rsa:3072 -nodes -days 365 \
    -keyout docker/dashboard/ssl/cert.key -out docker/dashboard/ssl/cert.crt \
    -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
  ```
  Für den Betrieb ein Zertifikat der internen CA verwenden (CSR mit allen Hostnamen/IPs im SAN).

### Bestehende Installation aktualisieren (einmalig nach dem 25.09.2026)

`main`/`master` wurden neu geschrieben, und `docker/coriolis.conf`, `docker/users.yaml` und `docker/dashboard/ssl/` sind nicht mehr im Git. Ein normales `git pull` schlägt fehl, ein `git reset --hard` würde diese Dateien löschen. Stattdessen im Repo-Verzeichnis **vor** dem Update ausführen:

```bash
sh docker/migrate-untracked-config.sh            # Remote/Branch optional: origin main
```

Das Skript sichert die Konfiguration nach `.config-backup-<Zeitstempel>/`, legt `.env` aus den bisherigen Compose-Werten an, setzt den Branch auf den Remote-Stand und stellt die Dateien wieder her. Liegt das Skript im alten Stand noch nicht vor, vorher einzeln holen: `git fetch origin && git show origin/main:docker/migrate-untracked-config.sh > /tmp/migrate.sh && sh /tmp/migrate.sh`. Den Backup-Ordner nach erfolgreichem Start löschen, er enthält Zugangsdaten.

### Starten des Stacks

1. **Stack starten (inkl. Dashboard & Swagger)**:
   ```bash
   docker-compose up -d
   # bzw. mit Podman:
   podman-compose up -d
   ```

2. **Dashboard separat starten / neu starten**:
   ```bash
   docker-compose up -d dashboard
   # bzw. mit Podman:
   podman-compose up -d dashboard
   ```

---

## Zugriff & Benutzer

Nach dem Start ist das Dashboard unter folgender Adresse erreichbar:

- **Web Dashboard (HTTPS)**: [https://localhost](https://localhost) (Port 443)
- **Web Dashboard (HTTP)**: [http://localhost](http://localhost) (Port 80)
- **Swagger API Explorer**: `https://localhost/dashboard/swagger.html`
- **REST-API**: `http://localhost:7667/v1`

### Benutzer (`/etc/coriolis/users.yaml`)

Die Benutzer und ihre Passwort-Hashes stehen in `docker/users.yaml` (nicht im Git). Vorlage mit Anleitung zum Erzeugen der Hashes: `docker/users.yaml.example`. Typische Rollen:

| Benutzername | Rolle | Berechtigungen |
| :--- | :--- | :--- |
| `admin` | `admin` | Vollzugriff: Endpunkte, Migrationen, System-Konfiguration (`coriolis.conf`, `policy.yaml`, `users.yaml`), Systemdienste |
| `operator` | `operator` | Operativer Betrieb: Endpunkte und Migrationen anlegen, ausführen, cancellen und deployen |
| `viewer` | `viewer` | Nur Lesezugriff: Migrationen, Endpunkte und Logs einsehen. Schreibaktionen sind in der UI deaktiviert |

---

## Funktionen des Dashboards

### 1. Authentifizierung & Sitzungsverwaltung
- **Dark-Theme Login-Overlay**: Direkte Anmeldung beim Öffnen der Seite.
- **Benutzerprofil & Rollenanzeige**: Anzeige des angemeldeten Benutzers mit farblich codiertem Badge (`admin`, `operator`, `viewer`) im Header.
- **Logout-Funktion**: Beenden der Sitzung und Löschen des JWT-Tokens im Speicher.
- **Automatischer Session-Timeout-Handling**: 401-Interception mit Hinweismeldung und automatischer Weiterleitung zum Login.

### 2. Rollenbasierte Oberfläche (RBAC)
- **Viewer-Modus**: Buttons zum Erstellen, Bearbeiten oder Löschen von Migrationen und Endpunkten werden automatisch deaktiviert. Ein dezentes Informations-Banner weist auf den Lesemodus hin.
- **Operator-Modus**: Freigabe für alle Migrations- und Endpunktaufgaben. Systemkonfigurations-Optionen bleiben Administratoren vorbehalten.

### 3. Unterstützte Hypervisoren & Endpunkttypen
- **VMware vSphere** (Quelle & Ziel / Reverse Migration)
- **Oracle OLVM / oVirt** (Ziel mit automatischer VLAN-Netzwerkprovisionierung & Quelle)
- **Microsoft Hyper-V** (Ziel via WinRM mit Gen1/Gen2-Unterstützung und vSwitch-Mapping)
- **Proxmox VE** (Ziel via Proxmox REST-API mit QEMU/KVM und VirtIO)

### 4. Swagger API Explorer
- Integrierte interaktive Dokumentation unter `/dashboard/swagger.html`.
- Unterstützung für Bearer-Token Autorisierung (`Authorize`-Button) zum direkten Testen geschützter REST-Endpunkte.

---

## Entwicklung & Hot-Reload

Das Dashboard ist als Single-Page-Applikation (`app.js`, `index.html`, `style.css`) aufgebaut und wird per Docker-Volume in den Nginx-Container gemountet:
- Änderungen an `docker/dashboard/app.js`, `index.html` oder `style.css` werden sofort ohne Container-Rebuild im Browser wirksam (ggf. Browser-Cache leeren).

---

## Fehlerbehebung

- **Dashboard nicht erreichbar**: Prüfen, ob der Container läuft: `docker-compose ps dashboard`.
- **401 Unauthorized bei API-Aufrufen**: Überprüfen, ob das Token abgelaufen ist. Über das Tür-Icon oben rechts abmelden und erneut anmelden.
- **LDAP-Login schlägt fehl**: Einstellungen in `coriolis.conf` unter `[ldap]` (Server-URL, Bind-DN, Zertifikate) prüfen und Log im API-Container kontrollieren: `docker-compose logs -f api`.

---

## Lizenz

Apache License 2.0. Copyright (c) thesolution.at & Cloudbase Solutions SRL.
