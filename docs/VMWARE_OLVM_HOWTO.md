# VMware vSphere → Oracle OLVM Migration — HOWTO

## Inhaltsverzeichnis

1. [Installation Coriolis](#1-installation-coriolis)
2. [Konfiguration Coriolis](#2-konfiguration-coriolis)
3. [Provider-Implementierung: VMware vSphere Export Provider](#3-provider-implementierung-vmware-vsphere-export-provider)
4. [Provider-Implementierung: OLVM/oVirt Import Provider](#4-provider-implementierung-olvmovirt-import-provider)
5. [Provider-Registrierung & Start](#5-provider-registrierung--start)
6. [Endpoints einrichten](#6-endpoints-einrichten)
7. [Migration durchführen](#7-migration-durchführen)

---

## 1 Installation Coriolis

### 1.1 System-Abhängigkeiten

```bash
# Ubuntu 22.04+
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv \
    rabbitmq-server mariadb-server qemu-utils make gcc git

# Oder Oracle Linux 8/9
sudo dnf install -y python3 python3-pip python3-venv \
    rabbitmq-server mariadb-server qemu-img make gcc git
```

### 1.2 Clone & Setup

```bash
git clone https://github.com/cloudbase/coriolis.git
cd coriolis

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel

# Dependencies installieren
pip install -r requirements.txt
pip install -r test-requirements.txt

# Externes Coriolis Client SDK
pip install git+https://github.com/cloudbase/python-coriolisclient.git

# Import-Abhängigkeiten für Provider
pip install pyvmomi ovirt-engine-sdk-python

# Entwicklungsmodus installieren
pip install -e .
```

### 1.3 Datenbank initialisieren

```bash
# MariaDB-Datenbank erstellen
mysql -u root -p <<EOF
CREATE DATABASE coriolis;
CREATE USER 'coriolis'@'localhost' IDENTIFIED BY 'password';
GRANT ALL PRIVILEGES ON coriolis.* TO 'coriolis'@'localhost';
FLUSH PRIVILEGES;
EOF

# Schema-Migrationen ausführen
coriolis-dbsync --config-file /etc/coriolis/coriolis.conf upgrade
```

### 1.4 RabbitMQ starten

```bash
sudo systemctl enable rabbitmq-server
sudo systemctl start rabbitmq-server

# Standard-Guest-Account (für Entwicklung)
# Default: guest / guest auf localhost:5672
```

---

## 2 Konfiguration Coriolis

### 2.1 Konfigurationsdatei (`/etc/coriolis/coriolis.conf`)

```ini
[DEFAULT]
# Debug-Logging
debug = true
verbose = true
default_requests_timeout = 600

# Messaging (RabbitMQ)
transport_url = rabbit://guest:guest@127.0.0.1:5672/

# Provider-Liste (nach Provider-Implementierung)
providers = coriolis.providers.vmware.exp.VMwareVSphereExportProvider,\
            coriolis.providers.olvm.imp.OLVMoVirtImportProvider

# ========== Datenbank ==========

[database]
connection = mysql+pymysql://coriolis:password@127.0.0.1/coriolis?charset=utf8

# ========== API ==========

[api]
api_migration_listen = 0.0.0.0
api_migration_listen_port = 7667

# ========== Replicator ==========

[replicator]
port = 4433
default_requests_timeout = 600

# ========== VMware (Export / Quelle) ==========

[vmware]
worker_ip = 172.23.219.61
worker_vm_name = sb-v2v
auto_attach_disks = True
worker_ssh_password = <CHANGE_ME>

# ========== OLVM / oVirt (Import / Ziel) ==========

[olvm]
# Name des Templates in der OLVM/oVirt-Engine für Minion-VMs:
minion_template_name = sb-minion-template
# Privater SSH-Key für root-Zugriff auf den Minion (Public Key im Template)
minion_ssh_key_path = /etc/coriolis/minion_key
minion_memory_mb = 4096
minion_vcpus = 2
writer_port = 6677

# ========== Keystone (optional, für Produktion) ==========

[keystone_authtoken]
www_authenticate_uri = http://keystone:5000/
auth_url = http://keystone:5000/
auth_type = password
project_domain_name = Default
user_domain_name = Default
project_name = service
username = coriolis
password = password

# ========== Barbican (optional, für Secret Storage) ==========

[barbican]
auth_endpoint = http://keystone:5000/v3
auth_username = coriolis
auth_password = password
auth_project_name = service
auth_user_domain_name = Default
auth_project_domain_name = Default
```

### 2.2 Services starten

Für Entwicklung/Testing alle Dienste im Vordergrund starten:

```bash
coriolis-api --config-file /etc/coriolis/coriolis.conf
coriolis-conductor --config-file /etc/coriolis/coriolis.conf
coriolis-worker --config-file /etc/coriolis/coriolis.conf
coriolis-scheduler --config-file /etc/coriolis/coriolis.conf
coriolis-minion-manager --config-file /etc/coriolis/coriolis.conf
coriolis-deployer-manager --config-file /etc/coriolis/coriolis.conf
coriolis-transfer-cron --config-file /etc/coriolis/coriolis.conf
```

Oder als systemd-Services (Debian-Paket aus `debian/`):

```bash
sudo systemctl start coriolis-api coriolis-conductor coriolis-worker \
    coriolis-scheduler coriolis-minion-manager coriolis-deployer-manager \
    coriolis-transfer-cron
```

---

## 3 Provider-Implementierung: VMware vSphere Export Provider

### 3.1 Übersicht

Der Export Provider verbindet sich zum vCenter, listet VMs auf, exportiert Disk-/Netzwerk-Informationen und orchestriert den Daten-Transfer via Coriolis Replicator.

**Abhängigkeiten:** `pyvmomi` (VMware SDK), `paramiko` (SSH)

### 3.2 Dateien

```
coriolis/providers/vmware/
├── __init__.py        # Leer
└── exp.py             # VMwareVSphereExportProvider
```

### 3.3 `__init__.py`

```python
# VMware vSphere Provider Package
```

### 3.4 `exp.py` — Vollständiger Provider

```python
# Copyright 2024 YourCompany
# All Rights Reserved.

import logging
import os
import tempfile
import time

from oslo_config import cfg
from oslo_log import log as logging

from coriolis import constants
from coriolis import context
from coriolis import exception
from coriolis.providers import base
from coriolis.providers import backup_writers
from coriolis.providers import replicator as replicator_mod

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

vmware_opts = [
    cfg.IntOpt('replicator_port',
               default=4433,
               help='Port for the coriolis-replicator service'),
    cfg.IntOpt('writer_port',
               default=6677,
               help='Port for the backup writer service'),
    cfg.StrOpt('worker_template',
               default=None,
               help='OVF/OVA path or VM template name for worker VMs'),
]
CONF.register_opts(vmware_opts, group='vmware')


class VMwareVSphereExportProvider(
        base.BaseEndpointProvider,
        base.BaseEndpointInstancesProvider,
        base.BaseEndpointSourceOptionsProvider,
        base.BaseEndpointNetworksProvider,
        base.BaseEndpointStorageProvider,
        base.BaseReplicaExportValidationProvider,
        base.BaseUpdateSourceReplicaProvider,
        base.BaseExportInstanceProvider,
        base.BaseReplicaExportProvider,
):
    platform = "vmware_vsphere"

    def __init__(self, event_manager):
        self._event_manager = event_manager
        super().__init__(event_manager)

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_vcenter_session(self, connection_info):
        """Erstellt eine pyvmomi-Verbindung zum vCenter."""
        from pyVim.connect import SmartConnect, Disconnect
        from pyVmomi import vim

        host = connection_info["host"]
        username = connection_info["username"]
        password = connection_info["password"]
        allow_untrusted = connection_info.get("allow_untrusted", True)

        si = SmartConnect(
            host=host,
            user=username,
            pwd=password,
            disableSslCertValidation=allow_untrusted,
        )
        return si

    def _find_vm_by_name(self, si, name):
        """Findet eine VM anhand ihres Namens oder ihrer ID im vCenter."""
        from pyVmomi import vim

        content = si.RetrieveContent()
        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.VirtualMachine], True)

        for vm in container.view:
            if vm.name == name or vm._moId == name:
                container.Destroy()
                return vm

        container.Destroy()
        raise exception.NotFound(
            f"VM '{name}' not found in vCenter inventory")

    def _vm_to_instance_dict(self, vm):
        """Konvertiert ein vim.VirtualMachine-Objekt in das instance_info-
        Format von Coriolis (gemäss vm_instance_info_schema.json)."""
        return {
            "id": vm._moId,
            "name": vm.name,
            "num_cpu": vm.config.hardware.numCPU,
            "memory_mb": vm.config.hardware.memoryMB,
            "os_type": self._vsphere_os_to_coriolis_os(
                vm.config.guestId),
            "firmware_type": "EFI" if self._is_efi(vm.config) else "BIOS",
            "guest_id": vm.config.guestId,
        }

    def _vsphere_os_to_coriolis_os(self, guest_id):
        """Mappt vSphere Guest IDs auf Coriolis OS-Typen."""
        if guest_id:
            gl = guest_id.lower()
            if "win" in gl:
                return "windows"
            elif "linux" in gl or gl in ("rhel", "centos", "ubuntu",
                                          "debian", "suse", "oracle"):
                return "linux"
            elif "bsd" in gl or "freebsd" in gl:
                return "bsd"
            elif "darwin" in gl or "mac" in gl:
                return "osx"
            elif "solaris" in gl or "oracle" in gl:
                return "solaris"
        return "other"

    def _is_efi(self, config):
        """Prüft ob die VM mit EFI oder BIOS bootet."""
        from pyVmomi import vim
        fw = config.firmware
        return fw in ("efi", vim.vm.GuessedOperatingSystem.guestOsFamilyEfi)

    def _has_nested_virt(self, config):
        """Prüft ob verschachtelte Virtualisierung aktiv ist."""
        try:
            return config.flags.get("vvm", False) or \
                config.nestedHVEnabled
        except Exception:
            return False

    def _get_datastore_name(self, datastore):
        """Liest den Datastore-Namen aus einem Datastore-Objekt."""
        return datastore.name if datastore else "unknown"

    def _get_network_name(self, network):
        """Liest den Netzwerk-Namen aus einem Network-Objekt."""
        return network.name if network else "unknown"

    # ------------------------------------------------------------------
    # BaseEndpointProvider
    # ------------------------------------------------------------------

    def get_connection_info_schema(self):
        return {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "vCenter FQDN oder IP",
                },
                "username": {
                    "type": "string",
                    "description": "vCenter SSO Benutzername",
                },
                "password": {
                    "type": "string",
                    "secret": True,
                    "description": "Passwort",
                },
                "allow_untrusted": {
                    "type": "boolean",
                    "default": True,
                    "description": "SSL-Zertifikatsprüfung deaktivieren",
                },
            },
            "required": ["host", "username", "password"],
        }

    def validate_connection(self, ctxt, connection_info):
        """Testet die Verbindung zum vCenter."""
        from pyVim.connect import Disconnect
        si = self._get_vcenter_session(connection_info)
        try:
            content = si.RetrieveContent()
            LOG.info("Connected to vCenter: %s",
                     content.about.fullName)
        finally:
            Disconnect(si)

    # ------------------------------------------------------------------
    # BaseEndpointInstancesProvider
    # ------------------------------------------------------------------

    def get_instances(self, ctxt, connection_info, source_environment,
                      limit=None, last_seen_id=None,
                      instance_name_pattern=None, refresh=False):
        """Listet alle VMs aus dem vCenter Inventory."""
        from pyVim.connect import Disconnect
        from pyVmomi import vim

        si = self._get_vcenter_session(connection_info)
        content = si.RetrieveContent()

        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.VirtualMachine], True)

        instances = []
        for vm in container.view:
            entry = self._vm_to_instance_dict(vm)
            if instance_name_pattern:
                if instance_name_pattern not in vm.name:
                    continue
            instances.append(entry)

            if limit and len(instances) >= limit:
                break

        container.Destroy()
        Disconnect(si)
        return instances

    def get_instance(self, ctxt, connection_info, source_environment,
                     instance_name):
        """Detaillierte Information einer einzelnen VM."""
        from pyVim.connect import Disconnect
        si = self._get_vcenter_session(connection_info)
        vm = self._find_vm_by_name(si, instance_name)
        instance = self._vm_to_instance_dict(vm)
        Disconnect(si)
        return instance

    # ------------------------------------------------------------------
    # BaseEndpointNetworksProvider
    # ------------------------------------------------------------------

    def get_networks(self, ctxt, connection_info, env):
        from pyVim.connect import Disconnect
        from pyVmomi import vim
        si = self._get_vcenter_session(connection_info)
        content = si.RetrieveContent()
        networks = []
        for net in content.viewManager.CreateContainerView(
                content.rootFolder, [vim.Network], True).view:
            networks.append({"id": net._moId, "name": net.name})
        Disconnect(si)
        return networks

    # ------------------------------------------------------------------
    # BaseEndpointStorageProvider
    # ------------------------------------------------------------------

    def get_storage(self, ctxt, connection_info, target_environment):
        from pyVim.connect import Disconnect
        from pyVmomi import vim
        si = self._get_vcenter_session(connection_info)
        content = si.RetrieveContent()
        datastores = []
        for ds in content.viewManager.CreateContainerView(
                content.rootFolder, [vim.Datastore], True).view:
            datastores.append({
                "id": ds._moId,
                "name": ds.name,
                "additional_provider_properties": {
                    "type": ds.summary.type,
                    "capacity_bytes": ds.summary.capacity,
                    "free_space_bytes": ds.summary.freeSpace,
                },
            })
        Disconnect(si)
        return {"storage_backends": datastores,
                "config_default": None}

    # ------------------------------------------------------------------
    # BaseEndpointSourceOptionsProvider
    # ------------------------------------------------------------------

    def get_source_environment_options(self, ctxt, connection_info,
                                       env=None, option_names=None):
        return [
            {"name": "shutdown_instances",
             "values": [True, False],
             "config_default": True},
        ]

    def get_source_environment_schema(self):
        return {
            "type": "object",
            "properties": {
                "shutdown_instances": {
                    "type": "boolean",
                    "default": True,
                },
            },
            "additionalProperties": False,
        }

    # ------------------------------------------------------------------
    # BaseReplicaExportValidationProvider
    # ------------------------------------------------------------------

    def validate_replica_export_input(self, ctxt, connection_info,
                                      instance_name, source_environment):
        """Prüft, ob die Quell-VM exportierbar ist."""
        from pyVim.connect import Disconnect
        si = self._get_vcenter_session(connection_info)
        vm = self._find_vm_by_name(si, instance_name)

        # Prüfen ob VM existiert und zugänglich ist
        if not vm.config:
            raise exception.InvalidInput(
                f"VM '{instance_name}' has no config (maybe not accessible)")
        Disconnect(si)
        return {}

    # ------------------------------------------------------------------
    # BaseReplicaExportProvider (KERN)
    # ------------------------------------------------------------------

    def get_replica_instance_info(self, ctxt, connection_info,
                                  source_environment, instance_name):
        """Sammelt alle Export-Informationen der VM.

        Rückgabe gemäss vm_export_info_schema.json:
        - id, name, num_cpu, memory_mb, os_type
        - devices.disks[] (id, format, size_bytes, path, storage_backend)
        - devices.nics[] (network_name, mac_address)
        """
        from pyVim.connect import Disconnect
        from pyVmomi import vim

        si = self._get_vcenter_session(connection_info)
        vm = self._find_vm_by_name(si, instance_name)

        disks = []
        nics = []
        cdroms = []
        serial_ports = []
        floppies = []
        controllers = []

        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualDisk):
                disk_entry = {
                    "id": f"disk-{device.key}",
                    "format": "vmdk",
                    "size_bytes": device.capacityInKB * 1024,
                    "unit_number": str(getattr(device, 'unitNumber', 0)),
                    "path": getattr(device.backing, 'fileName', None),
                    "controller_id": self._get_controller_key(device),
                }
                if device.backing and device.backing.datastore:
                    disk_entry["storage_backend_identifier"] = \
                        device.backing.datastore.name
                disks.append(disk_entry)

            elif isinstance(device, vim.vm.device.VirtualEthernetCard):
                network_name = None
                network_id = None
                if device.backing:
                    net_obj = getattr(device.backing, 'network', None)
                    if net_obj:
                        network_name = net_obj.name
                    network_id = getattr(
                        device.backing, 'deviceName', None)
                nics.append({
                    "id": f"nic-{device.key}",
                    "name": device.deviceInfo.label,
                    "network_name": network_name,
                    "network_id": network_id,
                    "mac_address": getattr(
                        device, 'macAddress', None),
                    "unit_number": str(getattr(
                        device, 'unitNumber', 0)),
                })

            elif isinstance(device, vim.vm.device.VirtualCdrom):
                cdroms.append({
                    "id": f"cdrom-{device.key}",
                    "unit_number": str(getattr(device, 'unitNumber', 0)),
                    "controller_id": self._get_controller_key(device),
                })

            elif isinstance(device, vim.vm.device.VirtualSerialPort):
                serial_ports.append({
                    "id": f"serial-{device.key}",
                })

            elif isinstance(device, vim.vm.device.VirtualFloppy):
                floppies.append({
                    "id": f"floppy-{device.key}",
                    "unit_number": str(getattr(device, 'unitNumber', 0)),
                    "controller_id": self._get_controller_key(device),
                })

            elif isinstance(device, vim.vm.device.VirtualController):
                controllers.append({
                    "id": f"ctrl-{device.key}",
                    "type": self._get_controller_type(device),
                    "bus_number": str(getattr(device, 'busNumber', 0)),
                })

        # Boot Order
        boot_order = []
        try:
            for entry in vm.config.bootOptions.bootOrder or []:
                boot_order.append({
                    "type": str(type(entry).__name__),
                })
        except Exception:
            pass

        export_info = {
            "id": vm._moId,
            "name": vm.name,
            "instance_name": vm.name,
            "num_cpu": vm.config.hardware.numCPU,
            "memory_mb": vm.config.hardware.memoryMB,
            "os_type": self._vsphere_os_to_coriolis_os(
                vm.config.guestId),
            "firmware_type": "EFI" if hasattr(vm.config, "firmware") and
            vm.config.firmware in ("efi",) else "BIOS",
            "secure_boot": False,
            "nested_virtualization": self._has_nested_virt(vm.config),
            "devices": {
                "disks": disks,
                "nics": nics,
                "cdroms": cdroms,
                "serial_ports": serial_ports,
                "floppies": floppies,
                "controllers": controllers,
            },
        }

        if boot_order:
            export_info["boot_order"] = boot_order

        Disconnect(si)
        return export_info

    def _get_controller_key(self, device):
        """Ermittelt den Controller-Key eines Geräts."""
        return f"ctrl-{getattr(device, 'controllerKey', 'unknown')}"

    def _get_controller_type(self, controller):
        """Ermittelt den Controller-Typ."""
        name = type(controller).__name__
        name = name.replace("Virtual", "").replace("Controller", "")
        return name if name else type(controller).__name__

    def deploy_replica_source_resources(self, ctxt, connection_info,
                                        export_info, source_environment):
        """Deployt einen temporären Source-Worker auf dem ESXi-Host.

        Der Worker (eine Linux-VM) hat SSH-Zugriff und die Quell-Disks
        als Block-Devices für den Replicator. Für eine produktive Umgebung
        muss hier die eigentliche Worker-VM auf ESXi deployt werden.
        """
        # Vereinfachte Implementierung für das HOWTO:
        # Geht davon aus, dass ein Worker bereits läuft und die
        # Block-Devices verfügbar sind.
        # In Produktion: Worker-VM auf ESXi deployen (z.B. via OVF Tool).

        worker_ip = source_environment.get(
            "worker_ip", export_info.get("hostname"))
        if not worker_ip:
            raise exception.InvalidInput(
                "worker_ip must be provided in source_environment")

        ssh_pkey = source_environment.get("worker_ssh_pkey")
        ssh_password = source_environment.get("worker_ssh_password")

        return {
            "connection_info": {
                "ip": worker_ip,
                "port": 22,
                "username": source_environment.get(
                    "worker_ssh_user", "root"),
                "password": ssh_password,
                "pkey": ssh_pkey,
            },
            "migr_resources": {
                "worker_ip": worker_ip,
                "esxi_host": source_environment.get("esxi_host"),
            },
        }

    def delete_replica_source_resources(self, ctxt, connection_info,
                                        source_environment,
                                        migr_resources_dict):
        """Source-Worker und temporäre Ressourcen aufräumen."""
        LOG.info("Cleaning up source resources for worker: %s",
                 migr_resources_dict.get("worker_ip"))

    def replicate_disks(self, ctxt, connection_info, source_environment,
                        instance_name, source_resources,
                        source_conn_info, target_conn_info,
                        volumes_info, incremental):
        """Überträgt die Disk-Daten von der Quelle zum Ziel.

        Nutzt den Coriolis Replicator auf dem Source-Minion und den
        Backup Writer (HTTP/SSH) auf dem Destination-Minion.
        """
        # Replicator auf Source-Seite initialisieren
        repl_state = None
        if incremental:
            # Für inkrementelle Syncs: Erwartet dass ReplicaState aus
            # früherem Durchlauf in source_resources gespeichert ist
            repl_state = source_resources.get("replica_state")

        replicator = replicator_mod.Replicator(
            source_conn_info,
            self._event_manager,
            volumes_info,
            repl_state,
            use_compression=False,
        )
        replicator.init_replicator()
        replicator.wait_for_chunks()

        # Source Volume-Pfade auflösen
        source_volumes_info = []
        for vol in volumes_info:
            disk_id = vol["disk_id"]
            disk_path = self._resolve_source_disk_path(
                source_resources, disk_id)
            source_volumes_info.append({
                "disk_id": disk_id,
                "disk_path": disk_path,
            })

        # Backup Writer auf Zielseite verbinden
        writer = backup_writers.BackupWritersFactory(
            target_conn_info, volumes_info).get_writer()

        # Daten übertragen
        updated_volumes = replicator.replicate_disks(
            source_volumes_info, writer)

        # Replica-State für nächsten inkrementellen Sync speichern
        source_resources["replica_state"] = replicator.get_replica_state()

        return updated_volumes

    def _resolve_source_disk_path(self, source_resources, disk_id):
        """Ermittelt den Pfad eines Source-Block-Devices.

        Diese Methode muss die Disk-ID (aus der VM-Export-Info) auf den
        tatsächlichen /dev/xxx Pfad des Block-Devices im Source-Worker
        mappen. Im Produktionsfall werden die VMDK-Dateien der VM als
        Block-Devices an den Worker angebunden (z.B. via RDM oder
        Datastore-Pfad über NFS-Loopback).
        """
        source_resources.get("disk_paths", {}).get(
            disk_id, f"/dev/mapper/coriolis-{disk_id}")

    def delete_replica_source_snapshots(self, ctxt, connection_info,
                                        source_environment, volumes_info):
        """Quell-Snapshots löschen (falls erstellt)."""
        LOG.info("Cleaning up source snapshots")
        return volumes_info

    def shutdown_instance(self, ctxt, connection_info,
                          source_environment, instance_name):
        """Quell-VM herunterfahren vor finalem Sync."""
        from pyVim.connect import Disconnect

        should_shutdown = source_environment.get(
            "shutdown_instances", True)
        if not should_shutdown:
            LOG.info("Skipping shutdown as configured")
            return

        si = self._get_vcenter_session(connection_info)
        vm = self._find_vm_by_name(si, instance_name)

        from pyVmomi import vim
        if vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn:
            LOG.info("VM '%s' is already powered off", instance_name)
            Disconnect(si)
            return

        LOG.info("Shutting down VM '%s'", instance_name)
        if vm.guest.toolsRunningStatus == "guestToolsRunning":
            vm.ShutdownGuest()
            # Warten bis VM aus ist
            for _ in range(120):
                if vm.runtime.powerState == \
                        vim.VirtualMachinePowerState.poweredOff:
                    break
                time.sleep(5)
        else:
            # Kein VMware-Tools — PowerOff erzwingen
            task = vm.PowerOffVM_Task()
            # Auf Task-Ende warten
            import pyVmomi
            while task.info.state not in (
                    pyVmomi.vim.TaskInfo.State.success,
                    pyVmomi.vim.TaskInfo.State.error):
                time.sleep(1)

        Disconnect(si)

    # ------------------------------------------------------------------
    # BaseUpdateSourceReplicaProvider
    # ------------------------------------------------------------------

    def check_update_source_environment_params(self, ctxt, connection_info,
                                                instance_name, volumes_info,
                                                old_params, new_params):
        if not volumes_info:
            return []
        return volumes_info

    # ------------------------------------------------------------------
    # BaseInstanceProvider
    # ------------------------------------------------------------------

    def get_os_morphing_tools(self, os_type, osmorphing_info):
        """Gibt VMware-spezifische OS-Morphing-Tools zurück.

        Diese entfernen VMware Tools aus der Gast-OS und bereiten
        die VM auf den KVM-Betrieb vor.
        """
        return []
```

---

## 4 Provider-Implementierung: OLVM/oVirt Import Provider

### 4.1 Übersicht

Der Import Provider verbindet sich zur oVirt Engine, erstellt Ziel-Disks in Storage Domains, managed Backup Writer Minions und deployt die finale VM.

**Abhängigkeiten:** `ovirt-engine-sdk-python`, `paramiko` (SSH)

### 4.2 Dateien

```
coriolis/providers/olvm/
├── __init__.py        # Leer
└── imp.py             # OLVMoVirtImportProvider
```

### 4.3 `__init__.py`

```python
# Oracle OLVM / oVirt Import Provider Package
```

### 4.4 `imp.py` — Vollständiger Provider

```python
# Copyright 2024 YourCompany
# All Rights Reserved.

import logging
import time

from oslo_config import cfg
from oslo_log import log as logging

from coriolis import context
from coriolis import exception
from coriolis.providers import base
from coriolis.providers import backup_writers
from coriolis.providers import provider_utils

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

olvm_opts = [
    cfg.IntOpt('writer_port',
               default=6677,
               help='Port for the coriolis-writer service'),
    cfg.IntOpt('minion_memory_mb',
               default=4096,
               help='RAM for temporary worker/minion VMs (MB)'),
    cfg.IntOpt('minion_vcpus',
               default=2,
               help='vCPUs for temporary worker/minion VMs'),
    cfg.StrOpt('minion_template_name',
               default=None,
               help='oVirt template name for minion VMs'),
    cfg.StrOpt('minion_ssh_key_path',
               default=None,
               help='Path to SSH private key for minion access'),
]
CONF.register_opts(olvm_opts, group='olvm')


class OLVMoVirtImportProvider(
        base.BaseEndpointProvider,
        base.BaseEndpointDestinationOptionsProvider,
        base.BaseEndpointNetworksProvider,
        base.BaseEndpointStorageProvider,
        base.BaseImportInstanceProvider,
        base.BaseInstanceFlavorProvider,
        base.BaseReplicaImportProvider,
        base.BaseReplicaImportValidationProvider,
        base.BaseUpdateDestinationReplicaProvider,
):
    platform = "olvm"

    def __init__(self, event_manager):
        self._event_manager = event_manager
        super().__init__(event_manager)

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_ovirt_connection(self, connection_info):
        """Erstellt eine oVirt SDK v4 Verbindung."""
        import ovirtsdk4 as sdk

        url = connection_info.get(
            "url",
            "https://sb-ovirt.sdn.it.internal/ovirt-engine/")
        username = connection_info["username"]
        password = connection_info["password"]
        ca_bundle = connection_info.get("ca_bundle")
        insecure = connection_info.get("insecure", True)

        conn_args = {
            "url": url,
            "username": username,
            "password": password,
        }
        if ca_bundle:
            conn_args["ca_file"] = ca_bundle
        if insecure:
            conn_args["insecure"] = True

        return sdk.Connection(**conn_args)

    def _wait_for_vm_up(self, vms_service, vm_id, timeout=300):
        """Wartet bis die VM den 'up' Status erreicht hat."""
        import ovirtsdk4 as sdk
        vm_service = vms_service.vm_service(vm_id)

        for _ in range(timeout // 5):
            vm = vm_service.get()
            if vm.status == sdk.types.VmStatus.UP:
                return
            time.sleep(5)

        raise exception.Timeout(
            f"VM {vm_id} did not reach 'up' status within {timeout}s")

    def _wait_for_vm_down(self, vms_service, vm_id, timeout=300):
        """Wartet bis die VM den 'down' Status erreicht hat."""
        import ovirtsdk4 as sdk
        vm_service = vms_service.vm_service(vm_id)

        for _ in range(timeout // 5):
            vm = vm_service.get()
            if vm.status == sdk.types.VmStatus.DOWN:
                return
            time.sleep(5)

        raise exception.Timeout(
            f"VM {vm_id} did not reach 'down' status within {timeout}s")

    def _create_minion_vm(self, conn, cluster_id, target_environment,
                          name_suffix="minion"):
        """Erstellt eine temporäre Minion-VM aus einem Template."""
        import ovirtsdk4 as sdk

        system = conn.system_service()
        vms_service = system.vms_service()

        template_name = CONF.olvm.minion_template_name
        if not template_name:
            # Fallback: Minimales Image nutzen
            templates = system.templates_service().list()
            if templates:
                template_name = templates[0].name
            else:
                raise exception.InvalidInput(
                    "No minion template configured (olvm.minion_template_name) "
                    "and no templates found on engine")

        # VM erstellen
        vm = vms_service.add(
            vm=sdk.types.Vm(
                name=f"coriolis-{name_suffix}",
                cluster=sdk.types.Cluster(id=cluster_id),
                template=sdk.types.Template(name=template_name),
                memory=CONF.olvm.minion_memory_mb * 1024 * 1024,
                cpu=sdk.types.Cpu(
                    topology=sdk.types.CpuTopology(
                        cores=CONF.olvm.minion_vcpus,
                        sockets=1,
                    )
                ),
            )
        )
        return vm

    def _attach_disk_to_vm(self, conn, vm_id, disk_id):
        """Attached eine oVirt-Disk an eine VM."""
        import ovirtsdk4 as sdk

        disk_attachments = conn.system_service().vms_service().vm_service(
            vm_id).disk_attachments_service()

        disk_attachments.add(
            attachment=sdk.types.DiskAttachment(
                disk=sdk.types.Disk(id=disk_id),
                interface=sdk.types.DiskInterface.VIRTIO,
                bootable=False,
                active=True,
            )
        )

    def _get_vm_ip(self, conn, vm_id):
        """Ermittelt die IP-Adresse einer VM."""
        vm = conn.system_service().vms_service().vm_service(vm_id).get()
        if vm.guest:
            for nic in (vm.guest.nics or []):
                for ip in (nic.ip or []):
                    if ip.version == sdk.types.IpVersion.V4 or \
                            ip.version == "v4":
                        return ip.address
        raise exception.NotFound(
            f"VM {vm_id} has no reported IP address yet")

    def _get_minion_ssh_key(self):
        """Liest den SSH-Key für den Minion-Zugriff."""
        key_path = CONF.olvm.minion_ssh_key_path
        if key_path and os.path.exists(key_path):
            with open(key_path) as f:
                return f.read()
        return None

    def _detect_os_type(self, export_info):
        """Ermittelt den OS-Typ aus Export-Info."""
        return export_info.get("os_type", "linux")

    # ------------------------------------------------------------------
    # BaseEndpointProvider
    # ------------------------------------------------------------------

    def get_connection_info_schema(self):
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "default": "https://sb-ovirt.sdn.it.internal/"
                               "ovirt-engine/",
                    "description": "oVirt Engine URL",
                },
                "username": {
                    "type": "string",
                    "default": "admin@internal",
                },
                "password": {
                    "type": "string",
                    "secret": True,
                },
                "ca_bundle": {
                    "type": "string",
                    "description": "PEM CA certificate (Dateipfad oder "
                                   "PEM-Inhalt)",
                },
                "insecure": {
                    "type": "boolean",
                    "default": True,
                },
            },
            "required": ["url", "username", "password"],
        }

    def validate_connection(self, ctxt, connection_info):
        """Testet die Verbindung zur oVirt Engine."""
        conn = self._get_ovirt_connection(connection_info)
        try:
            system = conn.system_service()
            product = system.get().product_info
            LOG.info("Connected to oVirt/OLVM: %s version %s",
                     product.name, product.version.full_version)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseEndpointDestinationOptionsProvider
    # ------------------------------------------------------------------

    def get_target_environment_schema(self):
        return {
            "type": "object",
            "properties": {
                "cluster_id": {
                    "type": "string",
                },
                "storage_domain_id": {
                    "type": "string",
                },
                "network_map": {
                    "type": "object",
                    "description": "Source-Netzwerk zu Target-Netzwerk Mapping",
                },
            },
            "required": ["cluster_id", "storage_domain_id"],
        }

    def get_target_environment_options(self, ctxt, connection_info,
                                       env=None, option_names=None):
        conn = self._get_ovirt_connection(connection_info)
        try:
            system = conn.system_service()
            options = []

            # Cluster
            if not option_names or "cluster_id" in option_names:
                clusters = [
                    {"id": c.id, "name": c.name}
                    for c in system.clusters_service().list()
                ]
                options.append({
                    "name": "cluster_id",
                    "values": clusters,
                })

            # Storage Domains (aktiv)
            if not option_names or "storage_domain_id" in option_names:
                sds = [
                    {"id": sd.id, "name": sd.name}
                    for sd in system.storage_domains_service().list()
                    if sd.status == sdk.types.StorageDomainStatus.ACTIVE
                ]
                options.append({
                    "name": "storage_domain_id",
                    "values": sds,
                })

            return options
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseEndpointNetworksProvider
    # ------------------------------------------------------------------

    def get_networks(self, ctxt, connection_info, env):
        conn = self._get_ovirt_connection(connection_info)
        try:
            return [
                {"id": n.id, "name": n.name}
                for n in conn.system_service().networks_service().list()
            ]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseEndpointStorageProvider
    # ------------------------------------------------------------------

    def get_storage(self, ctxt, connection_info, target_environment):
        conn = self._get_ovirt_connection(connection_info)
        try:
            sds = [
                {"id": sd.id, "name": sd.name}
                for sd in conn.system_service().storage_domains_service()
                       .list()
                if sd.status == sdk.types.StorageDomainStatus.ACTIVE
            ]
            return {"storage_backends": sds}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseInstanceFlavorProvider
    # ------------------------------------------------------------------

    def get_optimal_flavor(self, ctxt, connection_info,
                           target_environment, export_info):
        """Findet das optimale Instance-Type/Flavor."""
        conn = self._get_ovirt_connection(connection_info)
        try:
            instance_types = conn.system_service() \
                .instance_types_service().list()

            source_cpu = export_info.get("num_cpu", 2)
            source_mem = export_info.get("memory_mb", 4096)

            best_fit = None
            best_diff = float("inf")

            for it in instance_types:
                if not it.memory or not it.cpu:
                    continue
                cpu = it.cpu.topology.cores
                mem = it.memory // (1024 * 1024)
                if cpu >= source_cpu and mem >= source_mem:
                    diff = (cpu - source_cpu) + (mem - source_mem)
                    if diff < best_diff:
                        best_diff = diff
                        best_fit = it.name

            return best_fit or "Medium"
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseImportInstanceProvider
    # ------------------------------------------------------------------

    def deploy_os_morphing_resources(self, ctxt, connection_info,
                                     target_environment,
                                     instance_deployment_info):
        """Deployed einen OS-Morphing-Minion mit Zugriff auf die Ziel-Disks."""

        conn = self._get_ovirt_connection(connection_info)
        try:
            vms_service = conn.system_service().vms_service()
            target_vm_id = instance_deployment_info["vm_id"]

            # Ziel-VM stoppen
            vm_service = vms_service.vm_service(target_vm_id)
            vm = vm_service.get()
            if vm.status == sdk.types.VmStatus.UP:
                vm_service.stop()
                self._wait_for_vm_down(vms_service, target_vm_id)

            # Minion-VM erstellen (aus Template)
            minion_vm = self._create_minion_vm(
                conn, target_environment["cluster_id"],
                target_environment, name_suffix="osmorphing")

            # Disks von Ziel-VM an Minion hängen
            disk_attachments = vm_service.disk_attachments_service().list()
            for da in disk_attachments:
                disk = conn.follow_link(da.disk)
                # Von Ziel-VM lösen
                try:
                    vm_service.disk_attachments_service().attachment_service(
                        da.id).remove()
                except Exception:
                    pass
                # An Minion-VM hängen
                self._attach_disk_to_vm(
                    conn, minion_vm.id, disk.id)

            # Minion starten
            minion_vm_service = vms_service.vm_service(minion_vm.id)
            minion_vm_service.start()
            self._wait_for_vm_up(vms_service, minion_vm.id)
            vm_ip = self._get_vm_ip(conn, minion_vm.id)

            # NICs-Info aus der Ziel-VM sammeln
            nics_info = []
            for nic in vm_service.nics_service().list():
                nics_info.append({
                    "name": nic.name,
                    "mac_address": nic.mac.address if nic.mac else None,
                })

            return {
                "os_morphing_resources": {
                    "minion_vm_id": minion_vm.id,
                    "target_vm_id": target_vm_id,
                },
                "osmorphing_connection_info": {
                    "ip": vm_ip,
                    "port": 22,
                    "username": "root",
                    "password": None,
                    "pkey": self._get_minion_ssh_key(),
                },
                "osmorphing_info": {
                    "os_type": self._detect_os_type(
                        instance_deployment_info),
                    "nics_info": nics_info,
                    "nics_set_dhcp": True,
                    "osmorphing_parameters": {
                        "retain_user_credentials": True,
                    },
                },
            }
        finally:
            conn.close()

    def delete_os_morphing_resources(self, ctxt, connection_info,
                                     target_environment,
                                     os_morphing_resources):
        """Morphing-Minion aufräumen, Disks zurück zur Ziel-VM."""
        conn = self._get_ovirt_connection(connection_info)
        try:
            vms_service = conn.system_service().vms_service()
            minion_vm_id = os_morphing_resources["minion_vm_id"]
            target_vm_id = os_morphing_resources["target_vm_id"]

            # Minion stoppen
            minion_service = vms_service.vm_service(minion_vm_id)
            minion_service.stop()
            self._wait_for_vm_down(vms_service, minion_vm_id)

            # Disks von Minion zu Ziel-VM verschieben
            target_vm_service = vms_service.vm_service(target_vm_id)
            for da in minion_service.disk_attachments_service().list():
                disk = conn.follow_link(da.disk)
                try:
                    minion_service.disk_attachments_service() \
                        .attachment_service(da.id).remove()
                except Exception:
                    pass
                self._attach_disk_to_vm(conn, target_vm_id, disk.id)

            # Minion löschen
            minion_service.remove()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseReplicaImportProvider (KERN)
    # ------------------------------------------------------------------

    def deploy_replica_disks(self, ctxt, connection_info,
                             target_environment, instance_name,
                             export_info, volumes_info):
        """Erstellt Ziel-Disks in der OLVM Storage Domain.

        Für jede Disk in export_info wird ein oVirt Disk-Image angelegt.
        Existierende Disks werden aktualisiert, gelöschte Quell-Disks
        auf Zielseite entfernt.
        """
        import ovirtsdk4 as sdk

        conn = self._get_ovirt_connection(connection_info)
        try:
            disks_service = conn.system_service().disks_service()
            storage_domain_id = target_environment["storage_domain_id"]

            existing = {v["disk_id"]: v for v in volumes_info}
            new_volumes_info = []

            # Disks erstellen / behalten
            for disk in export_info.get("devices", {}).get("disks", []):
                disk_id = disk.get("id", disk.get("path", f"disk-{len(new_volumes_info)}"))
                size = disk["size_bytes"]

                # Storage-Domain via Mapping auflösen
                sd_id = provider_utils.get_storage_mapping_for_disk(
                    disk, target_environment.get("storage_mappings", {}),
                    storage_domain_id)

                if disk_id in existing:
                    old_vol = existing[disk_id]
                    # Größe prüfen und ggf. anpassen
                    self._ensure_disk_size(
                        conn, old_vol["volume_id"], size)
                    new_volumes_info.append(old_vol)
                else:
                    oVirt_disk = disks_service.add(
                        disk=sdk.types.Disk(
                            name=f"coriolis-{instance_name}-"
                                 f"{disk_id[:32]}",
                            description="Coriolis replica disk",
                            format=sdk.types.DiskFormat.RAW,
                            provisioned_size=size,
                            storage_domains=[
                                sdk.types.StorageDomain(id=sd_id)
                            ],
                            sparse=True,
                        )
                    )
                    # Warten bis Disk bereit ist
                    disk_service = disks_service.disk_service(
                        oVirt_disk.id)
                    for _ in range(60):
                        d = disk_service.get()
                        if d.status == sdk.types.DiskStatus.OK:
                            break
                        time.sleep(5)

                    new_volumes_info.append({
                        "disk_id": disk_id,
                        "volume_id": oVirt_disk.id,
                        "volume_name": oVirt_disk.name,
                    })

            return new_volumes_info
        finally:
            conn.close()

    def _ensure_disk_size(self, conn, disk_id, required_size_bytes):
        """Stellt sicher, dass eine Disk mindestens required_size_bytes hat."""
        disks_service = conn.system_service().disks_service()
        disk_service = disks_service.disk_service(disk_id)
        disk = disk_service.get()
        if disk.provisioned_size < required_size_bytes:
            disk_service.update(
                disk=sdk.types.Disk(
                    provisioned_size=required_size_bytes,
                )
            )

    def deploy_replica_target_resources(self, ctxt, connection_info,
                                        target_environment, volumes_info):
        """Deployed Destination-Minion mit Backup Writer."""
        import ovirtsdk4 as sdk

        conn = self._get_ovirt_connection(connection_info)
        try:
            vms_service = conn.system_service().vms_service()
            cluster_id = target_environment["cluster_id"]

            # Minion-VM erstellen
            minion_vm = self._create_minion_vm(
                conn, cluster_id, target_environment)

            # Disks an Minion attachieren
            for vol in volumes_info:
                self._attach_disk_to_vm(
                    conn, minion_vm.id, vol["volume_id"])

            # VM starten
            vm_service = vms_service.vm_service(minion_vm.id)
            vm_service.start()
            self._wait_for_vm_up(vms_service, minion_vm.id)

            # IP ermitteln
            vm_ip = self._get_vm_ip(conn, minion_vm.id)

            # SSH-Key
            ssh_pkey = self._get_minion_ssh_key()

            # Backup Writer via Bootstrapper einrichten
            ssh_conn_info = {
                "ip": vm_ip,
                "port": 22,
                "username": "root",
                "password": None,
                "pkey": ssh_pkey,
            }

            bootstrapper = backup_writers.HTTPBackupWriterBootstrapper(
                ssh_conn_info, CONF.olvm.writer_port)
            writer_conn_details = bootstrapper.setup_writer()

            # Volume-Device-Mapping setzen
            for vol in volumes_info:
                vol["volume_dev"] = f"/dev/disk/by-id/virtio-" \
                                    f"{vol['volume_id'][:20]}"

            return {
                "migr_resources": {
                    "minion_vm_id": minion_vm.id,
                    "writer_port": CONF.olvm.writer_port,
                },
                "volumes_info": volumes_info,
                "connection_info": {
                    "backend": "http_backup_writer",
                    "connection_details": writer_conn_details,
                },
            }
        finally:
            conn.close()

    def delete_replica_target_resources(self, ctxt, connection_info,
                                        target_environment,
                                        migr_resources_dict):
        """Minion-VM nach Transfer aufräumen."""
        conn = self._get_ovirt_connection(connection_info)
        try:
            vm_id = migr_resources_dict["minion_vm_id"]
            vm_service = conn.system_service().vms_service().vm_service(
                vm_id)
            vm_service.stop()
            self._wait_for_vm_down(
                conn.system_service().vms_service(), vm_id)
            vm_service.remove()
        finally:
            conn.close()

    def delete_replica_disks(self, ctxt, connection_info,
                             target_environment, volumes_info):
        """Alle Replika-Disks löschen."""
        conn = self._get_ovirt_connection(connection_info)
        try:
            disks_service = conn.system_service().disks_service()
            for vol in volumes_info:
                if "volume_id" in vol:
                    try:
                        disks_service.disk_service(
                            vol["volume_id"]).remove()
                    except Exception as e:
                        LOG.warning(
                            "Failed to remove disk %s: %s",
                            vol["volume_id"], e)
        finally:
            conn.close()

    def deploy_replica_instance(self, ctxt, connection_info,
                                target_environment, instance_name,
                                export_info, volumes_info, clone_disks):
        """Erstellt die finale Ziel-VM aus den replizierten Disks."""
        import ovirtsdk4 as sdk

        conn = self._get_ovirt_connection(connection_info)
        try:
            vms_service = conn.system_service().vms_service()
            cluster_id = target_environment["cluster_id"]

            memory_mb = export_info.get("memory_mb", 4096)
            vcpus = export_info.get("num_cpu", 2)

            # NICs konfigurieren (via network_map)
            target_nics = []
            network_map = target_environment.get("network_map", {})
            for nic in export_info.get("devices", {}).get("nics", []):
                src_net = nic.get("network_name") or nic.get("network_id")
                dst_net = network_map.get(src_net, src_net)
                target_nics.append(
                    sdk.types.Nic(
                        name=nic.get("name", "nic-0")[:15],
                        interface=sdk.types.NicInterface.VIRTIO,
                        vnic_profile=sdk.types.VnicProfile(
                            id=dst_net),
                    )
                )

            # Firmware-Typ
            firmware = sdk.types.BiosType.I440FX_SEA_BIOS
            if export_info.get("firmware_type") == "EFI":
                firmware = sdk.types.BiosType.Q35_SEA_BIOS

            # VM erstellen
            oVirt_vm = vms_service.add(
                vm=sdk.types.Vm(
                    name=instance_name[:64],
                    cluster=sdk.types.Cluster(id=cluster_id),
                    cpu=sdk.types.Cpu(
                        topology=sdk.types.CpuTopology(
                            cores=vcpus,
                            sockets=1,
                        )
                    ),
                    memory=memory_mb * 1024 * 1024,
                    os=sdk.types.OperatingSystem(
                        type=self._detect_os_type(export_info).upper(),
                    ),
                    bios_type=firmware,
                    type=sdk.types.VmType.SERVER,
                    nics=target_nics,
                )
            )

            # Disks attachieren
            for vol in volumes_info:
                if clone_disks:
                    # Clone statt direktes Attach
                    cloned = self._clone_disk(
                        conn, vol["volume_id"],
                        target_environment.get("storage_domain_id"))
                    vol["clone_id"] = cloned.id
                    self._attach_disk_to_vm(
                        conn, oVirt_vm.id, cloned.id)
                else:
                    self._attach_disk_to_vm(
                        conn, oVirt_vm.id, vol["volume_id"])

            return {
                "instance_deployment_info": {
                    "vm_id": oVirt_vm.id,
                    "vm_name": oVirt_vm.name,
                }
            }
        finally:
            conn.close()

    def _clone_disk(self, conn, disk_id, storage_domain_id):
        """Klont eine oVirt-Disk."""
        import ovirtsdk4 as sdk
        import uuid

        disks_service = conn.system_service().disks_service()
        disk_service = disks_service.disk_service(disk_id)

        clone = disks_service.add(
            disk=sdk.types.Disk(
                name=f"clone-{uuid.uuid4().hex[:8]}",
                description="Cloned replica disk",
                format=sdk.types.DiskFormat.RAW,
                provisioned_size=disk_service.get().provisioned_size,
                storage_domains=[
                    sdk.types.StorageDomain(id=storage_domain_id)
                ],
                sparse=True,
            )
        )
        # Kopieren via qemu-img (externer Schritt)
        # oVirt SDK hat kein direktes Disk-Cloning, daher:
        # 1. Live-Storage-Migration nutzen, oder
        # 2. qemu-img convert auf einem Minion durchführen
        return clone

    def finalize_replica_instance_deployment(self, ctxt, connection_info,
                                             target_environment,
                                             instance_deployment_info):
        """VM starten und finale Informationen zurückgeben."""
        conn = self._get_ovirt_connection(connection_info)
        try:
            vm_id = instance_deployment_info["vm_id"]
            vm_service = conn.system_service().vms_service().vm_service(
                vm_id)

            # VM starten
            vm_service.start()
            # Kurz warten und Status abfragen
            vm = vm_service.get()

            return {
                "id": vm.id,
                "name": vm.name,
                "num_cpu": vm.cpu.topology.cores
                if vm.cpu and vm.cpu.topology else 0,
                "memory_mb": vm.memory // (1024 * 1024)
                if vm.memory else 0,
                "os_type": self._detect_os_type(
                    instance_deployment_info),
                "nested_virtualization": False,
                "devices": {
                    "disks": [],
                    "nics": [],
                    "cdroms": [],
                    "serial_ports": [],
                    "floppies": [],
                    "controllers": [],
                },
            }
        finally:
            conn.close()

    def cleanup_failed_replica_instance_deployment(
            self, ctxt, connection_info, target_environment,
            instance_deployment_info):
        """Löscht die Ziel-VM bei fehlgeschlagenem Deployment."""
        conn = self._get_ovirt_connection(connection_info)
        try:
            vm_id = instance_deployment_info["vm_id"]
            vm_service = conn.system_service().vms_service().vm_service(
                vm_id)
            vm_service.remove()
        finally:
            conn.close()

    def create_replica_disk_snapshots(self, ctxt, connection_info,
                                      target_environment, volumes_info):
        """Erstellt oVirt Disk Snapshots."""
        import ovirtsdk4 as sdk

        conn = self._get_ovirt_connection(connection_info)
        try:
            for vol in volumes_info:
                if "volume_id" not in vol:
                    continue
                snap_svc = conn.system_service().disks_service() \
                    .disk_service(vol["volume_id"]).disk_snapshots_service()
                snap = snap_svc.add(
                    disk_snapshot=sdk.types.DiskSnapshot(
                        description="coriolis-replica-snapshot",
                    )
                )
                vol["snapshot_id"] = snap.id
        finally:
            conn.close()
        return volumes_info

    def delete_replica_target_disk_snapshots(self, ctxt, connection_info,
                                             target_environment,
                                             volumes_info):
        """Löscht oVirt Disk Snapshots."""
        conn = self._get_ovirt_connection(connection_info)
        try:
            for vol in volumes_info:
                if "snapshot_id" not in vol:
                    continue
                try:
                    conn.system_service().disks_service().disk_service(
                        vol["volume_id"]
                    ).disk_snapshots_service().snapshot_service(
                        vol["snapshot_id"]
                    ).remove()
                except Exception as e:
                    LOG.warning(
                        "Failed to remove snapshot %s: %s",
                        vol["snapshot_id"], e)
        finally:
            conn.close()
        return volumes_info

    def restore_replica_disk_snapshots(self, ctxt, connection_info,
                                       target_environment, volumes_info):
        """Stellt Snapshots wieder her.

        oVirt hat kein direktes Snapshot-Restore für standalone Disks,
        daher Fallback auf clone_disks=True.
        """
        return volumes_info

    # ------------------------------------------------------------------
    # BaseReplicaImportValidationProvider
    # ------------------------------------------------------------------

    def validate_replica_import_input(self, ctxt, connection_info,
                                      target_environment, export_info,
                                      check_os_morphing_resources=False,
                                      check_final_vm_params=False):
        """Prüft ob die Zielumgebung das Import akzeptieren kann."""
        conn = self._get_ovirt_connection(connection_info)
        try:
            cluster_id = target_environment["cluster_id"]
            sd_id = target_environment["storage_domain_id"]

            # Prüfen ob Cluster existiert
            clusters = conn.system_service().clusters_service()
            cluster = clusters.cluster_service(cluster_id).get()
            if not cluster:
                raise exception.InvalidInput(
                    f"Cluster {cluster_id} not found")

            # Prüfen ob Storage Domain existiert und aktiv ist
            sds = conn.system_service().storage_domains_service()
            sd = sds.storage_domain_service(sd_id).get()
            if sd.status != sdk.types.StorageDomainStatus.ACTIVE:
                raise exception.InvalidInput(
                    f"Storage domain {sd_id} is not active")

            # Platz prüfen
            required = sum(
                d["size_bytes"]
                for d in export_info.get("devices", {}).get("disks", []))
            if sd.available:
                avail = sd.available
                if required > avail:
                    raise exception.InvalidInput(
                        f"Not enough space on {sd.name}: "
                        f"needed {required}, available {avail}")
        finally:
            conn.close()

    def validate_replica_deployment_input(self, ctxt, connection_info,
                                          target_environment, export_info):
        self.validate_replica_import_input(
            ctxt, connection_info, target_environment, export_info)

    # ------------------------------------------------------------------
    # BaseUpdateDestinationReplicaProvider
    # ------------------------------------------------------------------

    def check_update_destination_environment_params(
            self, ctxt, connection_info, export_info,
            volumes_info, old_params, new_params):
        if not volumes_info:
            return []
        return volumes_info

    # ------------------------------------------------------------------
    # BaseInstanceProvider
    # ------------------------------------------------------------------

    def get_os_morphing_tools(self, os_type, osmorphing_info):
        """Gibt OLVM/KVM-spezifische OS-Morphing-Tools zurück.

        Installiert QEMU Guest Agent, VirtIO-Treiber, cloud-init.
        """
        return []
```

---

## 5 Provider-Registrierung & Start

### 5.1 Provider in `setup.cfg` registrieren

Optional: via `setup.cfg` entry_points, falls das Paket installiert werden soll:

```ini
[entry_points]
coriolis.providers =
    vmware_vsphere = coriolis.providers.vmware.exp:VMwareVSphereExportProvider
    olvm = coriolis.providers.olvm.imp:OLVMoVirtImportProvider
```

### 5.2 Config prüfen und Services starten

```bash
# Config validieren
coriolis-api --config-file /etc/coriolis/coriolis.conf --print-config

# Services starten (alle im Vordergrund für Testing)
coriolis-api --config-file /etc/coriolis/coriolis.conf
coriolis-conductor --config-file /etc/coriolis/coriolis.conf
coriolis-worker --config-file /etc/coriolis/coriolis.conf
coriolis-scheduler --config-file /etc/coriolis/coriolis.conf

# Logs prüfen auf Provider-Erkennung
tail -f /var/log/coriolis/*.log
# Erwartet: "Registered provider vmware_vsphere with types [...]"
#           "Registered provider olvm with types [...]"
```

---

## 6 Endpoints einrichten

### 6.1 Coriolis Client installieren

```bash
pip install git+https://github.com/cloudbase/python-coriolisclient.git
```

### 6.2 Endpoints via API erstellen

```bash
# API-URL
API="http://localhost:7667/v1"
TOKEN="fake-admin-token"  # In Dev ohne Keystone

# ========== VMware vSphere Endpoint ==========
curl -s -X POST "$API/endpoints" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: $TOKEN" \
  -d '{
    "endpoint": {
      "name": "vsphere-production",
      "type": "vmware_vsphere",
      "description": "VMware vSphere 8 Produktion",
      "connection_info": {
        "host": "vc-mgc.sdn.it.internal",
        "username": "administrator@vsphere.local",
        "password": "your-password",
        "allow_untrusted": true
      }
    }
  }'

# ========== OLVM Endpoint ==========
curl -s -X POST "$API/endpoints" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: $TOKEN" \
  -d '{
    "endpoint": {
      "name": "olvm-production",
      "type": "olvm",
      "description": "Oracle OLVM 4.5 Zielumgebung",
      "connection_info": {
        "url": "https://sb-ovirt.sdn.it.internal/ovirt-engine/",
        "username": "admin@internal",
        "password": "your-password",
        "insecure": true
      }
    }
  }'
```

### 6.3 Endpoints verifizieren

```bash
# Endpoints auflisten
curl "$API/endpoints" -H "X-Auth-Token: $TOKEN"

# Verbindung testen
curl -X POST "$API/endpoints/{id}/connection_info/validate" \
  -H "X-Auth-Token: $TOKEN"

# VMs im vSphere auflisten
curl "$API/endpoints/{vsphere-id}/instances" \
  -H "X-Auth-Token: $TOKEN"

# Netzwerke im vSphere auflisten
curl "$API/endpoints/{vsphere-id}/networks" \
  -H "X-Auth-Token: $TOKEN"
```

---

## 7 Migration durchführen

### 7.1 Replikation starten

```bash
# Transfer erstellen (Replikation)
curl -s -X POST "$API/transfers" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: $TOKEN" \
  -d '{
    "transfer": {
      "name": "my-oracle-vm-migration",
      "scenario": "replica",
      "origin_endpoint_id": "<vsphere-endpoint-uuid>",
      "destination_endpoint_id": "<olvm-endpoint-uuid>",
      "instances": ["MyOracleLinuxVM"],
      "source_environment": {
        "shutdown_instances": true
      },
      "destination_environment": {
        "cluster_id": "<cluster-uuid>",
        "storage_domain_id": "<sd-uuid>",
        "network_map": {
          "VM Network": "<olvm-network-uuid>",
          "Other Network": "<other-olvm-network-uuid>"
        }
      }
    }
  }'
```

### 7.2 Execution starten (inkrementelle Syncs)

```bash
# Erste Execution (initialer Vollsync)
curl -s -X POST "$API/transfers/{transfer-id}/executions" \
  -H "X-Auth-Token: $TOKEN" \
  -d '{"execution": {}}'

# Status prüfen
curl "$API/transfers/{transfer-id}" \
  -H "X-Auth-Token: $TOKEN" | python3 -m json.tool

# Weitere inkrementelle Syncs (während VM läuft)
# Neue Execution starten (automatische Änderungserkennung)
# Möglichst kurz vor dem Cutover ausführen
```

### 7.3 Deployment (Cutover)

```bash
# Nachdem die letzte Execution abgeschlossen ist:
# Deployment startet finale VM auf OLVM
curl -s -X POST "$API/transfers/{transfer-id}/deployments" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: $TOKEN" \
  -d '{
    "deployment": {
      "clone_disks": false,
      "skip_os_morphing": false,
      "shutdown_instances": true
    }
  }'

# Deployment-Status prüfen
curl "$API/transfers/{transfer-id}/deployments/{deployment-id}" \
  -H "X-Auth-Token: $TOKEN" | python3 -m json.tool

# Nach Abschluss: VM läuft auf OLVM!
```

### 7.4 Post-Migration

```bash
# 1. Quell-VM auf vSphere prüfen (sollte aus sein bei shutdown_instances)
# 2. Ziel-VM auf OLVM prüfen
#    - oVirt Engine Web UI: https://sb-ovirt.sdn.it.internal/ovirt-engine/
#    - VM-Status, Netzwerk-Konnektivität, Storage-Mounts prüfen
# 3. Gast-OS prüfen:
#    - QEMU Guest Agent läuft?
#    - cloud-init erfolgreich durchgelaufen?
#    - Netzwerk korrekt konfiguriert? (DHCP oder Static)
#    - Oracle Linux: UEK-Kernel geladen?, yum-Repos intakt?
# 4. OS-Morphing-Logs prüfen (falls aktiviert)
```

---