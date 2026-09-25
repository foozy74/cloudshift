# VMware vSphere → Oracle OLVM — Implementierungsplan

## Übersicht

Dieser Plan beschreibt, was implementiert werden muss, um VMware vSphere → Oracle OLVM Migrationen mit Coriolis zu ermöglichen.

Da beide Provider (VMware Export, OLVM Import) **nicht** im Open-Source Coriolis-Repo enthalten sind, müssen ca. 3000-4000 Zeilen Python-Code geschrieben werden.

---

## Phase 1: Setup & Vorbereitung (1-2 Tage)

### Aufgaben

- [ ] Coriolis-Repository klonen und lokal installieren
- [ ] `pyvmomi` und `ovirt-engine-sdk-python` installieren
- [ ] SSH-Key für Minion-Zugriff generieren
- [ ] Coriolis-Konfiguration (`/etc/coriolis/coriolis.conf`) anlegen
- [ ] MariaDB und RabbitMQ starten
- [ ] `coriolis-dbsync upgrade` ausführen
- [ ] Schnelltest: `tox -e py3` läuft durch

### Zu lesende Dateien (Referenz implementierung)

| Datei | Zweck |
|---|---|
| `coriolis/providers/base.py` | Alle abstrakten Basisklassen (1495 Zeilen) |
| `coriolis/tests/integration/test_provider/exp.py` | Referenz Export Provider (Test) |
| `coriolis/tests/integration/test_provider/imp.py` | Referenz Import Provider (Test) |
| `coriolis/providers/factory.py` | Provider-Registrierung (86 Zeilen) |
| `coriolis/providers/replicator.py` | Replicator-Klasse (960 Zeilen) |
| `coriolis/providers/backup_writers.py` | Backup Writer (1218 Zeilen) |
| `coriolis/tasks/replica_tasks.py` | Task-Pipeline (43833 Bytes) |
| `coriolis/schemas/vm_export_info_schema.json` | VM-Export-Schema |
| `coriolis/schemas/replication_worker_conn_info_schema.json` | SSH-Connection-Schema |
| `coriolis/schemas/disk_sync_resources_conn_info_schema.json` | Backup-Writer-Connection-Schema |
| `coriolis/schemas/os_morphing_resources_schema.json` | OS-Morphing-Ressourcen-Schema |
| `coriolis/constants.py` | Typ-Konstanten |

---

## Phase 2: VMware vSphere Export Provider (5-8 Tage)

### 2.1 Provider-Struktur

```
coriolis/providers/vmware/
├── __init__.py
└── exp.py             # VMwareVSphereExportProvider (~700-900 Zeilen)
```

### 2.2 Zu implementierende Methoden

**MUSS implementiert (13 abstrakte Methoden):**

| # | Methode | Basis-Klasse | Beschreibung |
|---|---|---|---|
| 1 | `get_connection_info_schema()` | `BaseEndpointProvider` | JSON-Schema: host, username, password |
| 2 | `validate_connection()` | `BaseEndpointProvider` | vCenter Verbindung testen via pyvmomi |
| 3 | `get_instances()` | `BaseEndpointInstancesProvider` | Alle VMs aus vCenter Inventory auflisten |
| 4 | `get_instance()` | `BaseEndpointInstancesProvider` | Einzelne VM-Details abrufen |
| 5 | `get_networks()` | `BaseEndpointNetworksProvider` | Port Groups auflisten |
| 6 | `get_storage()` | `BaseEndpointStorageProvider` | Datastores auflisten |
| 7 | `get_source_environment_options()` | `BaseEndpointSourceOptionsProvider` | Optionen (z.B. shutdown) |
| 8 | `get_source_environment_schema()` | `BaseExportInstanceProvider` | JSON-Schema für source_environment |
| 9 | `get_replica_instance_info()` | `BaseReplicaExportProvider` | **KERN**: VM-Export-Info (Disks, NICs, CPU, RAM) |
| 10 | `deploy_replica_source_resources()` | `BaseReplicaExportProvider` | Source-Minion deployen |
| 11 | `delete_replica_source_resources()` | `BaseReplicaExportProvider` | Source-Minion aufräumen |
| 12 | `replicate_disks()` | `BaseReplicaExportProvider` | **KERN**: Disk-Daten via Replicator + Backup Writer übertragen |
| 13 | `shutdown_instance()` | `BaseReplicaExportProvider` | Quell-VM herunterfahren |
| 14 | `delete_replica_source_snapshots()` | `BaseReplicaExportProvider` | Snapshots löschen |
| 15 | `get_os_morphing_tools()` | `BaseInstanceProvider` | Source-OS-Morphing-Tools (leer lassen) |
| 16 | `validate_replica_export_input()` | `BaseReplicaExportValidationProvider` | Export-Parameter validieren |

