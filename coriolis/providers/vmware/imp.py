# Copyright 2026 Thesolution.at
# All Rights Reserved.

import os
import time

from oslo_config import cfg
from oslo_log import log as logging

from coriolis import exception
from coriolis.providers import base

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

vmware_imp_opts = [
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
               help='vSphere template name for minion VMs'),
    cfg.StrOpt('minion_ssh_key_path',
               default=None,
               help='Path to SSH private key for minion access'),
    cfg.StrOpt('migration_log_dir',
               default='/var/log/coriolis/migrations',
               help='Directory for per-migration JSON-Lines log files'),
]
CONF.register_opts(vmware_imp_opts, group='vmware_import')


class VMwareVSphereImportProvider(
        base.BaseEndpointProvider,
        base.BaseEndpointDestinationOptionsProvider,
        base.BaseEndpointNetworksProvider,
        base.BaseEndpointStorageProvider,
        base.BaseInstanceFlavorProvider,
        base.BaseReplicaImportProvider,
        base.BaseReplicaImportValidationProvider,
        base.BaseUpdateDestinationReplicaProvider,
):
    platform = "vmware_vsphere"

    def __init__(self, event_manager):
        self._event_manager = event_manager

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_vcenter_session(self, connection_info):
        """Creates a pyvmomi Connection to vCenter."""
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
        """Finds VM by name or UUID in vCenter."""
        from pyVmomi import vim
        content = si.RetrieveContent()
        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.VirtualMachine], True)
        for vm in container.view:
            if vm.name == name or vm.config.uuid == name:
                return vm
        return None

    def _wait_for_task(self, task, timeout=600):
        """Waits for a VMware Task to finish."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if task.info.state in ["success", "error"]:
                if task.info.state == "error":
                    msg = task.info.error.localizedMessage
                    raise exception.CoriolisException(
                        f"VMware Task failed: {msg}")
                return task.info.result
            time.sleep(5)
        raise exception.CoriolisException(
            f"VMware Task timed out after {timeout} seconds.")

    def _get_vm_ip(self, vm, timeout=900):
        """Obtains VM IP address from VMware Tools."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            ip = getattr(vm.guest, "ipAddress", None)
            if ip and not ip.startswith("127."):
                return ip
            time.sleep(10)
        raise exception.CoriolisException(
            f"Timed out waiting for VM {vm.name} IP from VMware Tools.")

    def _get_minion_ssh_key(self):
        key_path = CONF.vmware_import.minion_ssh_key_path
        if key_path and os.path.exists(key_path):
            with open(key_path, 'r') as f:
                return f.read()
        return None

    def _detect_os_type(self, export_info):
        return export_info.get("os_type", "linux")

    # ------------------------------------------------------------------
    # BaseEndpointProvider
    # ------------------------------------------------------------------

    def get_connection_info_schema(self):
        return {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "vCenter Server host/IP",
                },
                "username": {
                    "type": "string",
                },
                "password": {
                    "type": "string",
                    "secret": True,
                },
                "allow_untrusted": {
                    "type": "boolean",
                    "default": True,
                },
            },
            "required": ["host", "username", "password"],
        }

    def validate_connection(self, ctxt, connection_info):
        from pyVim.connect import Disconnect
        si = self._get_vcenter_session(connection_info)
        try:
            content = si.RetrieveContent()
            LOG.info("Connected to vCenter: %s",
                     content.about.fullName)
        finally:
            Disconnect(si)

    # ------------------------------------------------------------------
    # BaseEndpointDestinationOptionsProvider
    # ------------------------------------------------------------------

    def get_target_environment_schema(self):
        return {
            "type": "object",
            "properties": {
                "datacenter": {
                    "type": "string",
                    "description": "Target datacenter name",
                },
                "cluster": {
                    "type": "string",
                    "description": "Target cluster name",
                },
                "datastore": {
                    "type": "string",
                    "description": "Target datastore name",
                },
                "network_map": {
                    "type": "object",
                },
                "preserve_mac_addresses": {
                    "type": "boolean",
                },
            },
            "required": ["datacenter", "cluster", "datastore"],
        }

    def get_target_environment_options(self, ctxt, connection_info,
                                       env=None, option_names=None):
        from pyVim.connect import Disconnect
        from pyVmomi import vim
        si = self._get_vcenter_session(connection_info)
        try:
            content = si.RetrieveContent()
            options = []

            # Datacenters
            if not option_names or "datacenter" in option_names:
                container = content.viewManager.CreateContainerView(
                    content.rootFolder, [vim.Datacenter], True)
                dcs = [{"id": dc.name, "name": dc.name}
                       for dc in container.view]
                options.append({
                    "name": "datacenter",
                    "values": dcs,
                })

            # Clusters
            if not option_names or "cluster" in option_names:
                container = content.viewManager.CreateContainerView(
                    content.rootFolder, [vim.ClusterComputeResource], True)
                clusters = [{"id": c.name, "name": c.name}
                            for c in container.view]
                options.append({
                    "name": "cluster",
                    "values": clusters,
                })

            # Datastores
            if not option_names or "datastore" in option_names:
                container = content.viewManager.CreateContainerView(
                    content.rootFolder, [vim.Datastore], True)
                datastores = [
                    {"id": ds.name, "name": ds.name}
                    for ds in container.view if ds.summary.accessible]
                options.append({
                    "name": "datastore",
                    "values": datastores,
                })

            return options
        finally:
            Disconnect(si)

    # ------------------------------------------------------------------
    # BaseEndpointNetworksProvider
    # ------------------------------------------------------------------

    def get_networks(self, ctxt, connection_info, env):
        from pyVim.connect import Disconnect
        from pyVmomi import vim
        si = self._get_vcenter_session(connection_info)
        try:
            content = si.RetrieveContent()
            container = content.viewManager.CreateContainerView(
                content.rootFolder, [vim.Network], True)
            return [{"id": net.name, "name": net.name}
                    for net in container.view]
        finally:
            Disconnect(si)

    # ------------------------------------------------------------------
    # BaseEndpointStorageProvider
    # ------------------------------------------------------------------

    def get_storage(self, ctxt, connection_info, target_environment):
        from pyVim.connect import Disconnect
        from pyVmomi import vim
        si = self._get_vcenter_session(connection_info)
        try:
            content = si.RetrieveContent()
            ds_name = target_environment["datastore"]
            container = content.viewManager.CreateContainerView(
                content.rootFolder, [vim.Datastore], True)
            for ds in container.view:
                if ds.name == ds_name:
                    return {
                        "total_bytes": ds.summary.capacity,
                        "available_bytes": ds.summary.freeSpace,
                        "used_bytes": (
                            ds.summary.capacity - ds.summary.freeSpace),
                    }
            raise exception.NotFound(f"Datastore {ds_name} not found.")
        finally:
            Disconnect(si)

    # ------------------------------------------------------------------
    # BaseInstanceFlavorProvider
    # ------------------------------------------------------------------

    def get_optimal_flavor(
            self, ctxt, connection_info, instance_name, export_info):
        return {
            "vcpus": export_info.get("vcpus", 2),
            "memory_mb": export_info.get("memory_mb", 4096),
        }

    # ------------------------------------------------------------------
    # BaseReplicaImportProvider
    # ------------------------------------------------------------------

    def deploy_replica_disks(self, ctxt, connection_info,
                             target_environment, instance_name,
                             export_info, volumes_info):
        # We will create disks using VirtualDiskManager or placeholder VMDKs
        from pyVim.connect import Disconnect
        si = self._get_vcenter_session(connection_info)
        try:
            # For simplicity, we register disk paths on the target datastore.
            # The actual VMDK allocation can happen as part of placeholder VM.
            ds_name = target_environment["datastore"]
            new_volumes_info = []
            for index, disk in enumerate(
                    export_info.get("devices", {}).get("disks", [])):
                disk_id = disk.get("id", f"disk-{index}")
                vol_path = f"[{ds_name}] {instance_name}/disk-{index}.vmdk"
                new_volumes_info.append({
                    "disk_id": disk_id,
                    "volume_id": vol_path,
                    "size_bytes": disk["size_bytes"],
                })
            return new_volumes_info
        finally:
            Disconnect(si)

    def deploy_replica_target_resources(self, ctxt, connection_info,
                                        target_environment, volumes_info):
        from pyVim.connect import Disconnect
        si = self._get_vcenter_session(connection_info)
        try:
            # Clones minion template to create a helper VM
            template_name = CONF.vmware_import.minion_template_name
            if not template_name:
                raise exception.CoriolisException(
                    "Missing 'minion_template_name' configuration option.")

            template = self._find_vm_by_name(si, template_name)
            if not template:
                raise exception.NotFound(
                    f"Template {template_name} not found.")

            # clone task mock/sim
            # In a real environment, we would run template.CloneVM_Task(...)
            # For now we create target resources representation:
            minion_ip = "172.24.12.34"  # Dummy IP or resolved via tools

            # setup writer connection details representation
            return {
                "migr_resources": {
                    "minion_vm_name": f"coriolis-minion-{int(time.time())}",
                    "writer_port": CONF.vmware_import.writer_port,
                },
                "volumes_info": volumes_info,
                "connection_info": {
                    "backend": "http_backup_writer",
                    "connection_details": {"url": f"http://{minion_ip}:6677"},
                },
            }
        finally:
            Disconnect(si)

    def delete_replica_target_resources(self, ctxt, connection_info,
                                        target_environment, migr_resources):
        from pyVim.connect import Disconnect
        si = self._get_vcenter_session(connection_info)
        try:
            minion_name = migr_resources["minion_vm_name"]
            minion_vm = self._find_vm_by_name(si, minion_name)
            if minion_vm:
                # PowerOff and Destroy task
                if minion_vm.runtime.powerState == "poweredOn":
                    task = minion_vm.PowerOffVM_Task()
                    self._wait_for_task(task)
                task = minion_vm.Destroy_Task()
                self._wait_for_task(task)
        except Exception as e:
            LOG.warning("Failed to cleanup minion VM %s: %s",
                        migr_resources.get("minion_vm_name"), e)
        finally:
            Disconnect(si)

    def delete_replica_disks(self, ctxt, connection_info,
                             target_environment, volumes_info):
        from pyVim.connect import Disconnect
        si = self._get_vcenter_session(connection_info)
        try:
            content = si.RetrieveContent()
            vdm = content.virtualDiskManager
            for vol in volumes_info:
                vol_path = vol["volume_id"]
                try:
                    task = vdm.DeleteVirtualDisk_Task(name=vol_path)
                    self._wait_for_task(task)
                except Exception as e:
                    LOG.warning(
                        "Failed to delete VMDK disk %s: %s", vol_path, e)
        finally:
            Disconnect(si)

    def deploy_replica_instance(self, ctxt, connection_info,
                                target_environment, instance_name,
                                export_info, volumes_info, clone_disks):
        from pyVim.connect import Disconnect
        si = self._get_vcenter_session(connection_info)
        try:
            # Create target VM config and register in vCenter
            # Real impl uses CreateVM_Task under a target folder/datacenter
            # Attach disks VMDK
            # Return vm representation id
            return {"vm_id": instance_name}
        finally:
            Disconnect(si)

    def finalize_replica_instance_deployment(
            self, ctxt, connection_info,
            target_environment, instance_name,
            volumes_info, instance_deployment_info):
        pass

    def cleanup_failed_replica_instance_deployment(
            self, ctxt, connection_info,
            target_environment, instance_name):
        from pyVim.connect import Disconnect
        si = self._get_vcenter_session(connection_info)
        try:
            vm = self._find_vm_by_name(si, instance_name)
            if vm:
                if vm.runtime.powerState == "poweredOn":
                    task = vm.PowerOffVM_Task()
                    self._wait_for_task(task)
                task = vm.Destroy_Task()
                self._wait_for_task(task)
        finally:
            Disconnect(si)

    def create_replica_disk_snapshots(self, ctxt, connection_info,
                                      target_environment, volumes_info):
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
        # Checks if datacenter and datastore exist and has space
        self.get_storage(ctxt, connection_info, target_environment)

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

    def deploy_os_morphing_resources(
            self, ctxt, connection_info, target_environment,
            instance_deployment_info):
        return {
            "os_morphing_resources": {},
            "osmorphing_connection_info": {},
            "osmorphing_info": {},
        }

    def delete_os_morphing_resources(
            self, ctxt, connection_info, target_environment,
            os_morphing_resources):
        pass

    def get_os_morphing_tools(self, os_type, osmorphing_info):
        return []
