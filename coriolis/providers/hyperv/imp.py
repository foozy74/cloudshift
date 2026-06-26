# Copyright 2024 thesolution.at
# All Rights Reserved.

import json
import os
import time
import uuid

from oslo_config import cfg
from oslo_log import log as logging

from coriolis import exception
from coriolis.providers import backup_writers
from coriolis.providers import base
from coriolis.providers import provider_utils

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

hyperv_opts = [
    cfg.IntOpt('writer_port',
               default=6677,
               help='Port for the coriolis-writer service on the minion'),
    cfg.IntOpt('minion_memory_mb',
               default=4096,
               help='RAM for temporary worker/minion VMs (MB)'),
    cfg.IntOpt('minion_vcpus',
               default=2,
               help='vCPUs for temporary worker/minion VMs'),
    cfg.StrOpt('minion_template_vhdx',
               default=None,
               help='Path to the Ubuntu minion template VHDX on the '
                    'Hyper-V host. A copy is made for each minion VM.'),
    cfg.StrOpt('minion_ssh_key_path',
               default=None,
               help='Path to SSH private key for minion access'),
    cfg.StrOpt('default_vm_path',
               default='C:\\VMs',
               help='Default directory on the Hyper-V host where VHDX '
                    'files for new VMs are created'),
    cfg.StrOpt('default_switch',
               default=None,
               help='Default Hyper-V virtual switch to connect minion VMs '
                    'to. If unset, the first available switch is used.'),
]
CONF.register_opts(hyperv_opts, group='hyperv')