### 2.3 Technische Entscheidungen

**Disk-Transfer-Strategie:**

Der **Replicator** (Coriolis-bord-eigener Disk-Chunker) benötigt die Quell-Disks als **Block-Devices** auf einer Linux-Minion. Für vSphere gibt es mehrere Ansätze:

| Ansatz | Komplexität | Vorteil | Nachteil |
|---|---|---|---|
| **A: Temporäre VM auf ESXi** | Hoch | Direkter Zugriff auf VMDK via RDM | Braucht ESXi SSH + OVF-Tool |
| **B: vCenter Datastore-Mount** | Mittel | Keine extra VM nötig | vCenter erlaubt kein Mount von VMDK via NFS |
| **C: SSH-Tunnel direkt auf ESXi** | Hoch | Nutzt ESXi interne Tools | `vmkfstools` Export erlaubt kein Block-Level Lesen |
| **D: Coriolis qemu_reader auf Worker** | Mittel | Nutzt libqemu.so, liest VMDK über HTTP/API | Braucht Zugriff auf VMDK-Datei via Datastore-Pfad |

**Empfohlen: Ansatz A** — Temporäre Linux-Worker-VM auf einem ESXi-Host deployen (via OVF Tool oder SSH + Template). Die VMDK-Dateien werden per `vmkfstools -i` oder als RDM an die Worker-VM durchgereicht.

### 2.4 Abhängigkeiten

```python
import pyVmomi            # vSphere SDK
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import paramiko           # SSH zu ESXi Hosts
```

---

## Phase 3: OLVM/oVirt Import Provider (7-10 Tage)

### 3.1 Provider-Struktur

```
coriolis/providers/olvm/
├── __init__.py
└── imp.py                # OLVMoVirtImportProvider (~1000-1300 Zeilen)
```

### 3.2 Zu implementierende Methoden

**MUSS implementiert (20 Methoden):**

