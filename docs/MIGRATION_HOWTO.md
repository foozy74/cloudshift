# How-To: VMware vSphere zu Oracle OLVM Migration mit Coriolis

Diese Anleitung führt Sie Schritt für Schritt durch den gesamten Migrationsprozess einer virtuellen Maschine von VMware vSphere (Quelle) nach Oracle OLVM (Ziel) unter Verwendung der laufenden Coriolis-Installation auf `sb-v2v` (`172.23.219.61`).

---

## 1. Vorbereitungen

### A. Netzwerk & Zugriffe
* Die Coriolis-Container müssen das vCenter über Port `443` sowie die ESXi-Hosts über Port `902` erreichen können.
* Die Coriolis-Container müssen die OLVM/oVirt Engine über Port `443` erreichen können.
* Die temporäre Minion-VM auf OLVM muss über das Netzwerk mit den Coriolis-Containern (Port `6677` und `4433`) kommunizieren können.
* **Proxy-Bypass:** Interne Netze (`172.23.0.0/16`) müssen in `NO_PROXY` hinterlegt sein (in `ProviderSession` ist der Proxy automatisch deaktiviert).

### B. OLVM Minion-Template bereitstellen
Coriolis benötigt auf der Ziel-OLVM-Plattform ein minimales OS-Template zur Erstellung der temporären Worker-VMs (Minions):
1. Erstellen Sie eine minimale virtuelle Maschine in OLVM (z. B. mit Oracle Linux 8/9) mit installiertem `qemu-guest-agent`.
2. **CPU-Kompatibilität:** Das Cluster (z. B. `sb1`) bzw. Template muss mindestens ein **`x86-64-v3`** (AVX2)-fähiges CPU-Modell besitzen (z. B. Intel Skylake/CascadeLake/IceLake oder AMD EPYC), damit `glibc` in modernen Gast-Betriebssystemen während des OS-Morphings fehlerfrei läuft.
3. Fahren Sie die VM herunter und konvertieren Sie diese in OLVM in ein **Template** (z. B. Name: `template-sb-Minion`).
4. **Template-Name konfigurieren:**
   * **Global in `docker/coriolis.conf`:**
     ```ini
     [olvm]
     minion_template_name = template-sb-Minion
     minion_vcpus = 2
     minion_memory_mb = 4096
     ```
   * **Oder pro Migration in der `destination_environment`:**
     ```json
     "destination_environment": {
       "cluster_id": "sb1",
       "storage_domain_id": "olvm-sb1",
       "minion_template_name": "template-sb-Minion"
     }
     ```

### C. VMware Worker-VM & Automatisches HotAdd
Auf VMware-Seite dient die bestehende Worker-VM `sb-v2v` als Daten-Proxy. Coriolis hängt die VMDK-Festplatten der Quell-VM per HotAdd vollautomatisch an diese Worker-VM an und liest sie konsistent aus einem temporären Snapshot aus:
```ini
[vmware]
worker_ip = 172.23.219.61
worker_vm_name = sb-v2v
auto_attach_disks = True
worker_ssh_password = VMware.99
```

---

## 2. Schritt-für-Schritt Migrationsanleitung

### Schritt 2.1: VMware-Quell-Endpunkt in Coriolis registrieren

Registrieren Sie Ihre VMware-Umgebung als Quelle:

```bash
curl -i -X POST "http://172.23.219.61:7667/v1/endpoints" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: fake-admin-token" \
  -d '{
    "endpoint": {
      "name": "vsphere-source",
      "type": "vmware_vsphere",
      "description": "VMware vCenter Quellumgebung",
      "connection_info": {
        "host": "vc-mgc.sdn.it.internal",
        "username": "administrator@vsphere.local",
        "password": "your-vcenter-password",
        "allow_untrusted": true
      }
    }
  }'
```
*Notieren Sie sich die ID des Endpunkts aus der Antwort (`"id": "<vsphere-endpoint-uuid>"`).*

---

### Schritt 2.2: OLVM-Ziel-Endpunkt in Coriolis registrieren

Registrieren Sie Ihre Oracle OLVM-Umgebung als Ziel:

```bash
curl -i -X POST "http://172.23.219.61:7667/v1/endpoints" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: fake-admin-token" \
  -d '{
    "endpoint": {
      "name": "olvm-destination",
      "type": "olvm",
      "description": "Oracle OLVM Zielumgebung",
      "connection_info": {
        "url": "https://sb-ovirt.sdn.it.internal/ovirt-engine/",
        "username": "admin@internal",
        "password": "your-olvm-password",
        "insecure": true
      }
    }
  }'
```
*Notieren Sie sich die ID des Endpunkts (`"id": "<olvm-endpoint-uuid>"`).*

---

### Schritt 2.3: Migrations-Job (Transfer) erstellen

Definieren Sie den Transfer mit den Mappings für Cluster, Storage-Domain und Netzwerke:

```bash
curl -i -X POST "http://172.23.219.61:7667/v1/transfers" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: fake-admin-token" \
  -d '{
    "transfer": {
      "name": "migration-sbl13155t",
      "scenario": "replica",
      "origin_endpoint_id": "<vsphere-endpoint-uuid>",
      "destination_endpoint_id": "<olvm-endpoint-uuid>",
      "instances": ["sbl13155t"],
      "source_environment": {
        "shutdown_instances": true
      },
      "destination_environment": {
        "cluster_id": "sb1",
        "storage_domain_id": "olvm-sb1",
        "network_map": {
          "sb_3tier_mgc_appl": "sb_3tier_appl"
        }
      }
    }
  }'
```
*Notieren Sie sich die Transfer-ID (`"id": "<transfer-uuid>"`).*

---

### Schritt 2.4: Erste Replikation starten (Vollsync)

Startet den ersten Datenabgleich im laufenden Betrieb der Quell-VM:

```bash
curl -i -X POST "http://172.23.219.61:7667/v1/transfers/<transfer-uuid>/executions" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: fake-admin-token" \
  -d '{"execution": {}}'
```

---

### Schritt 2.5: Status des Migrations-Jobs überwachen

```bash
curl -s "http://172.23.219.61:7667/v1/transfers/<transfer-uuid>" \
  -H "X-Auth-Token: fake-admin-token" | python3 -m json.tool
```
Sobald die Replikation abgeschlossen ist, steht die Execution auf `COMPLETED`.

---

### Schritt 2.6: Finaler Cutover (Shutdown, Delta-Sync & OS-Morphing)

Führen Sie den Cutover im Wartungsfenster mit Shutdown der VMware-VM und automatischem Deployment auf OLVM aus:

```bash
curl -i -X POST "http://172.23.219.61:7667/v1/transfers/<transfer-uuid>/executions" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: fake-admin-token" \
  -d '{
    "execution": {
      "shutdown_instances": true,
      "auto_deploy": true
    }
  }'
```

**Was Coriolis automatisch ausführt:**
1. Fährt die VM im vCenter sauber per `ShutdownGuest()` herunter.
2. Überträgt die letzten geänderten Blöcke (Delta) in wenigen Sekunden.
3. Startet den temporären OS-Morphing-Minion:
   - Installiert `qemu-guest-agent`.
   - Deinstalliert `open-vm-tools`.
   - Bindet KVM VirtIO-Treiber in `initramfs` ein.
   - Konfiguriert Netzwerk & GRUB-Bootloader.
4. Hängt die Festplatten an die neue VM auf OLVM an (sauber benannt als `<VM>_<DISK_ID>`) und startet sie.

---

## 3. Fehlerdiagnose und Logdateien

Sollte es bei einem Schritt zu Verzögerungen oder Fehlern kommen, können Sie die Log-Ausgaben der jeweiligen Coriolis-Container auf dem Server direkt einsehen:

```bash
# Worker-Logs (Führt Datentransfer, HotAdd und OS-Morphing aus)
podman logs -f coriolis-worker

# Conductor-Logs (Orchestrierung und Task-Abfolge)
podman logs -f coriolis-conductor

# API-Logs (REST-API Anfragen und Responses)
podman logs -f coriolis-api
```
