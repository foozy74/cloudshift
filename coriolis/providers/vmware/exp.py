# Copyright 2024 YourCompany
# All Rights Reserved.

import time

from oslo_config import cfg
from oslo_log import log as logging

from coriolis import exception
from coriolis.providers import backup_writers
from coriolis.providers import base
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
    cfg.StrOpt('worker_ip',
               default=None,
               help='IP address of the VMware worker VM (default to local '
                    'host if None)'),
    cfg.StrOpt('worker_ssh_password',
               default=None,
               secret=True,
               help='SSH password for the VMware worker VM'),
    cfg.StrOpt('worker_ssh_pkey_path',
               default=None,
               help='SSH private key path for the VMware worker VM'),
]
CONF.register_opts(vmware_opts, group='vmware')


class VMwareVSphereExportProvider(
        base.BaseEndpointInstancesProvider,
        base.BaseEndpointSourceOptionsProvider,
        base.BaseEndpointNetworksProvider,
        base.BaseEndpointStorageProvider,
        base.BaseReplicaExportValidationProvider,
        base.BaseUpdateSourceReplicaProvider,
        base.BaseReplicaExportProvider,
):
    platform = "vmware_vsphere"

    def __init__(self, event_manager):
        self._event_manager = event_manager

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_vcenter_session(self, connection_info):
        """Erstellt eine pyvmomi-Verbindung zum vCenter."""
        from pyVim.connect import SmartConnect
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
            elif "linux" in gl or any(
                x in gl for x in ("rhel", "centos", "ubuntu",
                                  "debian", "suse", "oracle")):
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
        fw = getattr(config, "firmware", "bios")
        return fw == "efi"

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

    def _get_vlan_id(self, device):
        """Liest die numerische VLAN-ID aus einem VirtualEthernetCard-Gerät.

        Unterstützt:
          - DVS-Portgroups (DistributedVirtualPortgroup): liest vlanId aus
            defaultPortConfig.
          - Standard-Portgroups (Network): keine VLAN-ID verfügbar → gibt 0
            zurück (untagged).

        :param device: vim.vm.device.VirtualEthernetCard
        :returns: int VLAN-ID (0 = untagged) oder None wenn nicht lesbar
        """
        try:
            from pyVmomi import vim
            backing = device.backing
            dv_backing_cls = (
                vim.vm.device.VirtualEthernetCard.
                DistributedVirtualPortBackingInfo)
            if isinstance(backing, dv_backing_cls):
                portgroup_key = backing.port.portgroupKey
                # backing.port hat keine direkte Referenz auf das PG-Obj.
                # Key wird in get_replica_instance_info aufgeloest.
                return portgroup_key  # wird unten zu int aufgelöst
            # Standard-Portgroup: kein VLAN-Tag → untagged
            return 0
        except Exception:
            return None

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
                "worker_ip": {
                    "type": "string",
                },
                "worker_ssh_user": {
                    "type": "string",
                },
                "worker_ssh_password": {
                    "type": "string",
                },
                "worker_ssh_pkey": {
                    "type": "string",
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

        # Portgroup-Key → VLAN-ID Mapping vorab aufbauen (DVSwitch-Netzwerke)
        portgroup_vlan_map = {}
        try:
            content = si.RetrieveContent()
            pg_view = content.viewManager.CreateContainerView(
                content.rootFolder,
                [vim.dvs.DistributedVirtualPortgroup],
                True)
            for pg in pg_view.view:
                try:
                    vlan_cfg = pg.config.defaultPortConfig.vlan
                    # VmwareDistributedVirtualSwitchVlanIdSpec
                    vlan_id = getattr(vlan_cfg, 'vlanId', 0)
                    portgroup_vlan_map[pg.key] = int(vlan_id) \
                        if isinstance(vlan_id, int) else 0
                except Exception:
                    portgroup_vlan_map[pg.key] = 0
            pg_view.Destroy()
        except Exception as pg_err:
            LOG.debug("Could not build portgroup VLAN map: %s", pg_err)

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
                vlan_id = 0  # default: untagged
                if device.backing:
                    net_obj = getattr(device.backing, 'network', None)
                    if net_obj:
                        network_name = net_obj.name
                    network_id = getattr(
                        device.backing, 'deviceName', None)
                    # DVS-Portgroup: VLAN-ID über pre-built map
                    if isinstance(
                            device.backing,
                            vim.vm.device.VirtualEthernetCard
                            .DistributedVirtualPortBackingInfo):
                        pg_key = device.backing.port.portgroupKey
                        vlan_id = portgroup_vlan_map.get(pg_key, 0)
                nics.append({
                    "id": f"nic-{device.key}",
                    "name": device.deviceInfo.label,
                    "network_name": network_name,
                    "network_id": network_id,
                    "vlan_id": vlan_id,
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

    def deploy_replica_source_resources(
            self, ctxt, connection_info, export_info, source_environment):
        """Deployt einen temporären Source-Worker auf dem ESXi-Host.

        Der Worker (eine Linux-VM) hat SSH-Zugriff und die Quell-Disks
        als Block-Devices für den Replicator. Für eine produktive Umgebung
        muss hier die eigentliche Worker-VM auf ESXi deployt werden.
        """
        # Vereinfachte Implementierung für das HOWTO:
        # Geht davon aus, dass ein Worker bereits läuft und die
        # Block-Devices verfügbar sind.
        # In Produktion: Worker-VM auf ESXi deployen (z.B. via OVF Tool).

        worker_ip = source_environment.get("worker_ip")
        if not worker_ip:
            worker_ip = CONF.vmware.worker_ip
        if not worker_ip:
            worker_ip = export_info.get("hostname")
        if not worker_ip:
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect((connection_info.get("host", "8.8.8.8"), 80))
                worker_ip = s.getsockname()[0]
                s.close()
            except Exception:
                pass

        if not worker_ip:
            raise exception.InvalidInput(
                "worker_ip must be provided in source_environment or "
                "vmware configuration")

        ssh_pkey = source_environment.get("worker_ssh_pkey")
        if not ssh_pkey:
            ssh_pkey_path = CONF.vmware.worker_ssh_pkey_path
            if ssh_pkey_path:
                import os
                if os.path.exists(ssh_pkey_path):
                    try:
                        with open(ssh_pkey_path, 'r') as f:
                            ssh_pkey = f.read()
                    except Exception as e:
                        LOG.warning(
                            "Failed to read VMware worker SSH pkey at %s: %s",
                            ssh_pkey_path, e)

        ssh_password = source_environment.get("worker_ssh_password")
        if not ssh_password and not ssh_pkey:
            ssh_password = CONF.vmware.worker_ssh_password

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
        # Fetch disk sizes from vCenter as a fallback/validation
        vcenter_disk_sizes = {}
        try:
            from pyVim.connect import Disconnect
            from pyVmomi import vim
            si = self._get_vcenter_session(connection_info)
            vm = self._find_vm_by_name(si, instance_name)
            for device in vm.config.hardware.device:
                if isinstance(device, vim.vm.device.VirtualDisk):
                    vcenter_disk_sizes[f"disk-{device.key}"] = (
                        device.capacityInKB * 1024)
            Disconnect(si)
            LOG.info("Fetched disk sizes from vCenter: %s", vcenter_disk_sizes)
        except Exception as e:
            LOG.warning("Failed to fetch disk sizes from vCenter: %s", e)

        for vol in volumes_info:
            disk_id = vol["disk_id"]
            size = (vcenter_disk_sizes.get(disk_id) or
                    vol.get("size") or vol.get("size_bytes"))
            if size:
                vol["size"] = size
                vol["size_bytes"] = size

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

        # Replicator-Devices abfragen und sortieren
        try:
            repl_devices = replicator._cli.get_status(brief=False)
            # Filter out devices that are not exportable or have
            # mounted partitions, or just filter by name starting
            # with 'sd' and not 'sda'
            dev_names = sorted([
                d["device-name"] for d in repl_devices
                if d.get("device-name") and d["device-name"] != "sda"
            ])
            LOG.info("Found replicator devices: %s", dev_names)
        except Exception as e:
            LOG.warning("Failed to fetch replicator devices: %s", e)
            dev_names = []

        # Source Volume-Pfade auflösen
        source_volumes_info = []
        for idx, vol in enumerate(volumes_info):
            disk_id = vol["disk_id"]
            # Fallback mapping: if we have a matching device name
            # from the replicator, use it!
            if idx < len(dev_names):
                disk_path = f"/dev/{dev_names[idx]}"
            else:
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
        replicator.replicate_disks(
            source_volumes_info, writer)

        # Replica-State für nächsten inkrementellen Sync speichern
        source_resources["replica_state"] = replicator.get_replica_state()

        return volumes_info

    def _resolve_source_disk_path(self, source_resources, disk_id):
        """Ermittelt den Pfad eines Source-Block-Devices.

        Diese Methode muss die Disk-ID (aus der VM-Export-Info) auf den
        tatsächlichen /dev/xxx Pfad des Block-Devices im Source-Worker
        mappen. Im Produktionsfall werden die VMDK-Dateien der VM als
        Block-Devices an den Worker angebunden (z.B. via RDM oder
        Datastore-Pfad über NFS-Loopback).
        """
        return source_resources.get("disk_paths", {}).get(
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

    def check_update_source_environment_params(
            self, ctxt, connection_info, instance_name, volumes_info,
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