| # | Methode | Basis-Klasse | Beschreibung |
|---|---|---|---|
| 1 | `get_connection_info_schema()` | `BaseEndpointProvider` | JSON-Schema: url, username, password, ca_bundle |
| 2 | `validate_connection()` | `BaseEndpointProvider` | oVirt Engine Verbindung testen |
| 3 | `get_target_environment_schema()` | `BaseEndpointDestinationOptionsProvider` | JSON-Schema: cluster_id, storage_domain_id |
| 4 | `get_target_environment_options()` | `BaseEndpointDestinationOptionsProvider` | Cluster, Storage, Networks als Optionen |
| 5 | `get_networks()` | `BaseEndpointNetworksProvider` | Logical Networks auflisten |
| 6 | `get_storage()` | `BaseEndpointStorageProvider` | Storage Domains auflisten |
| 7 | `get_optimal_flavor()` | `BaseInstanceFlavorProvider` | Besten Instance-Type/Flavor wählen |
| 8 | `deploy_replica_disks()` | `BaseReplicaImportProvider` | Ziel-Disks in Storage Domain erstellen |
| 9 | `deploy_replica_target_resources()` | `BaseReplicaImportProvider` | **KERN**: Minion + Backup Writer deployen |
| 10 | `delete_replica_target_resources()` | `BaseReplicaImportProvider` | Minion aufräumen |
| 11 | `delete_replica_disks()` | `BaseReplicaImportProvider` | Replika-Disks löschen |
| 12 | `deploy_replica_instance()` | `BaseReplicaImportProvider` | **KERN**: Ziel-VM erstellen (CPU, RAM, NICs, Disks) |
| 13 | `finalize_replica_instance_deployment()` | `BaseReplicaImportProvider` | VM starten, finalen Status zurückgeben |
| 14 | `cleanup_failed_replica_instance_deployment()` | `BaseReplicaImportProvider` | Fehlgeschlagene VM löschen |
| 15 | `deploy_os_morphing_resources()` | `BaseImportInstanceProvider` | **KERN**: Morphing-Minion mit Ziel-Disks deployen |
| 16 | `delete_os_morphing_resources()` | `BaseImportInstanceProvider` | Morphing-Minion aufräumen, Disks zurück |
| 17 | `create_replica_disk_snapshots()` | `BaseReplicaImportProvider` | oVirt Disk Snapshots erstellen |
| 18 | `delete_replica_target_disk_snapshots()` | `BaseReplicaImportProvider` | Snapshots löschen |
| 19 | `restore_replica_disk_snapshots()` | `BaseReplicaImportProvider` | Snapshots wiederherstellen |
| 20 | `validate_replica_import_input()` | `BaseReplicaImportValidationProvider` | Import-Parameter validieren |
| 21 | `validate_replica_deployment_input()` | `BaseReplicaImportValidationProvider` | Deployment-Parameter validieren |
| 22 | `check_update_destination_environment_params()` | `BaseUpdateDestinationReplicaProvider` | Update-Kompatibilität prüfen |
| 23 | `get_os_morphing_tools()` | `BaseInstanceProvider` | KVM-OS-Morphing-Tools |

### 3.3 Abhängigkeiten

```python
import ovirtsdk4 as sdk                # oVirt Engine SDK v4
from ovirtsdk4 import types
```

### 3.4 oVirt REST API Mapping

| oVirt Typ | Verwendung |
|---|---|
| `types.Cluster` | Welcher Ziel-Cluster |
| `types.StorageDomain` | Persistenter Speicher für Disks |
| `types.Disk` | Festplatten-Images (RAW oder qcow2, sparse) |
| `types.Nic` / `types.VnicProfile` | Netzwerk-Schnittstellen |
| `types.Vm` | Virtuelle Maschine |
| `types.DiskAttachment` | Disk an VM gebunden |
| `types.DiskSnapshot` | Disk-Snapshot für schnelleres Deployment |
| `types.InstanceType` | VM-Größen-Vorlage |

---

## Phase 4: Worker-Minion-Template & Integration (2-3 Tage)

### 4.1 Minion-Template erstellen

Ein Linux-VM-Template auf OLVM, das für Worker-Minions verwendet wird:

```bash
# Template-Anforderungen:
# - Oracle Linux 8/9 oder Ubuntu 22.04+
# - SSH-Key für Root-Zugriff vorinstalliert
# - ca. 20 GB Boot-Disk
# - cloud-init konfiguriert
# - DHCP für Netzwerk

# coriolis-writer Binary muss auf dem Template liegen
# Oder: per SSH auf das Template kopieren beim Deployment
```

### 4.2 SSH-Key-Management

```bash
# Schlüsselpaar generieren (einmalig)
ssh-keygen -t ed25519 -f /etc/coriolis/minion_key -N ""

# Public-Key in Minion-Template einbauen (/root/.ssh/authorized_keys, 600,
# .ssh 700, SELinux: restorecon -Rv /root/.ssh)
```

Im Docker-Setup liegt der Private Key unter `secrets/olvm_minion_ssh_key` und wird als Compose-Secret nur in den Worker eingebunden (`minion_ssh_key_path = /run/secrets/olvm_minion_ssh_key`). Details: [MIGRATION_HOWTO.md](MIGRATION_HOWTO.md), Abschnitt B.

### 4.3 Backup-Writer-Integration

