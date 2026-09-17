# How-To: VMware vSphere zu Oracle OLVM Migration mit Coriolis

Diese Anleitung führt Sie Schritt für Schritt durch den gesamten Migrationsprozess einer virtuellen Maschine von VMware vSphere (Quelle) nach Oracle OLVM (Ziel) unter Verwendung der laufenden Coriolis-Installation auf `172.23.219.54`.

---

## 1. Vorbereitungen

### A. Netzwerk & Zugriffe
* Die Coriolis-Container müssen das vCenter über Port `443` sowie die ESXi-Hosts über Port `902` erreichen können.
* Die Coriolis-Container müssen die OLVM/oVirt Engine über Port `443` erreichen können.
* Die temporäre Minion-VM auf OLVM muss über das Netzwerk mit den Coriolis-Containern (Port `6677` und `4433`) kommunizieren können.

### B. OLVM Minion-Template bereitstellen
Coriolis benötigt auf der Ziel-OLVM-Plattform ein minimales OS-Template zur Erstellung der temporären Worker-VMs (Minions):
1. Erstellen Sie eine minimale virtuelle Maschine in OLVM (z. B. mit Oracle Linux 8/9 oder CentOS) mit installiertem `qemu-guest-agent`.
2. Installieren Sie das Betriebssystem, konfigurieren Sie SSH und stellen Sie sicher, dass keine graphische Oberfläche aktiv ist.
3. Fahren Sie die VM herunter und konvertieren Sie diese in OLVM in ein **Template** (z. B. Name: `sb-minion-template` oder `coriolis-minion-template`).
4. **Template-Name konfigurieren:**
   * **Global in `coriolis.conf`:**
     ```ini
     [olvm]
     minion_template_name = sb-minion-template
     ```
   * **Oder pro Migration in der `destination_environment`:**
     ```json
     "destination_environment": {
       "cluster_name": "Default",
       "storage_domain": "data",
       "minion_template_name": "sb-minion-template"
     }
     ```

### C. VMware Worker-VM & Automatisches HotAdd
Auf VMware-Seite dient eine bestehende Worker-VM (z. B. `sb-v2v`) als Daten-Proxy. Coriolis hängt die VMDK-Festplatten der Quell-VM per HotAdd vollautomatisch an diese Worker-VM an:
```ini
[vmware]
worker_ip = 172.23.219.61
worker_vm_name = sb-v2v
auto_attach_disks = True
```

---

## 2. Schritt-für-Schritt Migrationsanleitung

### Schritt 2.1: VMware-Quell-Endpunkt in Coriolis registrieren

Registrieren Sie Ihre VMware-Umgebung als Quelle. Ersetzen Sie die IP-Adresse, den Benutzernamen und das Passwort durch Ihre vCenter-Zugangsdaten.

**API-Aufruf:**
```bash
curl -i -X POST -H "Content-Type: application/json" -H "X-Project-Id: admin" \
  -d '{
    "endpoint": {
      "name": "vsphere-source",
      "type": "vmware_vsphere",
      "description": "VMware vCenter Source Environment",
      "connection_info": {
        "host": "vcenter.ihredomaene.local",
        "username": "administrator@vsphere.local",
        "password": "vcenter_passwort",
        "allow_untrusted": true
      }
    }
  }' http://172.23.219.54:7667/v1/admin/endpoints
```
*Die Antwort enthält eine JSON-Struktur. Notieren Sie sich die ID des Endpunkts (z. B. `"id": "c1a2b3c4-d5e6-f7g8-h9i0-j1k2l3m4n5o6"`).*

---

### Schritt 2.2: OLVM-Ziel-Endpunkt in Coriolis registrieren

Registrieren Sie Ihre Oracle OLVM-Umgebung als Ziel.

**API-Aufruf:**
```bash
curl -i -X POST -H "Content-Type: application/json" -H "X-Project-Id: admin" \
  -d '{
    "endpoint": {
      "name": "olvm-destination",
      "type": "olvm",
      "description": "Oracle OLVM Destination Environment",
      "connection_info": {
        "url": "https://olvm-engine.ihredomaene.local/ovirt-engine/",
        "username": "admin@internal",
        "password": "olvm_passwort",
        "insecure": true
      }
    }
  }' http://172.23.219.54:7667/v1/admin/endpoints
```
*Die Antwort enthält ebenfalls eine ID. Notieren Sie sich diese (z. B. `"id": "z9y8x7w6-v5u4-t3s2-r1q0-p9o8n7m6l5k4"`).*

