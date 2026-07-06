# Copyright 2026 Thesolution.at
# All Rights Reserved.

import time

from oslo_config import cfg
from oslo_log import log as logging

from coriolis import exception
from coriolis.providers import base

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class OLVMoVirtExportProvider(
        base.BaseEndpointInstancesProvider,
        base.BaseEndpointSourceOptionsProvider,
        base.BaseEndpointNetworksProvider,
        base.BaseEndpointStorageProvider,
        base.BaseReplicaExportValidationProvider,
        base.BaseUpdateSourceReplicaProvider,
        base.BaseReplicaExportProvider,
):
    platform = "olvm"

    def __init__(self, event_manager):
        self._event_manager = event_manager

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_ovirt_connection(self, connection_info):
        """Creates an oVirt SDK v4 Connection."""
        import ovirtsdk4 as sdk

        url = connection_info.get("url")
        if url:
            url_stripped = url.rstrip("/")
            if url_stripped.endswith("/ovirt-engine"):
                url = url_stripped + "/api"
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

    def _find_vm_by_name(self, conn, name):
        """Finds VM by name or ID in oVirt."""
        vms_service = conn.system_service().vms_service()
        try:
            vm = vms_service.vm_service(name).get()
            if vm:
                return vm
        except Exception:
            pass

        res = vms_service.list(search=f"name={name}")
        if res:
            return res[0]
        return None

    def _vm_to_instance_dict(self, vm):
        # Build standard instance dictionary
        guest_os = getattr(vm, "os", None)
        os_type = "linux"
        if guest_os and getattr(guest_os, "type", None):
            if "windows" in guest_os.type.lower():
                os_type = "windows"

        return {
            "id": vm.id,
            "name": vm.name,
            "status": str(vm.status),
            "os_type": os_type,
            "vcpus": vm.cpu.topology.cores if vm.cpu else 1,
            "memory_mb": int(vm.memory / (1024 * 1024)) if vm.memory else 1024,
        }

    # ------------------------------------------------------------------
    # BaseEndpointProvider
    # ------------------------------------------------------------------

    def get_connection_info_schema(self):
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "oVirt Engine URL",
                },
                "username": {
                    "type": "string",
                },
                "password": {
                    "type": "string",
                    "secret": True,
                },
                "ca_bundle": {
                    "type": "string",
                    "description": "PEM CA certificate path or content",
                },
                "insecure": {
                    "type": "boolean",
                    "default": True,
                },
            },
            "required": ["url", "username", "password"],
        }

    def validate_connection(self, ctxt, connection_info):
        conn = self._get_ovirt_connection(connection_info)
        try:
            system = conn.system_service()
            product = system.get().product_info
            LOG.info("Connected to oVirt/OLVM: %s version %s",
                     product.name, product.version.full_version)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseEndpointInstancesProvider
    # ------------------------------------------------------------------

    def get_instances(self, ctxt, connection_info, source_environment,
                      limit=None, last_seen_id=None,
                      instance_name_pattern=None, refresh=False):
        conn = self._get_ovirt_connection(connection_info)
        try:
            vms_service = conn.system_service().vms_service()
            search = None
            if instance_name_pattern:
                search = f"name=*{instance_name_pattern}*"

            vms = vms_service.list(search=search)
            return [self._vm_to_instance_dict(vm) for vm in vms]
        finally:
            conn.close()

    def get_instance(self, ctxt, connection_info, source_environment,
                     instance_name):
        conn = self._get_ovirt_connection(connection_info)
        try:
            vm = self._find_vm_by_name(conn, instance_name)
            if not vm:
                raise exception.NotFound(f"VM {instance_name} not found.")
            return self._vm_to_instance_dict(vm)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseEndpointNetworksProvider
    # ------------------------------------------------------------------

    def get_networks(self, ctxt, connection_info, env):
        conn = self._get_ovirt_connection(connection_info)
        try:
            nets = conn.system_service().networks_service().list()
            return [{"id": n.id, "name": n.name} for n in nets]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseEndpointStorageProvider
    # ------------------------------------------------------------------

    def get_storage(self, ctxt, connection_info, target_environment):
        conn = self._get_ovirt_connection(connection_info)
        try:
            sds = conn.system_service().storage_domains_service().list()
            backends = []
            for sd in sds:
                backends.append({
                    "id": sd.id,
                    "name": sd.name,
                    "available_bytes": sd.available or 0,
                    "total_bytes": (sd.available or 0) + (sd.used or 0),
                })
            return {"storage_backends": backends}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseEndpointSourceOptionsProvider
    # ------------------------------------------------------------------

    def get_source_environment_schema(self):
        return {
            "type": "object",
            "properties": {},
        }

    def get_source_environment_options(self, ctxt, connection_info,
                                       env=None, option_names=None):
        return []

    # ------------------------------------------------------------------
    # BaseReplicaExportValidationProvider
    # ------------------------------------------------------------------

    def validate_replica_export_input(self, ctxt, connection_info,
                                      source_environment, instance_name):
        conn = self._get_ovirt_connection(connection_info)
        try:
            vm = self._find_vm_by_name(conn, instance_name)
            if not vm:
                raise exception.InvalidInput(
                    f"Source VM '{instance_name}' not found.")
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseUpdateSourceReplicaProvider
    # ------------------------------------------------------------------

    def check_update_source_environment_params(
            self, ctxt, connection_info, export_info,
            volumes_info, old_params, new_params):
        return volumes_info

    # ------------------------------------------------------------------
    # BaseReplicaExportProvider
    # ------------------------------------------------------------------

    def get_replica_instance_info(self, ctxt, connection_info,
                                  source_environment, instance_name):
        conn = self._get_ovirt_connection(connection_info)
        try:
            vm = self._find_vm_by_name(conn, instance_name)
            if not vm:
                raise exception.NotFound(f"VM {instance_name} not found.")

            # Get disks info
            vm_service = conn.system_service().vms_service().vm_service(vm.id)
            attachments = vm_service.disk_attachments_service().list()
            disks = []
            for index, att in enumerate(attachments):
                disk = conn.follow_link(att.disk)
                disks.append({
                    "id": disk.id,
                    "size_bytes": disk.provisioned_size or disk.size,
                    "type": "disk",
                    "bootable": att.bootable,
                })

            # Get NICs info
            nics = []
            for nic in vm_service.nics_service().list():
                nics.append({
                    "id": nic.id,
                    "name": nic.name,
                    "mac": nic.mac.address if nic.mac else None,
                    "network": (
                        nic.vnic_profile.name if nic.vnic_profile else "None"),
                })

            instance_info = self._vm_to_instance_dict(vm)
            instance_info["devices"] = {
                "disks": disks,
                "nics": nics,
            }
            return instance_info
        finally:
            conn.close()

    def deploy_replica_source_resources(self, ctxt, connection_info,
                                        source_environment, instance_name,
                                        volumes_info):
        conn = self._get_ovirt_connection(connection_info)
        try:
            vm = self._find_vm_by_name(conn, instance_name)
            if not vm:
                raise exception.NotFound(f"VM {instance_name} not found.")

            # Create snapshot
            vm_service = conn.system_service().vms_service().vm_service(vm.id)
            snapshots_service = vm_service.snapshots_service()
            snap = snapshots_service.add(
                snapshot=conn.types.Snapshot(
                    description=f"coriolis-replica-{int(time.time())}"
                )
            )

            # Wait for snapshot to become OK/active
            snap_service = snapshots_service.snapshot_service(snap.id)
            start_time = time.time()
            while time.time() - start_time < 300:
                snap_curr = snap_service.get()
                if str(snap_curr.snapshot_status) == "ok":
                    break
                time.sleep(5)
            else:
                raise exception.CoriolisException(
                    f"Snapshot for VM {instance_name} failed to become ready.")

            return {
                "source_vm_id": vm.id,
                "snapshot_id": snap.id,
            }
        finally:
            conn.close()

    def delete_replica_source_resources(self, ctxt, connection_info,
                                        source_environment, source_resources):
        conn = self._get_ovirt_connection(connection_info)
        try:
            vm_id = source_resources["source_vm_id"]
            snap_id = source_resources["snapshot_id"]

            vm_service = conn.system_service().vms_service().vm_service(vm_id)
            snapshots_service = vm_service.snapshots_service()
            snap_service = snapshots_service.snapshot_service(snap_id)

            try:
                snap_service.remove()
            except Exception as e:
                LOG.warning("Failed to delete snapshot %s: %s", snap_id, e)
        finally:
            conn.close()

    def replicate_disks(self, ctxt, connection_info, source_environment,
                        source_resources, volumes_info, backup_writer):
        # oVirt Image Transfer streaming
        conn = self._get_ovirt_connection(connection_info)
        try:
            import requests

            transfers_service = conn.system_service().image_transfers_service()
            for vol in volumes_info:
                disk_id = vol["disk_id"]
                # Initiate download transfer session
                transfer = transfers_service.add(
                    transfer=conn.types.ImageTransfer(
                        disk=conn.types.Disk(id=disk_id),
                        direction=conn.types.ImageTransferDirection.DOWNLOAD,
                        inactivity_timeout=600,
                    )
                )

                # Wait for state transferring
                t_service = transfers_service.image_transfer_service(
                    transfer.id)
                start_time = time.time()
                while time.time() - start_time < 300:
                    transfer_curr = t_service.get()
                    if str(transfer_curr.phase) == "transferring":
                        break
                    time.sleep(5)
                else:
                    raise exception.CoriolisException(
                        f"Image transfer for disk {disk_id} failed to start.")

                # Stream from transfer_url to backup_writer
                url = transfer_curr.transfer_url
                verify = not connection_info.get("insecure", True)
                ca_bundle = connection_info.get("ca_bundle")
                if verify and ca_bundle:
                    verify = ca_bundle

                response = requests.get(url, stream=True, verify=verify)
                response.raise_for_status()

                # Stream chunks to backup writer endpoint
                writer_connection = backup_writer["connection_details"]
                stream_url = writer_connection["url"]
                requests.post(
                    stream_url,
                    data=response.iter_content(chunk_size=1024 * 1024))

                # Finalize transfer
                t_service.finalize()
        finally:
            conn.close()

    def delete_replica_source_snapshots(self, ctxt, connection_info,
                                        source_environment, source_resources):
        # Done in delete_replica_source_resources
        pass

    def shutdown_instance(self, ctxt, connection_info,
                          source_environment, source_resources,
                          instance_name):
        conn = self._get_ovirt_connection(connection_info)
        try:
            vm_id = source_resources["source_vm_id"]
            vm_service = conn.system_service().vms_service().vm_service(vm_id)
            vm = vm_service.get()
            if str(vm.status) != "down":
                vm_service.stop()
                # Wait for down status
                start_time = time.time()
                while time.time() - start_time < 300:
                    vm_curr = vm_service.get()
                    if str(vm_curr.status) == "down":
                        break
                    time.sleep(5)
        finally:
            conn.close()

    def get_os_morphing_tools(self, os_type, osmorphing_info):
        return []