class HyperVImportProvider(
        base.BaseEndpointProvider,
        base.BaseEndpointDestinationOptionsProvider,
        base.BaseEndpointNetworksProvider,
        base.BaseEndpointStorageProvider,
        base.BaseInstanceFlavorProvider,
        base.BaseReplicaImportProvider,
        base.BaseReplicaImportValidationProvider,
        base.BaseUpdateDestinationReplicaProvider,
):
    platform = "hyperv"

    def __init__(self, event_manager):
        self._event_manager = event_manager

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_winrm_session(self, connection_info):
        """Erstellt eine WinRM/PowerShell-Session zum Hyper-V Host."""
        import winrm

        host = connection_info["host"]
        username = connection_info["username"]
        password = connection_info["password"]
        port = connection_info.get("port", 5986)
        use_https = connection_info.get("https", True)
        # 'ignore' skips certificate validation (self-signed WinRM certs).
        cert_validation = connection_info.get("cert_validation", "ignore")

        scheme = "https" if use_https else "http"
        endpoint = "%s://%s:%s/wsman" % (scheme, host, port)

        transport = connection_info.get("transport", "ntlm")
        return winrm.Session(
            endpoint,
            auth=(username, password),
            transport=transport,
            server_cert_validation=cert_validation,
        )

    def _run_ps(self, session, script):
        """Führt ein PowerShell-Skript aus und gibt stdout zurück.

        Wirft eine CoriolisException, wenn das Skript fehlschlägt.
        """
        result = session.run_ps(script)
        if result.status_code != 0:
            err = result.std_err
            if isinstance(err, bytes):
                err = err.decode(errors="replace")
            raise exception.CoriolisException(
                "PowerShell command on Hyper-V host failed: %s" % err)
        out = result.std_out
        if isinstance(out, bytes):
            out = out.decode(errors="replace")
        return out.strip()

    def _run_ps_json(self, session, script):
        """Führt PowerShell aus und parst die JSON-Ausgabe.

        Das Skript sollte sein Ergebnis via 'ConvertTo-Json' ausgeben.
        Gibt immer eine Liste zurück (auch bei einzelnen Objekten).
        """
        out = self._run_ps(session, script)
        if not out:
            return []
        data = json.loads(out)
        if isinstance(data, dict):
            return [data]
        return data

    def _get_minion_ssh_key(self):
        """Liest den SSH-Key für den Minion-Zugriff."""
        key_path = CONF.hyperv.minion_ssh_key_path
        if key_path and os.path.exists(key_path):
            with open(key_path) as f:
                return f.read()
        return None

    def _detect_os_type(self, export_info):
        """Ermittelt den OS-Typ aus Export-Info."""
        return export_info.get("os_type", "linux")

    def _get_default_switch(self, session, target_environment):
        """Ermittelt den Default-Switch für Minion-VMs."""
        switch = (target_environment.get("default_switch") or
                  CONF.hyperv.default_switch)
        if switch:
            return switch
        switches = self._run_ps_json(
            session,
            "Get-VMSwitch | Select-Object -First 1 Name | ConvertTo-Json")
        if switches:
            return switches[0]["Name"]
        raise exception.InvalidInput(
            "No Hyper-V virtual switch configured (hyperv.default_switch) "
            "and none found on the host")

    def _get_vm_path(self, target_environment):
        return (target_environment.get("vm_path") or
                CONF.hyperv.default_vm_path)

    def _vhdx_path(self, vm_path, instance_name, disk_id):
        safe_id = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in str(disk_id))[:32]
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in str(instance_name))[:32]
        filename = "coriolis-%s-%s.vhdx" % (safe_name, safe_id)
        return "%s\\%s" % (vm_path.rstrip("\\"), filename)

    def _wait_for_vm_state(self, session, vm_name, state, timeout=300):
        """Wartet bis die VM den angegebenen Status erreicht hat.

        state: 'Running' oder 'Off'
        """
        for _ in range(timeout // 5):
            out = self._run_ps(
                session,
                "(Get-VM -Name '%s').State" % vm_name)
            if out.strip().lower() == state.lower():
                return
            time.sleep(5)
        raise exception.Timeout(
            "VM %s did not reach state '%s' within %ss" % (
                vm_name, state, timeout))

    def _get_vm_ip(self, session, vm_name, timeout=900):
        """Ermittelt die IPv4-Adresse einer laufenden VM via KVP/IS."""
        script = (
            "$ips = (Get-VMNetworkAdapter -VMName '%s').IPAddresses; "
            "$ips | Where-Object { $_ -match "
            "'^\\d+\\.\\d+\\.\\d+\\.\\d+$' } | ConvertTo-Json" % vm_name)
        for _ in range(timeout // 5):
            try:
                out = self._run_ps(session, script)
                if out:
                    data = json.loads(out)
                    if isinstance(data, list):
                        if data:
                            return data[0]
                    elif data:
                        return data
            except Exception as e:
                LOG.debug("Failed to get IP for VM %s: %s", vm_name, e)
            time.sleep(5)
        raise exception.NotFound(
            "VM %s has no reported IPv4 address yet" % vm_name)

    def _create_minion_vm(self, session, target_environment,
                          name_suffix="minion"):
        """Erstellt eine temporäre Minion-VM aus dem Ubuntu-Template-VHDX."""
        template_vhdx = (
            target_environment.get("minion_template_vhdx") or
            CONF.hyperv.minion_template_vhdx)
        if not template_vhdx:
            raise exception.InvalidInput(
                "No minion template VHDX configured "
                "(hyperv.minion_template_vhdx)")

        vm_name = "coriolis-%s-%s" % (name_suffix, uuid.uuid4().hex[:8])
        vm_path = self._get_vm_path(target_environment)
        switch = self._get_default_switch(session, target_environment)
        boot_vhdx = "%s\\%s-boot.vhdx" % (vm_path.rstrip("\\"), vm_name)
        memory_bytes = CONF.hyperv.minion_memory_mb * 1024 * 1024

        script = (
            "Copy-Item -Path '%(tmpl)s' -Destination '%(boot)s' -Force; "
            "New-VM -Name '%(name)s' -MemoryStartupBytes %(mem)d "
            "-Generation 2 -VHDPath '%(boot)s' -SwitchName '%(switch)s' "
            "| Out-Null; "
            "Set-VMProcessor -VMName '%(name)s' -Count %(cpus)d; "
            "Set-VMFirmware -VMName '%(name)s' -EnableSecureBoot Off;" % {
                "tmpl": template_vhdx,
                "boot": boot_vhdx,
                "name": vm_name,
                "mem": memory_bytes,
                "switch": switch,
                "cpus": CONF.hyperv.minion_vcpus,
            })
        self._run_ps(session, script)
        return {"name": vm_name, "boot_vhdx": boot_vhdx}

    def _attach_disk_to_vm(self, session, vm_name, vhdx_path):
        """Attached eine VHDX an eine VM (SCSI-Controller)."""
        self._run_ps(
            session,
            "Add-VMHardDiskDrive -VMName '%s' -Path '%s'" % (
                vm_name, vhdx_path))

    def _delete_vm(self, session, vm_name, delete_boot_vhdx=None):
        """Stoppt und löscht eine VM, optional inklusive Boot-VHDX."""
        self._run_ps(
            session,
            "Stop-VM -Name '%s' -TurnOff -Force "
            "-ErrorAction SilentlyContinue; "
            "Remove-VM -Name '%s' -Force "
            "-ErrorAction SilentlyContinue" % (vm_name, vm_name))
        if delete_boot_vhdx:
            self._run_ps(
                session,
                "Remove-Item -Path '%s' -Force "
                "-ErrorAction SilentlyContinue" % delete_boot_vhdx)

    def _stop_vm(self, session, vm_name, timeout=300):
        """Fährt eine VM herunter und wartet auf den 'Off'-Status."""
        state = self._run_ps(
            session,
            "(Get-VM -Name '%s' -ErrorAction SilentlyContinue).State"
            % vm_name)
        if state.strip().lower() == "off":
            return
        self._run_ps(
            session,
            "Stop-VM -Name '%s' -Force -ErrorAction SilentlyContinue"
            % vm_name)
        try:
            self._wait_for_vm_state(session, vm_name, "Off", timeout=timeout)
        except exception.Timeout:
            # Fallback: hartes Ausschalten erzwingen.
            self._run_ps(
                session,
                "Stop-VM -Name '%s' -TurnOff -Force "
                "-ErrorAction SilentlyContinue" % vm_name)
            self._wait_for_vm_state(session, vm_name, "Off", timeout=60)

    def _get_attached_disk_paths(self, session, vm_name):
        """Gibt die VHDX-Pfade der an einer VM angehängten Disks zurück."""
        disks = self._run_ps_json(
            session,
            "Get-VMHardDiskDrive -VMName '%s' | "
            "Select-Object Path | ConvertTo-Json" % vm_name)
        return [d["Path"] for d in disks if d.get("Path")]

    def _detach_disk_from_vm(self, session, vm_name, vhdx_path):
        """Löst eine VHDX von einer VM (ohne die Datei zu löschen)."""
        self._run_ps(
            session,
            "Get-VMHardDiskDrive -VMName '%s' | "
            "Where-Object { $_.Path -eq '%s' } | "
            "Remove-VMHardDiskDrive" % (vm_name, vhdx_path))

    def _clone_vhdx(self, session, source_vhdx, vm_path):
        """Erstellt eine Kopie einer VHDX und gibt den neuen Pfad zurück."""
        clone_path = "%s\\clone-%s.vhdx" % (
            vm_path.rstrip("\\"), uuid.uuid4().hex[:8])
        self._run_ps(
            session,
            "Copy-Item -Path '%s' -Destination '%s' -Force" % (
                source_vhdx, clone_path))
        return clone_path

    # ------------------------------------------------------------------
    # BaseEndpointProvider
    # ------------------------------------------------------------------

    def get_connection_info_schema(self):
        return {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Hyper-V host name or IP address",
                },
                "port": {
                    "type": "integer",
                    "default": 5986,
                },
                "username": {
                    "type": "string",
                    "default": "Administrator",
                },
                "password": {
                    "type": "string",
                    "secret": True,
                },
                "https": {
                    "type": "boolean",
                    "default": True,
                    "description": "Use HTTPS (WinRM 5986) instead of "
                                   "HTTP (5985)",
                },
                "transport": {
                    "type": "string",
                    "default": "ntlm",
                    "description": "WinRM transport (ntlm, kerberos, "
                                   "credssp, basic)",
                },
                "cert_validation": {
                    "type": "string",
                    "default": "ignore",
                    "description": "WinRM server cert validation "
                                   "('validate' or 'ignore')",
                },
            },
            "required": ["host", "username", "password"],
        }

    def validate_connection(self, ctxt, connection_info):
        """Testet die WinRM-Verbindung zum Hyper-V Host."""
        session = self._get_winrm_session(connection_info)
        info = self._run_ps_json(
            session,
            "Get-VMHost | Select-Object Name, "
            "LogicalProcessorCount, MemoryCapacity | ConvertTo-Json")
        if info:
            LOG.info("Connected to Hyper-V host: %s", info[0].get("Name"))

    # ------------------------------------------------------------------
    # BaseEndpointDestinationOptionsProvider
    # ------------------------------------------------------------------

    def get_target_environment_schema(self):
        return {
            "type": "object",
            "properties": {
                "vm_path": {
                    "type": "string",
                    "description": "Directory on the Hyper-V host for new "
                                   "VHDX files",
                },
                "default_switch": {
                    "type": "string",
                    "description": "Default virtual switch for minion VMs",
                },
                "vm_generation": {
                    "type": "integer",
                    "enum": [1, 2],
                    "description": "Hyper-V VM generation for the target VM",
                },
                "network_map": {
                    "type": "object",
                    "description": "Source-network to Hyper-V-switch mapping",
                },
                "preserve_mac_addresses": {
                    "type": "boolean",
                    "description": "True to preserve the source VM's MAC addresses on the target VM.",
                },
            },
            "required": [],
        }

    def get_target_environment_options(self, ctxt, connection_info,
                                       env=None, option_names=None):
        session = self._get_winrm_session(connection_info)
        options = []

        if not option_names or "default_switch" in option_names:
            switches = self._run_ps_json(
                session,
                "Get-VMSwitch | Select-Object Name | ConvertTo-Json")
            options.append({
                "name": "default_switch",
                "values": [
                    {"id": s["Name"], "name": s["Name"]} for s in switches],
            })

        if not option_names or "vm_generation" in option_names:
            options.append({
                "name": "vm_generation",
                "values": [{"id": 1, "name": "Generation 1"},
                           {"id": 2, "name": "Generation 2"}],
            })

        return options

    # ------------------------------------------------------------------
    # BaseEndpointNetworksProvider
    # ------------------------------------------------------------------

    def get_networks(self, ctxt, connection_info, env):
        session = self._get_winrm_session(connection_info)
        switches = self._run_ps_json(
            session,
            "Get-VMSwitch | Select-Object Id, Name | ConvertTo-Json")
        return [
            {"id": s.get("Id", s["Name"]), "name": s["Name"]}
            for s in switches
        ]

    # ------------------------------------------------------------------
    # BaseEndpointStorageProvider
    # ------------------------------------------------------------------

    def get_storage(self, ctxt, connection_info, target_environment):
        """Listet verfügbare Speicherorte (Volumes) auf dem Hyper-V Host."""
        session = self._get_winrm_session(connection_info)
        volumes = self._run_ps_json(
            session,
            "Get-Volume | Where-Object { $_.DriveLetter } | "
            "Select-Object DriveLetter, SizeRemaining | ConvertTo-Json")
        backends = []
        for v in volumes:
            drive = v.get("DriveLetter")
            if drive:
                path = "%s:\\VMs" % drive
                backends.append({"id": path, "name": path})
        return {"storage_backends": backends}

    # ------------------------------------------------------------------
    # BaseInstanceFlavorProvider
    # ------------------------------------------------------------------

    def get_optimal_flavor(self, ctxt, connection_info,
                           target_environment, export_info):
        """Hyper-V hat kein Flavor-Konzept; CPU/Memory werden direkt
        aus den Export-Infos übernommen."""
        return None

    # ------------------------------------------------------------------
    # BaseReplicaImportProvider (KERN)
    # ------------------------------------------------------------------

    def deploy_replica_disks(self, ctxt, connection_info,
                             target_environment, instance_name,
                             export_info, volumes_info):
        """Erstellt Ziel-VHDX-Dateien auf dem Hyper-V Host.

        Für jede Disk in export_info wird eine Fixed-VHDX angelegt.
        Existierende VHDX werden wiederverwendet/vergrößert.
        """
        session = self._get_winrm_session(connection_info)
        vm_path = self._get_vm_path(target_environment)

        # Verfügbare Storage-Backends für das Mapping ermitteln
        storage_backends = self.get_storage(
            ctxt, connection_info,
            target_environment).get("storage_backends", [])

        existing = {v["disk_id"]: v for v in volumes_info}
        new_volumes_info = []

        for disk in export_info.get("devices", {}).get("disks", []):
            disk_id = disk.get(
                "id", disk.get("path", "disk-%d" % len(new_volumes_info)))
            size = disk["size_bytes"]

            target_path = vm_path
            if storage_backends:
                mapped_backend = provider_utils.get_storage_mapping_for_disk(
                    target_environment.get("storage_mappings", {}),
                    disk,
                    storage_backends,
                    config_default=vm_path,
                    error_on_missing_mapping=False,
                    error_on_backend_not_found=False)
                if mapped_backend:
                    target_path = mapped_backend

            vhdx_path = self._vhdx_path(target_path, instance_name, disk_id)

            disk_exists = False
            if disk_id in existing:
                old_vol = existing[disk_id]
                check = self._run_ps(
                    session,
                    "Test-Path -Path '%s'" % old_vol.get("volume_id", ""))
                disk_exists = check.strip().lower() == "true"

            if disk_exists:
                old_vol = existing[disk_id]
                self._ensure_vhdx_size(
                    session, old_vol["volume_id"], size)
                old_vol["size"] = size
                old_vol["size_bytes"] = size
                new_volumes_info.append(old_vol)
            else:
                self._run_ps(
                    session,
                    "New-VHD -Path '%s' -Fixed -SizeBytes %d | Out-Null" % (
                        vhdx_path, size))
                new_volumes_info.append({
                    "disk_id": disk_id,
                    "volume_id": vhdx_path,
                    "volume_name": os.path.basename(vhdx_path),
                    "size": size,
                    "size_bytes": size,
                })

        return new_volumes_info

    def _ensure_vhdx_size(self, session, vhdx_path, required_size_bytes):
        """Vergrößert eine VHDX bei Bedarf auf required_size_bytes."""
        out = self._run_ps(
            session,
            "(Get-VHD -Path '%s').Size" % vhdx_path)
        try:
            current = int(out.strip())
        except (ValueError, AttributeError):
            current = 0
        if current < required_size_bytes:
            self._run_ps(
                session,
                "Resize-VHD -Path '%s' -SizeBytes %d" % (
                    vhdx_path, required_size_bytes))

    def deploy_replica_target_resources(self, ctxt, connection_info,
                                        target_environment, volumes_info):
        """Deployed Destination-Minion mit HTTP Backup Writer."""
        session = self._get_winrm_session(connection_info)

        minion = self._create_minion_vm(session, target_environment)
        vm_name = minion["name"]

        for vol in volumes_info:
            self._attach_disk_to_vm(session, vm_name, vol["volume_id"])

        self._run_ps(session, "Start-VM -Name '%s'" % vm_name)
        self._wait_for_vm_state(session, vm_name, "Running")
        vm_ip = self._get_vm_ip(session, vm_name)

        ssh_conn_info = {
            "ip": vm_ip,
            "port": 22,
            "username": "ubuntu",
            "password": connection_info.get("minion_password"),
            "pkey": self._get_minion_ssh_key(),
        }

        bootstrapper = backup_writers.HTTPBackupWriterBootstrapper(
            ssh_conn_info, CONF.hyperv.writer_port)
        writer_conn_details = bootstrapper.setup_writer()

        # Disks werden auf dem Linux-Minion als /dev/sdX sichtbar.
        # Reihenfolge entspricht der Attach-Reihenfolge (nach Boot-Disk).
        for idx, vol in enumerate(volumes_info):
            vol["volume_dev"] = "/dev/sd%s" % chr(ord("b") + idx)

        return {
            "migr_resources": {
                "minion_vm_name": vm_name,
                "minion_boot_vhdx": minion["boot_vhdx"],
                "writer_port": CONF.hyperv.writer_port,
            },
            "volumes_info": volumes_info,
            "connection_info": {
                "backend": "http_backup_writer",
                "connection_details": writer_conn_details,
            },
        }

    def delete_replica_target_resources(self, ctxt, connection_info,
                                        target_environment,
                                        migr_resources_dict):
        """Minion-VM nach Transfer aufräumen."""
        session = self._get_winrm_session(connection_info)
        vm_name = migr_resources_dict["minion_vm_name"]
        boot_vhdx = migr_resources_dict.get("minion_boot_vhdx")
        self._delete_vm(session, vm_name, delete_boot_vhdx=boot_vhdx)

    def delete_replica_disks(self, ctxt, connection_info,
                             target_environment, volumes_info):
        """Alle Replika-VHDX löschen."""
        session = self._get_winrm_session(connection_info)
        for vol in volumes_info:
            vhdx = vol.get("volume_id")
            if vhdx:
                try:
                    self._run_ps(
                        session,
                        "Remove-Item -Path '%s' -Force "
                        "-ErrorAction SilentlyContinue" % vhdx)
                except Exception as e:
                    LOG.warning(
                        "Failed to remove VHDX %s: %s", vhdx, e)

    def deploy_replica_instance(self, ctxt, connection_info,
                                target_environment, instance_name,
                                export_info, volumes_info, clone_disks):
        """Erstellt die finale Ziel-VM aus den replizierten VHDX-Disks."""
        session = self._get_winrm_session(connection_info)

        memory_bytes = export_info.get("memory_mb", 4096) * 1024 * 1024
        vcpus = export_info.get("num_cpu", 2)
        vm_name = instance_name[:64]
        vm_path = self._get_vm_path(target_environment)

        generation = target_environment.get("vm_generation")
        if not generation:
            generation = 2 if export_info.get(
                "firmware_type") == "EFI" else 1

        network_map = target_environment.get("network_map", {})
        switches = list(network_map.values())
        first_switch = switches[0] if switches else self._get_default_switch(
            session, target_environment)

        # Boot-Disk (erste VHDX) festlegen
        boot_vhdx = volumes_info[0]["volume_id"] if volumes_info else None

        script = (
            "New-VM -Name '%(name)s' -MemoryStartupBytes %(mem)d "
            "-Generation %(gen)d -Path '%(path)s' "
            "-NoVHD | Out-Null; "
            "Set-VMProcessor -VMName '%(name)s' -Count %(cpus)d;" % {
                "name": vm_name,
                "mem": memory_bytes,
                "gen": generation,
                "path": vm_path,
                "cpus": vcpus,
            })
        self._run_ps(session, script)

        # Disks attachieren (Boot-Disk zuerst). Bei clone_disks wird eine
        # Kopie der Replika-VHDX angehängt, damit die Replika erhalten bleibt.
        for vol in volumes_info:
            disk_path = vol["volume_id"]
            if clone_disks:
                disk_path = self._clone_vhdx(session, disk_path, vm_path)
                vol["clone_id"] = disk_path
                if vol["volume_id"] == boot_vhdx:
                    boot_vhdx = disk_path
            self._attach_disk_to_vm(session, vm_name, disk_path)

        # Bei Generation 2: Boot-Reihenfolge auf erste HDD setzen
        if generation == 2 and boot_vhdx:
            self._run_ps(
                session,
                "$d = Get-VMHardDiskDrive -VMName '%s' | "
                "Where-Object { $_.Path -eq '%s' }; "
                "if ($d) { Set-VMFirmware -VMName '%s' "
                "-FirstBootDevice $d }" % (vm_name, boot_vhdx, vm_name))

        # NICs konfigurieren (via network_map auf Switches)
        nics = export_info.get("devices", {}).get("nics", [])
        preserve_mac = target_environment.get("preserve_mac_addresses", False)

        # Default-Adapter der VM mit erstem Switch verbinden
        self._run_ps(
            session,
            "Connect-VMNetworkAdapter -VMName '%s' -SwitchName '%s' "
            "-ErrorAction SilentlyContinue" % (vm_name, first_switch))

        if preserve_mac and nics:
            mac_addr = nics[0].get("mac_address")
            if mac_addr:
                clean_mac = mac_addr.replace(":", "").replace("-", "")
                self._run_ps(
                    session,
                    "Set-VMNetworkAdapter -VMName '%s' -MacAddress '%s' "
                    "-StaticMacAddress $true -ErrorAction SilentlyContinue" % (
                        vm_name, clean_mac))

        # Zusätzliche NICs hinzufügen
        for nic in nics[1:]:
            src_net = nic.get("network_name") or nic.get("network_id")
            dst_switch = network_map.get(src_net) if src_net else None
            if not dst_switch:
                dst_switch = first_switch

            mac_cmd = ""
            if preserve_mac:
                mac_addr = nic.get("mac_address")
                if mac_addr:
                    clean_mac = mac_addr.replace(":", "").replace("-", "")
                    mac_cmd = " -MacAddress '%s' -StaticMacAddress $true" % clean_mac

            self._run_ps(
                session,
                "Add-VMNetworkAdapter -VMName '%s' -SwitchName '%s'%s "
                "-ErrorAction SilentlyContinue" % (
                    vm_name, dst_switch, mac_cmd))

        return {
            "instance_deployment_info": {
                "vm_name": vm_name,
                "vm_id": vm_name,
                "os_type": self._detect_os_type(export_info),
                "disk_paths": [v["volume_id"] for v in volumes_info],
                "boot_disk_path": boot_vhdx,
                "nics_info": [
                    {
                        "name": nic.get("name", "nic-%d" % idx),
                        "mac_address": nic.get("mac_address"),
                    }
                    for idx, nic in enumerate(nics)
                ],
            }
        }

    def finalize_replica_instance_deployment(self, ctxt, connection_info,
                                             target_environment,
                                             instance_deployment_info):
        """VM starten und finale Informationen zurückgeben."""
        session = self._get_winrm_session(connection_info)
        vm_name = instance_deployment_info["vm_name"]

        self._run_ps(session, "Start-VM -Name '%s'" % vm_name)

        info = self._run_ps_json(
            session,
            "Get-VM -Name '%s' | Select-Object Name, ProcessorCount, "
            "MemoryStartup | ConvertTo-Json" % vm_name)
        vm = info[0] if info else {}

        return {
            "id": vm_name,
            "name": vm_name,
            "num_cpu": vm.get("ProcessorCount", 0),
            "memory_mb": int(vm.get("MemoryStartup", 0)) // (1024 * 1024),
            "os_type": instance_deployment_info.get("os_type", "linux"),
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

    def cleanup_failed_replica_instance_deployment(
            self, ctxt, connection_info, target_environment,
            instance_deployment_info):
        """Löscht die Ziel-VM bei fehlgeschlagenem Deployment."""
        if not instance_deployment_info:
            return
        session = self._get_winrm_session(connection_info)
        vm_name = instance_deployment_info.get("vm_name")
        if vm_name:
            self._delete_vm(session, vm_name)

    def create_replica_disk_snapshots(
            self, ctxt, connection_info, target_environment, volumes_info):
        """Snapshots der Replika-Disks.

        Während des Transfers sind die VHDX-Dateien nicht an eine
        laufende VM gebunden, daher gibt es kein VM-Checkpoint-Konzept.
        Wie beim OLVM-Provider wird hier kein Snapshot erstellt; für
        konsistente Deployments wird der ``clone_disks=True``-Pfad in
        ``deploy_replica_instance`` genutzt.
        """
        return volumes_info

    def delete_replica_target_disk_snapshots(self, ctxt, connection_info,
                                             target_environment,
                                             volumes_info):
        """No-op (siehe ``create_replica_disk_snapshots``)."""
        return volumes_info

    def restore_replica_disk_snapshots(self, ctxt, connection_info,
                                       target_environment, volumes_info):
        """No-op (Fallback auf ``clone_disks=True`` beim Deployment)."""
        return volumes_info

    # ------------------------------------------------------------------
    # BaseImportInstanceProvider (OS Morphing)
    # ------------------------------------------------------------------

    def deploy_os_morphing_resources(self, ctxt, connection_info,
                                     target_environment,
                                     instance_deployment_info):
        """OS-Morphing-Minion bereitstellen.

        Stoppt die Ziel-VM, hängt ihre Daten-Disks an einen frischen
        Linux-Minion (Ubuntu-Template), startet diesen und liefert die
        SSH-Verbindungsdaten zurück. Der OS-Morphing-Manager mountet
        anschließend die Disks per chroot und installiert die für
        Hyper-V nötigen Treiber/Tools (hv_* Module, cloud-init bzw.
        Windows Integration Services).
        """
        session = self._get_winrm_session(connection_info)
        target_vm_name = instance_deployment_info["vm_name"]

        # Disks der Ziel-VM ermitteln (Fallback auf gespeicherte Pfade)
        disk_paths = self._get_attached_disk_paths(session, target_vm_name)
        if not disk_paths:
            disk_paths = instance_deployment_info.get("disk_paths", [])
        boot_disk_path = instance_deployment_info.get("boot_disk_path")
        if not boot_disk_path and disk_paths:
            boot_disk_path = disk_paths[0]

        # Ziel-VM herunterfahren
        self._stop_vm(session, target_vm_name)

        # Daten-Disks von der Ziel-VM lösen
        for path in disk_paths:
            try:
                self._detach_disk_from_vm(session, target_vm_name, path)
            except Exception as e:
                LOG.warning(
                    "Failed to detach disk %s from target VM %s: %s",
                    path, target_vm_name, e)

        # Morphing-Minion erstellen
        minion = self._create_minion_vm(
            session, target_environment, name_suffix="osmorphing")
        minion_vm_name = minion["name"]

        # Daten-Disks an Minion hängen (Boot-Disk zuerst, damit die
        # Reihenfolge der /dev/sdX-Devices vorhersehbar ist)
        ordered_paths = list(disk_paths)
        if boot_disk_path and boot_disk_path in ordered_paths:
            ordered_paths.remove(boot_disk_path)
            ordered_paths.insert(0, boot_disk_path)
        for path in ordered_paths:
            self._attach_disk_to_vm(session, minion_vm_name, path)

        # Minion starten und IP ermitteln
        self._run_ps(session, "Start-VM -Name '%s'" % minion_vm_name)
        self._wait_for_vm_state(session, minion_vm_name, "Running")
        vm_ip = self._get_vm_ip(session, minion_vm_name)

        os_type = instance_deployment_info.get("os_type", "linux")
        nics_info = instance_deployment_info.get("nics_info", [])

        return {
            "os_morphing_resources": {
                "minion_vm_name": minion_vm_name,
                "minion_boot_vhdx": minion["boot_vhdx"],
                "target_vm_name": target_vm_name,
                "boot_disk_path": boot_disk_path,
                "disk_paths": disk_paths,
            },
            "osmorphing_connection_info": {
                "ip": vm_ip,
                "port": 22,
                "username": "ubuntu",
                "password": connection_info.get("minion_password"),
                "pkey": self._get_minion_ssh_key(),
            },
            "osmorphing_info": {
                "os_type": os_type,
                "nics_info": nics_info,
                "nics_set_dhcp": True,
                "osmorphing_parameters": {
                    "retain_user_credentials": True,
                },
            },
        }

    def delete_os_morphing_resources(self, ctxt, connection_info,
                                     target_environment,
                                     os_morphing_resources):
        """OS-Morphing-Minion aufräumen, Disks zurück zur Ziel-VM."""
        if not os_morphing_resources:
            return
        session = self._get_winrm_session(connection_info)
        minion_vm_name = os_morphing_resources.get("minion_vm_name")
        minion_boot_vhdx = os_morphing_resources.get("minion_boot_vhdx")
        target_vm_name = os_morphing_resources.get("target_vm_name")
        boot_disk_path = os_morphing_resources.get("boot_disk_path")
        disk_paths = os_morphing_resources.get("disk_paths", [])

        # Minion herunterfahren, damit die Disks freigegeben werden
        if minion_vm_name:
            try:
                self._stop_vm(session, minion_vm_name)
            except Exception as e:
                LOG.warning(
                    "Failed to stop morphing minion %s: %s",
                    minion_vm_name, e)
            for path in disk_paths:
                try:
                    self._detach_disk_from_vm(
                        session, minion_vm_name, path)
                except Exception as e:
                    LOG.warning(
                        "Failed to detach disk %s from minion %s: %s",
                        path, minion_vm_name, e)

        # Disks zurück an die Ziel-VM hängen (Boot-Disk zuerst)
        if target_vm_name:
            ordered_paths = list(disk_paths)
            if boot_disk_path and boot_disk_path in ordered_paths:
                ordered_paths.remove(boot_disk_path)
                ordered_paths.insert(0, boot_disk_path)
            for path in ordered_paths:
                try:
                    self._attach_disk_to_vm(
                        session, target_vm_name, path)
                except Exception as e:
                    LOG.warning(
                        "Failed to reattach disk %s to target VM %s: %s",
                        path, target_vm_name, e)

        # Minion löschen
        if minion_vm_name:
            self._delete_vm(
                session, minion_vm_name,
                delete_boot_vhdx=minion_boot_vhdx)

    # ------------------------------------------------------------------
    # BaseReplicaImportValidationProvider
    # ------------------------------------------------------------------

    def validate_replica_import_input(self, ctxt, connection_info,
                                      target_environment, export_info,
                                      check_os_morphing_resources=False,
                                      check_final_vm_params=False):
        """Prüft ob die Hyper-V Zielumgebung das Import akzeptieren kann."""
        session = self._get_winrm_session(connection_info)

        # Host erreichbar?
        self._run_ps(session, "Get-VMHost | Out-Null")

        # Switch vorhanden?
        switch = (target_environment.get("default_switch") or
                  CONF.hyperv.default_switch)
        if switch:
            switches = self._run_ps_json(
                session,
                "Get-VMSwitch -Name '%s' -ErrorAction SilentlyContinue | "
                "Select-Object Name | ConvertTo-Json" % switch)
            if not switches:
                raise exception.InvalidInput(
                    "Hyper-V virtual switch '%s' not found" % switch)

        # Minion-Template konfiguriert?
        template_vhdx = (
            target_environment.get("minion_template_vhdx") or
            CONF.hyperv.minion_template_vhdx)
        if not template_vhdx:
            raise exception.InvalidInput(
                "No minion template VHDX configured "
                "(hyperv.minion_template_vhdx)")

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
        """Gibt Hyper-V/Linux-spezifische OS-Morphing-Tools zurück.

        Reuse der Standard-Morphing-Tools (Hyper-V Integration Services
        sind in modernen Kerneln/Windows enthalten). Vollständige
        Hyper-V-spezifische Tools folgen in Phase 2.
        """
        from coriolis import constants
        from coriolis.osmorphing import amazon
        from coriolis.osmorphing import centos
        from coriolis.osmorphing import coreos
        from coriolis.osmorphing import debian
        from coriolis.osmorphing import openwrt
        from coriolis.osmorphing import oracle
        from coriolis.osmorphing import redhat
        from coriolis.osmorphing import rocky
        from coriolis.osmorphing import suse
        from coriolis.osmorphing import ubuntu
        from coriolis.osmorphing import windows

        os_morphers = {
            constants.OS_TYPE_LINUX: [
                amazon.BaseAmazonLinuxOSMorphingTools,
                centos.BaseCentOSMorphingTools,
                coreos.BaseCoreOSMorphingTools,
                debian.BaseDebianMorphingTools,
                openwrt.BaseOpenWRTMorphingTools,
                oracle.BaseOracleMorphingTools,
                redhat.BaseRedHatMorphingTools,
                rocky.BaseRockyLinuxMorphingTools,
                suse.BaseSUSEMorphingTools,
                ubuntu.BaseUbuntuMorphingTools,
            ],
            constants.OS_TYPE_WINDOWS: [
                windows.BaseWindowsMorphingTools,
            ]
        }
        return os_morphers.get(os_type, [])