Der `HTTPBackupWriterBootstrapper` aus `coriolis/providers/backup_writers.py` erledigt:

1. SFTP-Upload der `coriolis-writer` Binary
2. TLS-Zertifikatsgenerierung auf dem Minion
3. Systemd-Service-Erstellung
4. Firewall-Freigabe für Port 6677

### 4.4 SQLAlchemy-Migrationen

Falls neue Datenbank-Felder benötigt werden:

```bash
# Migration erstellen
cd coriolis/db/sqlalchemy/migrate_repo/
python -m migrate create NewFeatureName sqlalchemy_migrate

# In der generierten Datei upgrade/downgrade implementieren
```

---

## Phase 5: Integrationstests (5-7 Tage)

### 5.1 Unit Tests

Test-Ansatz: Jede Provider-Methode mit Mock-Objekten testen.

| Test | Was wird getestet |
|---|---|
| `test_vmware_connect` | vCenter Verbindung / Fehlerbehandlung |
| `test_vmware_get_instances` | VM-Listing korrekt |
| `test_vmware_get_instance_info` | Export-Info-Struktur korrekt |
| `test_vmware_replicate_disks` | Replicator + Writer Interaktion |
| `test_olvm_connect` | oVirt Engine Verbindung |
| `test_olvm_create_disks` | Disk-Erstellung in Storage Domain |
| `test_olvm_deploy_instance` | VM-Erstellung korrekt |
| `test_olvm_os_morphing` | Morphing-Minion-Lebenszyklus |

### 5.2 Integration Tests (nach Provider-Entwicklung)

```bash
# Integrationstests ausführen (benötigt root + scsi_debug + Docker)
sudo -E tox -e integration
```

---

## Phase 6: Dokumentation & Deployment (2-3 Tage)

- [ ] Provider-Konfiguration dokumentieren
- [ ] Endpoint-Konfiguration dokumentieren
- [ ] Troubleshooting-Guide schreiben
- [ ] Backup/Recovery-Plan dokumentieren
- [ ] Sicherheit: Secrets-Management via Barbican dokumentieren

---

## Geschätzter Gesamtaufwand

| Phase | Tage | Abhängigkeiten |
|---|---|---|
| 1: Setup & Vorbereitung | 1-2 | Keine |
| 2: VMware vSphere Export Provider | 5-8 | Phase 1 |
| 3: OLVM/oVirt Import Provider | 7-10 | Phase 1 |
| 4: Minion-Template & Integration | 2-3 | Phase 2+3 |
| 5: Integrationstests | 5-7 | Phase 2+3 |
| 6: Dokumentation & Deployment | 2-3 | Phase 2+3+4+5 |
| **Total** | **22-33 Arbeitstage** | |

---

## Risiken & Abhängigkeiten

| Risiko | Wahrscheinlichkeit | Auswirkung | Mitigation |
|---|---|---|---|
| vCenter API-Änderungen in vSphere 8 | Niedrig | Mittel | pyvmomi Abstraktionsschicht |
| oVirt SDK 4.5 API-Inkompatibilitäten | Mittel | Hoch | Direkte REST-API als Fallback |
| ESXi SSH-Zugriff blockiert | Hoch (Sicherheitsrichtlinie) | Sehr hoch | OVF/OVA-Tool als Alternative |
| Minion-VM hat keine Block-Device-Sicht auf VMDK | Mittel | Hoch | RDM oder vmkfstools Convert |
| Netzwerk-Latenz zwischen Source/Target Minions | Mittel | Niedrig | Kompression aktivieren |
| OS-Morphing schlägt fehl | Mittel | Mittel | `skip_os_morphing: true` als Workaround |

---

## Referenzen

- oVirt SDK Python: https://github.com/oVirt/ovirt-engine-sdk
- pyvmomi: https://github.com/vmware/pyvmomi
- Coriolis: https://github.com/cloudbase/coriolis
- Coriolis Client: https://github.com/cloudbase/python-coriolisclient
- OLVM Docs: https://docs.oracle.com/en/virtualization/oracle-linux-virtualization-manager/
