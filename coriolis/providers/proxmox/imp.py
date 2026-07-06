# Copyright 2026 Thesolution.at
# All Rights Reserved.

import os
import time

from oslo_config import cfg
from oslo_log import log as logging

from coriolis import exception
from coriolis.providers import backup_writers
from coriolis.providers import base
from coriolis import utils

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

proxmox_opts = [
    cfg.IntOpt('writer_port',
               default=6677,
               help='Port for the coriolis-writer service'),
    cfg.IntOpt('minion_memory_mb',
               default=4096,
               help='RAM for temporary worker/minion VMs (MB)'),
    cfg.IntOpt('minion_vcpus',
               default=2,
               help='vCPUs for temporary worker/minion VMs'),
    cfg.StrOpt('minion_template_id',
               default=None,
               help='Proxmox VM template ID or name for minion VMs'),
    cfg.StrOpt('minion_ssh_key_path',
               default=None,
               help='Path to SSH private key for minion access'),
    cfg.StrOpt('migration_log_dir',
               default='/var/log/coriolis/migrations',
               help='Directory for per-migration JSON-Lines log files'),
]
CONF.register_opts(proxmox_opts, group='proxmox')


class ProxmoxImportProvider(
        base.BaseEndpointProvider,
        base.BaseEndpointDestinationOptionsProvider,
        base.BaseEndpointNetworksProvider,
        base.BaseEndpointStorageProvider,
        base.BaseInstanceFlavorProvider,
        base.BaseReplicaImportProvider,
        base.BaseReplicaImportValidationProvider,
        base.BaseUpdateDestinationReplicaProvider,
):
    platform = "proxmox"

    def __init__(self, event_manager):
        self._event_manager = event_manager

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_proxmox_connection(self, connection_info):
        """Creates a Proxmox API client connection."""
        from proxmoxer import ProxmoxAPI

        url = connection_info.get("url")
        username = connection_info["username"]
        password = connection_info.get("password")
        token_name = connection_info.get("token_name")
        token_value = connection_info.get("token_value")
        insecure = connection_info.get("insecure", True)

        if token_name and token_value:
            return ProxmoxAPI(
                url,
                user=username,
                token_name=token_name,
                token_value=token_value,
                verify_ssl=not insecure
            )
        else:
            return ProxmoxAPI(
                url,
                user=username,
                password=password,
                verify_ssl=not insecure
            )

    def _find_vm_by_name(self, conn, name):
        """Searches all nodes for a VM matching the given name."""
        for node in conn.nodes.get():
            node_name = node["node"]
            for vm in conn.nodes(node_name).qemu.get():
                if vm.get("name") == name:
                    return node_name, vm["vmid"]
        return None, None

    def _resolve_template_vmid(self, conn, template_ref):
        """Resolves template ID or Name to a VMID integer."""
        try:
            return int(template_ref)
        except (ValueError, TypeError):
            pass

        for node in conn.nodes.get():
            node_name = node["node"]
            for vm in conn.nodes(node_name).qemu.get():
                if vm.get("name") == template_ref:
                    return vm["vmid"]

        raise exception.CoriolisException(
            f"Template VM '{template_ref}' not found on Proxmox cluster.")

    def _create_minion_vm(
            self, conn, node, target_environment,
            name_suffix="minion"):
        """Clones a minion VM from the template."""
        minion_vmid = conn.cluster.nextid.get()
        template_ref = CONF.proxmox.minion_template_id
        if not template_ref:
            raise exception.CoriolisException(
                "Missing 'minion_template_id' configuration option "
                "in the proxmox group.")

        template_vmid = self._resolve_template_vmid(conn, template_ref)

        # Clone request
        clone_params = {
            "newid": minion_vmid,
            "name": f"coriolis-{name_suffix}-{minion_vmid}",
            "full": 1,
        }
        conn.nodes(node).qemu(template_vmid).clone.post(**clone_params)

        # Apply memory / CPU configurations
        config_params = {
            "memory": CONF.proxmox.minion_memory_mb,
            "cores": CONF.proxmox.minion_vcpus,
        }
        conn.nodes(node).qemu(minion_vmid).config.post(**config_params)

        return minion_vmid

    def _wait_for_vm_up(self, conn, node, vmid, timeout=300):
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = conn.nodes(node).qemu(vmid).status.current.get()
            if status.get("status") == "running":
                return
            time.sleep(5)
        raise exception.CoriolisException(
            f"VM {vmid} did not start running within {timeout} seconds.")

    def _wait_for_vm_down(self, conn, node, vmid, timeout=300):
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                status = conn.nodes(node).qemu(vmid).status.current.get()
                if status.get("status") == "stopped":
                    return
            except Exception:
                # VM might have been deleted
                return
            time.sleep(5)
        raise exception.CoriolisException(
            f"VM {vmid} did not stop running within {timeout} seconds.")

    def _wait_for_task(self, conn, node, upid, timeout=600):
        """Polls a Proxmox task until it is stopped/finished."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = conn.nodes(node).tasks(upid).status.get()
            if status.get("status") == "stopped":
                exitstatus = status.get("exitstatus", "")
                if exitstatus != "OK":
                    raise exception.CoriolisException(
                        f"Proxmox task {upid} failed: {exitstatus}")
                return
            time.sleep(5)
        raise exception.CoriolisException(
            f"Proxmox task {upid} timed out after {timeout} seconds.")

    def _get_vm_ip(self, conn, node, vmid, timeout=900):
        """Obtains VM IP address from the QEMU Guest Agent."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                agent = conn.nodes(node).qemu(vmid).agent
                interfaces = agent.get("network-get-interfaces")
                for iface in interfaces.get("result", []):
                    for ip_info in iface.get("ip-addresses", []):
                        ip = ip_info.get("ip-address")
                        if ip_info.get("ip-address-type") == "ipv4":
                            if not ip.startswith("127."):
                                return ip
            except Exception:
                pass
            time.sleep(10)
        raise exception.CoriolisException(
            f"Timed out waiting for VM {vmid} IP address from "
            f"QEMU guest agent.")

    def _get_minion_ssh_key(self):
        key_path = CONF.proxmox.minion_ssh_key_path
        if key_path and os.path.exists(key_path):
            with open(key_path, 'r') as f:
                return f.read()
        return None

    def _detect_os_type(self, export_info):
        return export_info.get("os_type", "linux")

    def _delete_vm(self, conn, node, vmid):
        try:
            status = conn.nodes(node).qemu(vmid).status.current.get()
            if status.get("status") == "running":
                conn.nodes(node).qemu(vmid).status.stop.post()
                self._wait_for_vm_down(conn, node, vmid)
        except Exception:
            pass

        try:
            conn.nodes(node).qemu(vmid).delete()
        except Exception as e:
            LOG.warning("Failed to delete VM %s: %s", vmid, e)

    # ------------------------------------------------------------------
    # BaseEndpointProvider
    # ------------------------------------------------------------------

    def get_connection_info_schema(self):
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": (
                        "Proxmox API URL (e.g. "
                        "https://pve.example.com:8006/api2/json)"),
                },
                "username": {
                    "type": "string",
                    "description": "Username (e.g. root@pam or user@pve)",
                },
                "password": {
                    "type": "string",
                    "secret": True,
                    "description": "Proxmox password",
                },
                "token_name": {
                    "type": "string",
                    "description": "Optional API Token Name",
                },
                "token_value": {
                    "type": "string",
                    "secret": True,
                    "description": "Optional API Token Value",
                },
                "insecure": {
                    "type": "boolean",
                    "default": True,
                },
            },
            "required": ["url", "username"],
        }

    def validate_connection(self, ctxt, connection_info):
        conn = self._get_proxmox_connection(connection_info)
        try:
            nodes = conn.nodes.get()
            LOG.info("Connected to Proxmox VE. Found %d nodes.", len(nodes))
        except Exception as e:
            raise exception.InvalidInput(f"Failed to connect to Proxmox: {e}")

    # ------------------------------------------------------------------
    # BaseEndpointDestinationOptionsProvider
    # ------------------------------------------------------------------

    def get_target_environment_schema(self):
        return {
            "type": "object",
            "properties": {
                "node": {
                    "type": "string",
                    "description": "Target Proxmox Node name",
                },
                "storage": {
                    "type": "string",
                    "description": "Target storage domain name",
                },
                "network_map": {
                    "type": "object",
                    "description": (
                        "Mapping from source network to target bridge"),
                },
                "preserve_mac_addresses": {
                    "type": "boolean",
                    "description": "Preserve source MAC addresses",
                },
            },
            "required": ["node", "storage"],
        }

    def get_target_environment_options(self, ctxt, connection_info,
                                       env=None, option_names=None):
        conn = self._get_proxmox_connection(connection_info)
        options = []

        if not option_names or "node" in option_names:
            nodes = [
                {"id": n["node"], "name": n["node"]}
                for n in conn.nodes.get()
            ]
            options.append({
                "name": "node",
                "values": nodes,
            })

        if not option_names or "storage" in option_names:
            storages = [
                {"id": s["storage"], "name": s["storage"]}
                for s in conn.storage.get()
                if s.get("active") == 1
            ]
            options.append({
                "name": "storage",
                "values": storages,
            })

        return options

    # ------------------------------------------------------------------
    # BaseEndpointNetworksProvider
    # ------------------------------------------------------------------

    def get_networks(self, ctxt, connection_info, env):
        conn = self._get_proxmox_connection(connection_info)
        node = env.get("node")
        if not node:
            node = conn.nodes.get()[0]["node"]

        networks = []
        for net in conn.nodes(node).network.get():
            if net.get("type") == "bridge":
                networks.append({
                    "id": net["iface"],
                    "name": net["iface"]
                })
        return networks

    # ------------------------------------------------------------------
    # BaseEndpointStorageProvider
    # ------------------------------------------------------------------

    def get_storage(self, ctxt, connection_info, target_environment):
        conn = self._get_proxmox_connection(connection_info)
        node = target_environment["node"]
        storage = target_environment["storage"]

        status = conn.nodes(node).storage(storage).status.get()
        return {
            "total_bytes": status.get("total", 0),
            "available_bytes": status.get("avail", 0),
            "used_bytes": status.get("used", 0),
        }

    # ------------------------------------------------------------------
    # BaseInstanceFlavorProvider
    # ------------------------------------------------------------------

    def get_optimal_flavor(
            self, ctxt, connection_info, instance_name, export_info):
        flavor_vcpus = export_info.get("vcpus", 2)
        flavor_memory = export_info.get("memory_mb", 4096)
        return {
            "vcpus": flavor_vcpus,
            "memory_mb": flavor_memory,
        }

    # ------------------------------------------------------------------
    # BaseReplicaImportProvider
    # ------------------------------------------------------------------

    def deploy_replica_disks(self, ctxt, connection_info,
                             target_environment, instance_name,
                             export_info, volumes_info):
        conn = self._get_proxmox_connection(connection_info)
        node = target_environment["node"]
        storage = target_environment["storage"]

        # Find if VM already exists to fetch its VMID
        target_node, target_vmid = self._find_vm_by_name(conn, instance_name)
        if not target_vmid:
            target_vmid = conn.cluster.nextid.get()

        existing = {v["disk_id"]: v for v in volumes_info}
        new_volumes_info = []

        disks = export_info.get("devices", {}).get("disks", [])
        for index, disk in enumerate(disks):
            disk_id = disk.get("id", disk.get("path", f"disk-{index}"))
            size = disk["size_bytes"]

            disk_exists = False
            vol_id = None

            if disk_id in existing:
                vol_id = existing[disk_id]["volume_id"]
                try:
                    storage_name, vol_name = vol_id.split(":", 1)
                    conn.nodes(node).storage(storage_name).content(
                        vol_name).get()
                    disk_exists = True
                except Exception:
                    LOG.warning(
                        "Disk %s not found on storage, will recreate.",
                        vol_id)

            if not disk_exists:
                # Create disk image
                size_gb = int(size / (1024 ** 3))
                if size_gb <= 0:
                    size_gb = 1
                res = conn.nodes(node).storage(storage).content.post(
                    vmid=target_vmid,
                    size=f"{size_gb}G",
                    filename=f"vm-{target_vmid}-disk-{index}",
                )
                vol_id = res if isinstance(res, str) else res.get("volid")

            new_volumes_info.append({
                "disk_id": disk_id,
                "volume_id": vol_id,
                "target_vmid": target_vmid,
            })

        # Cleanup disks that are no longer present
        current_disk_ids = [
            d.get("id", d.get("path")) for d in disks
        ]
        for disk_id, vol in existing.items():
            if disk_id not in current_disk_ids:
                try:
                    storage_name, vol_name = vol["volume_id"].split(":", 1)
                    conn.nodes(node).storage(storage_name).content(
                        vol_name).delete()
                except Exception as e:
                    LOG.warning(
                        "Failed to delete unused disk %s: %s",
                        vol["volume_id"], e)

        return new_volumes_info

    def deploy_replica_target_resources(self, ctxt, connection_info,
                                        target_environment, volumes_info):
        conn = self._get_proxmox_connection(connection_info)
        node = target_environment["node"]

        # Create minion VM
        minion_vmid = self._create_minion_vm(conn, node, target_environment)

        # Attach volumes to minion VM config with predictable serial
        for index, vol in enumerate(volumes_info):
            disk_key = f"scsi{index + 1}"  # scsi0 is the minion's boot disk
            vol_id = vol["volume_id"]
            serial = f"cvol-{index}"
            conn.nodes(node).qemu(minion_vmid).config.post(
                **{disk_key: f"{vol_id},serial={serial}"}
            )

        # Start Minion VM
        conn.nodes(node).qemu(minion_vmid).status.start.post()
        self._wait_for_vm_up(conn, node, minion_vmid)

        # Get Minion IP
        minion_ip = self._get_vm_ip(conn, node, minion_vmid)

        # Bootstrap HTTPBackupWriter
        ssh_pkey = self._get_minion_ssh_key()
        ssh_conn_info = {
            "ip": minion_ip,
            "port": 22,
            "username": "root",
            "password": connection_info.get("password"),
            "pkey": ssh_pkey,
        }

        bootstrapper = backup_writers.HTTPBackupWriterBootstrapper(
            ssh_conn_info, CONF.proxmox.writer_port)
        writer_conn_details = bootstrapper.setup_writer()

        # Find the device paths inside the Minion
        ssh_client = bootstrapper._ssh
        for index, vol in enumerate(volumes_info):
            serial = f"cvol-{index}"
            cmd = (
                f"find -L /dev/disk/by-id/ -name '*cvol-{index}*' "
                f"-o -name '*{serial}*'")
            dev_path = None
            for _ in range(6):
                try:
                    out = utils.exec_ssh_cmd(
                        ssh_client, cmd).strip().splitlines()
                    if out:
                        dev_path = out[0]
                        break
                except Exception:
                    pass
                time.sleep(5)

            if not dev_path:
                raise exception.CoriolisException(
                    f"Could not find device for volume {vol['volume_id']} "
                    f"with serial {serial} on Minion VM.")
            vol["volume_dev"] = dev_path

        return {
            "migr_resources": {
                "minion_vm_id": minion_vmid,
                "writer_port": CONF.proxmox.writer_port,
            },
            "volumes_info": volumes_info,
            "connection_info": {
                "backend": "http_backup_writer",
                "connection_details": writer_conn_details,
            },
        }

    def delete_replica_target_resources(self, ctxt, connection_info,
                                        target_environment, migr_resources):
        conn = self._get_proxmox_connection(connection_info)
        node = target_environment["node"]
        minion_vmid = migr_resources["minion_vm_id"]

        # Stop VM
        try:
            status = conn.nodes(node).qemu(minion_vmid).status.current.get()
            if status.get("status") == "running":
                conn.nodes(node).qemu(minion_vmid).status.stop.post()
                self._wait_for_vm_down(conn, node, minion_vmid)
        except Exception as e:
            LOG.warning("Failed to stop minion VM %s: %s", minion_vmid, e)

        # Detach replica disks from Minion configuration before deleting it
        try:
            config = conn.nodes(node).qemu(minion_vmid).config.get()
            to_delete = []
            for key in config.keys():
                if key.startswith("scsi") and key != "scsi0":
                    to_delete.append(key)
            if to_delete:
                conn.nodes(node).qemu(minion_vmid).config.post(
                    delete=",".join(to_delete))
        except Exception as e:
            LOG.warning(
                "Failed to detach disks from minion VM %s: %s",
                minion_vmid, e)

        # Delete Minion VM
        try:
            conn.nodes(node).qemu(minion_vmid).delete()
        except Exception as e:
            LOG.warning("Failed to delete minion VM %s: %s", minion_vmid, e)

    def delete_replica_disks(self, ctxt, connection_info,
                             target_environment, volumes_info):
        conn = self._get_proxmox_connection(connection_info)
        node = target_environment["node"]

        for vol in volumes_info:
            try:
                storage_name, vol_name = vol["volume_id"].split(":", 1)
                conn.nodes(node).storage(storage_name).content(
                    vol_name).delete()
            except Exception as e:
                LOG.warning(
                    "Failed to delete replica disk %s: %s",
                    vol["volume_id"], e)

    def deploy_replica_instance(self, ctxt, connection_info,
                                target_environment, instance_name,
                                export_info, volumes_info, clone_disks):
        conn = self._get_proxmox_connection(connection_info)
        node = target_environment["node"]
        storage = target_environment["storage"]

        # Delete VM if it already exists
        target_node, target_vmid = self._find_vm_by_name(conn, instance_name)
        if target_vmid:
            self._delete_vm(conn, target_node, target_vmid)

        if not target_vmid:
            target_vmid = conn.cluster.nextid.get()

        flavor = self.get_optimal_flavor(
            ctxt, connection_info, instance_name, export_info)

        # Configure network interfaces
        network_map = target_environment.get("network_map", {})
        net_params = {}
        nics = export_info.get("devices", {}).get("nics", [])
        for index, nic in enumerate(nics):
            src_net = nic.get("network")
            tgt_bridge = network_map.get(src_net, "vmbr0")
            mac_str = ""
            preserve_mac = target_environment.get(
                "preserve_mac_addresses")
            if preserve_mac and nic.get("mac"):
                mac_str = f",macaddr={nic['mac']}"
            net_params[f"net{index}"] = (
                f"virtio,bridge={tgt_bridge}{mac_str}")

        # Create target VM config
        vm_params = {
            "vmid": target_vmid,
            "name": instance_name,
            "memory": flavor["memory_mb"],
            "cores": flavor["vcpus"],
            "scsihw": "virtio-scsi-pci",
            "agent": "enabled=1",
            **net_params
        }
        conn.nodes(node).qemu.post(**vm_params)

        # Attach/Clone disks
        for index, vol in enumerate(volumes_info):
            disk_key = f"scsi{index}"
            vol_id = vol["volume_id"]

            # Attach replica disk to target VM
            conn.nodes(node).qemu(target_vmid).config.post(
                **{disk_key: vol_id})

            if clone_disks:
                # Copy the disk and update VM configuration
                move_params = {
                    "disk": disk_key,
                    "storage": storage,
                    "delete": 0,
                }
                upid = conn.nodes(node).qemu(target_vmid).move_volume.post(
                    **move_params)
                self._wait_for_task(conn, node, upid)

        return {"vm_id": target_vmid}

    def finalize_replica_instance_deployment(
            self, ctxt, connection_info,
            target_environment, instance_name,
            volumes_info, instance_deployment_info):
        conn = self._get_proxmox_connection(connection_info)
        node = target_environment["node"]
        target_vmid = instance_deployment_info["vm_id"]

        # Ensure first SCSI disk is first boot device
        conn.nodes(node).qemu(target_vmid).config.post(boot="order=scsi0")

    def cleanup_failed_replica_instance_deployment(
            self, ctxt, connection_info,
            target_environment, instance_name):
        conn = self._get_proxmox_connection(connection_info)
        target_node, target_vmid = self._find_vm_by_name(conn, instance_name)
        if target_vmid:
            self._delete_vm(conn, target_node, target_vmid)

    def create_replica_disk_snapshots(self, ctxt, connection_info,
                                      target_environment, volumes_info):
        # Snapshotting standalone disks is not directly supported/needed
        return volumes_info

    def delete_replica_target_disk_snapshots(self, ctxt, connection_info,
                                             target_environment, volumes_info):
        return volumes_info

    def restore_replica_disk_snapshots(self, ctxt, connection_info,
                                       target_environment, volumes_info):
        return volumes_info

    # ------------------------------------------------------------------
    # BaseReplicaImportValidationProvider
    # ------------------------------------------------------------------

    def validate_replica_import_input(self, ctxt, connection_info,
                                      target_environment, export_info,
                                      check_os_morphing_resources=False,
                                      check_final_vm_params=False):
        conn = self._get_proxmox_connection(connection_info)
        node = target_environment["node"]
        storage = target_environment["storage"]

        # Check node exists
        nodes = [n["node"] for n in conn.nodes.get()]
        if node not in nodes:
            raise exception.InvalidInput(f"Proxmox node '{node}' not found.")

        # Check storage exists and has space
        try:
            status = conn.nodes(node).storage(storage).status.get()
            avail = status.get("avail", 0)
            required = sum(
                d["size_bytes"]
                for d in export_info.get("devices", {}).get("disks", []))
            if required > avail:
                raise exception.InvalidInput(
                    f"Not enough space on storage '{storage}': "
                    f"needed {required} bytes, available {avail} bytes.")
        except Exception as e:
            if isinstance(e, exception.InvalidInput):
                raise
            raise exception.InvalidInput(
                f"Storage '{storage}' not found or inactive on node "
                f"'{node}': {e}")

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
        return volumes_info

    # ------------------------------------------------------------------
    # BaseInstanceProvider & OS Morphing
    # ------------------------------------------------------------------

    def deploy_os_morphing_resources(self, ctxt, connection_info,
                                     target_environment,
                                     instance_deployment_info):
        conn = self._get_proxmox_connection(connection_info)
        node = target_environment["node"]
        target_vmid = instance_deployment_info["vm_id"]

        # Stop VM
        try:
            status = conn.nodes(node).qemu(target_vmid).status.current.get()
            if status.get("status") == "running":
                conn.nodes(node).qemu(target_vmid).status.stop.post()
                self._wait_for_vm_down(conn, node, target_vmid)
        except Exception as e:
            LOG.warning("Failed to stop target VM %s: %s", target_vmid, e)

        # Create OS Morphing Minion VM
        minion_vmid = self._create_minion_vm(
            conn, node, target_environment, name_suffix="osmorphing")

        # Detach disks from target VM and attach to Minion VM
        config = conn.nodes(node).qemu(target_vmid).config.get()
        target_disk_ids = []
        boot_disk_id = None
        to_detach = []

        for key, value in config.items():
            if key.startswith("scsi") and "disk" in key:
                vol_id = value.split(",")[0]
                target_disk_ids.append(vol_id)
                to_detach.append(key)
                if key == "scsi0":
                    boot_disk_id = vol_id

        # Detach from target
        if to_detach:
            conn.nodes(node).qemu(target_vmid).config.post(
                delete=",".join(to_detach))

        # Attach to Minion
        for index, vol_id in enumerate(target_disk_ids):
            disk_key = f"scsi{index + 1}"
            conn.nodes(node).qemu(minion_vmid).config.post(
                **{disk_key: vol_id})

        # Start Minion VM
        conn.nodes(node).qemu(minion_vmid).status.start.post()
        self._wait_for_vm_up(conn, node, minion_vmid)

        # Get Minion IP
        minion_ip = self._get_vm_ip(conn, node, minion_vmid)

        # Collect NIC info for OS Morphing parameters
        nics_info = []
        for key, value in config.items():
            if key.startswith("net") and isinstance(value, str):
                mac = None
                for part in value.split(","):
                    if part.startswith("macaddr="):
                        mac = part.split("=")[1]
                nics_info.append({
                    "name": key,
                    "mac_address": mac,
                })

        return {
            "os_morphing_resources": {
                "minion_vm_id": minion_vmid,
                "target_vm_id": target_vmid,
                "boot_disk_id": boot_disk_id,
                "target_disk_ids": target_disk_ids,
            },
            "osmorphing_connection_info": {
                "ip": minion_ip,
                "port": 22,
                "username": "root",
                "password": connection_info.get("password"),
                "pkey": self._get_minion_ssh_key(),
            },
            "osmorphing_info": {
                "os_type": self._detect_os_type(instance_deployment_info),
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
        conn = self._get_proxmox_connection(connection_info)
        node = target_environment["node"]
        minion_vmid = os_morphing_resources["minion_vm_id"]
        target_vmid = os_morphing_resources["target_vm_id"]
        target_disk_ids = os_morphing_resources.get("target_disk_ids", [])

        # Stop minion
        try:
            status = conn.nodes(node).qemu(minion_vmid).status.current.get()
            if status.get("status") == "running":
                conn.nodes(node).qemu(minion_vmid).status.stop.post()
                self._wait_for_vm_down(conn, node, minion_vmid)
        except Exception as e:
            LOG.warning(
                "Failed to stop morphing minion VM %s: %s", minion_vmid, e)

        # Detach disks from minion
        try:
            config = conn.nodes(node).qemu(minion_vmid).config.get()
            to_delete = []
            for key in config.keys():
                if key.startswith("scsi") and key != "scsi0":
                    to_delete.append(key)
            if to_delete:
                conn.nodes(node).qemu(minion_vmid).config.post(
                    delete=",".join(to_delete))
        except Exception as e:
            LOG.warning(
                "Failed to detach disks from minion VM %s: %s", minion_vmid, e)

        # Re-attach disks to target VM
        for index, vol_id in enumerate(target_disk_ids):
            disk_key = f"scsi{index}"
            conn.nodes(node).qemu(target_vmid).config.post(
                **{disk_key: vol_id})

        # Set boot device
        conn.nodes(node).qemu(target_vmid).config.post(boot="order=scsi0")

        # Delete minion VM
        try:
            conn.nodes(node).qemu(minion_vmid).delete()
        except Exception as e:
            LOG.warning(
                "Failed to delete morphing minion VM %s: %s", minion_vmid, e)

    def get_os_morphing_tools(self, os_type, osmorphing_info):
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