---

### Schritt 2.3: Migrations-Job (Transfer) erstellen

Erstellen Sie den Migrations-Job. Passen Sie hierbei die Namen der VMs, des OLVM-Zielclusters, der Storage-Domains und der Netzwerke an.

*   `origin_endpoint_id`: Die Quell-Endpoint-ID aus Schritt 2.1
*   `destination_endpoint_id`: Die Ziel-Endpoint-ID aus Schritt 2.2
*   `instances`: Liste der VM-Namen, wie sie im vCenter heißen.
*   `network_map`: Mapping der VMware-Portgruppe auf das logische OLVM-Netzwerk.
*   `storage_mappings`: Mapping des VMware-Datastores auf die OLVM Storage Domain.

**API-Aufruf:**
```bash
curl -i -X POST -H "Content-Type: application/json" -H "X-Project-Id: admin" \
  -d '{
    "transfer": {
      "origin_endpoint_id": "c1a2b3c4-d5e6-f7g8-h9i0-j1k2l3m4n5o6",
      "destination_endpoint_id": "z9y8x7w6-v5u4-t3s2-r1q0-p9o8n7m6l5k4",
      "source_environment": {
        "worker_vm_name": "sb-v2v",
        "worker_ip": "172.23.219.61",
        "auto_attach_disks": true
      },
      "destination_environment": {
        "cluster_name": "Default",
        "storage_domain": "data",
        "minion_template_name": "sb-minion-template"
      },
      "instances": [
        "webserver-prod-01"
      ],
      "network_map": {
        "VM Network": "ovirtmgmt"
      },
      "storage_mappings": {
        "datastore1": "data"
      }
    }
  }' http://172.23.219.54:7667/v1/admin/transfers
```
*Notieren Sie sich die ID des erstellten Transfers aus der API-Antwort (z. B. `"id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6"`).*

---

### Schritt 2.4: Erste Replikation starten (Spiegelung der Disks)

Starten Sie die Replikation. Dies kopiert alle Daten der Festplatten im laufenden Betrieb der Quell-VM.

**API-Aufruf:**
```bash
curl -i -X POST -H "Content-Type: application/json" -H "X-Project-Id: admin" \
  -d '{"execute": null}' \
  http://172.23.219.54:7667/v1/admin/transfers/a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6/actions
```

---

### Schritt 2.5: Status des Migrations-Jobs überwachen

Sie können den Fortschritt und Status der Datenübertragung jederzeit abfragen.

**API-Aufruf:**
```bash
curl -i -H "X-Project-Id: admin" \
  http://172.23.219.54:7667/v1/admin/transfers/a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6
```
Suchen Sie in der Ausgabe nach `"status"`. Der Status wechselt von `PENDING` auf `RUNNING` und schließlich auf `COMPLETED`, sobald die erste Datenübertragung abgeschlossen ist.

---

### Schritt 2.6: Finales Deployment (Cutover) ausführen

Sobald die Replikation abgeschlossen ist, können Sie das finale Deployment starten. 
*Hierbei wird die Quell-VM auf VMware-Seite heruntergefahren, ein letzter differentieller Disk-Sync durchgeführt, das OS Morphing durchgeführt und die VM auf OLVM gestartet.*

**API-Aufruf:**
```bash
curl -i -X POST -H "Content-Type: application/json" -H "X-Project-Id: admin" \
  -d '{
    "deploy": {
      "force": true,
      "shutdown_instances": true
    }
  }' \
  http://172.23.219.54:7667/v1/admin/transfers/a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6/actions
```

---

## 3. Fehlerdiagnose und Logdateien einsehen

Sollte es bei einem Schritt zu Verzögerungen oder Fehlern kommen, können Sie die Log-Ausgaben der jeweiligen Coriolis-Container auf dem Server direkt einsehen.

Verbinden Sie sich per SSH auf den Server `172.23.219.54` und führen Sie folgende Befehle aus:

*   **API-Logs** (WSGI, HTTP-Anfragen):
    ```bash
    podman logs -f coriolis-api
    ```
*   **Conductor-Logs** (Orchestrierung und Ablaufsteuerung):
    ```bash
    podman logs -f coriolis-conductor
    ```
*   **Worker-Logs** (Führt die eigentlichen Kopier- und API-Aktionen aus):
    ```bash
    podman logs -f coriolis-worker
    ```
*   **Minion-Manager-Logs** (Erstellung und Steuerung der Hilfs-VMs):
    ```bash
    podman logs -f coriolis-minion-manager
    ```
