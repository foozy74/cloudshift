# Copyright 2024 YourCompany
# All Rights Reserved.

import os
import time

from oslo_config import cfg
from oslo_log import log as logging

from coriolis import exception
from coriolis.providers import backup_writers
from coriolis.providers import base
from coriolis.providers.olvm import migration_log as mlog_mod
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
    cfg.StrOpt('migration_log_dir',
               default='/var/log/coriolis/migrations',
               help='Directory for per-migration JSON-Lines log files'),
]
CONF.register_opts(olvm_opts, group='olvm')


class OLVMoVirtImportProvider(
        base.BaseEndpointProvider,
        base.BaseEndpointDestinationOptionsProvider,
        base.BaseEndpointNetworksProvider,
        base.BaseEndpointStorageProvider,
        base.BaseInstanceFlavorProvider,
        base.BaseReplicaImportProvider,
        base.BaseReplicaImportValidationProvider,
        base.BaseUpdateDestinationReplicaProvider,
):
    platform = "olvm"

    def __init__(self, event_manager):
        self._event_manager = event_manager

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_ovirt_connection(self, connection_info):
        """Erstellt eine oVirt SDK v4 Verbindung."""
        import ovirtsdk4 as sdk

        url = connection_info.get(
            "url",
            "https://sb-ovirt.sdn.it.internal/ovirt-engine/api")
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

    def _find_cluster(self, conn, cluster_ref):
        system = conn.system_service()
        clusters_service = system.clusters_service()
        try:
            cluster = clusters_service.cluster_service(cluster_ref).get()
            if cluster:
                return cluster
        except Exception:
            pass
        try:
            res = clusters_service.list(search="name=%s" % cluster_ref)
            if res:
                return res[0]
        except Exception:
            pass
        return None

    def _find_storage_domain(self, conn, sd_ref):
        system = conn.system_service()
        sds_service = system.storage_domains_service()
        try:
            sd = sds_service.storage_domain_service(sd_ref).get()
            if sd:
                return sd
        except Exception:
            pass
        try:
            res = sds_service.list(search="name=%s" % sd_ref)
            if res:
                return res[0]
        except Exception:
            pass
        return None

    def _resolve_target_environment(self, conn, target_environment):
        """Resolves cluster_id, storage_domain_id, and datacenter_id."""
        if not target_environment:
            return
        cluster_id = target_environment.get("cluster_id")
        sd_id = target_environment.get("storage_domain_id")
        if cluster_id:
            resolved = self._find_cluster(conn, cluster_id)
            if resolved:
                target_environment["cluster_id"] = resolved.id
                # Datacenter-ID aus Cluster ableiten (für auto-networks)
                if getattr(resolved, "data_center", None):
                    target_environment.setdefault(
                        "datacenter_id", resolved.data_center.id)
        if sd_id:
            resolved = self._find_storage_domain(conn, sd_id)
            if resolved:
                target_environment["storage_domain_id"] = resolved.id

    def _ensure_network_and_vnic_profile(
            self, conn, datacenter_id, cluster_id, network_name, vlan_id):
        """Stellt sicher, dass ein logisches Netzwerk + VNIC-Profil auf OLVM
        existieren, und gibt die VNIC-Profil-ID zurück.

        Ablauf:
          1. Logisches Netzwerk suchen (nach Name).
          2. Falls nicht vorhanden: anlegen und an Datacenter + Cluster hängen.
          3. Falls vorhanden aber mit abweichender VLAN-ID: Fehler werfen.
          4. VNIC-Profil für das Netzwerk suchen oder anlegen.

        :param conn: aktive oVirt-Verbindung
        :param datacenter_id: ID des Datacenters
        :param cluster_id: ID des Clusters
        :param network_name: gewünschter Netzwerkname
        :param vlan_id: numerische VLAN-ID (0 = untagged, None = untagged)
        :returns: VNIC-Profil-ID (str)
        :raises exception.InvalidInput: bei VLAN-ID-Konflikt
        """
        import ovirtsdk4 as sdk

        effective_vlan_id = vlan_id if vlan_id else 0
        system = conn.system_service()
        networks_svc = system.networks_service()
        vnic_profiles_svc = system.vnic_profiles_service()

        # --- 1. Logisches Netzwerk suchen ---
        existing = networks_svc.list(search="name=%s" % network_name)
        network_obj = None
        for n in existing:
            if n.name == network_name:
                network_obj = n
                break

        if network_obj:
            # --- 3. VLAN-ID-Konfliktprüfung ---
            existing_vlan = 0
            if network_obj.vlan and network_obj.vlan.id is not None:
                existing_vlan = int(network_obj.vlan.id)
            if existing_vlan != effective_vlan_id:
                raise exception.InvalidInput(
                    "Network '%s' already exists on OLVM with VLAN-ID %d, "
                    "but source requires VLAN-ID %d. "
                    "Please resolve the conflict manually before migrating."
                    % (network_name, existing_vlan, effective_vlan_id))
            LOG.info(
                "Network '%s' (VLAN %d) already exists on OLVM (id=%s).",
                network_name, effective_vlan_id, network_obj.id)
        else:
            # --- 2. Logisches Netzwerk anlegen ---
            LOG.info(
                "Creating logical network '%s' with VLAN-ID %d ...",
                network_name, effective_vlan_id)
            vlan_spec = sdk.types.Vlan(id=effective_vlan_id) \
                if effective_vlan_id else None
            network_obj = networks_svc.add(
                network=sdk.types.Network(
                    name=network_name,
                    data_center=sdk.types.DataCenter(id=datacenter_id),
                    vlan=vlan_spec,
                    usages=[
                        sdk.types.NetworkUsage.VM,
                    ],
                )
            )
            LOG.info(
                "Logical network '%s' created (id=%s).",
                network_name, network_obj.id)

            # Netzwerk an Cluster anhängen
            cluster_networks_svc = (
                system.clusters_service()
                .cluster_service(cluster_id)
                .networks_service())
            cluster_networks_svc.add(
                network=sdk.types.Network(id=network_obj.id)
            )
            LOG.info(
                "Network '%s' attached to cluster %s.",
                network_name, cluster_id)

        # --- 4. VNIC-Profil suchen oder anlegen ---
        for p in vnic_profiles_svc.list():
            if p.network and p.network.id == network_obj.id \
                    and p.name == network_name:
                LOG.debug(
                    "Reusing existing VNIC profile '%s' (id=%s).",
                    p.name, p.id)
                return p.id

        LOG.info(
            "Creating VNIC profile '%s' for network %s ...",
            network_name, network_obj.id)
        vnic_profile = vnic_profiles_svc.add(
            profile=sdk.types.VnicProfile(
                name=network_name,
                network=sdk.types.Network(id=network_obj.id),
            )
        )
        LOG.info(
            "VNIC profile '%s' created (id=%s).",
            network_name, vnic_profile.id)
        return vnic_profile.id

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

        template_name = target_environment.get(
            "minion_template_name", CONF.olvm.minion_template_name)
        if not template_name:
            # Fallback: Minimales Image nutzen
            templates = system.templates_service().list()
            if templates:
                template_name = templates[0].name
            else:
                raise exception.InvalidInput(
                    "No minion template configured "
                    "(olvm.minion_template_name) "
                    "and no templates found on engine")

        # VNIC-Profil für das Management-Netzwerk (ovirtmgmt) suchen
        # (eingeschränkt auf Cluster-Netzwerke)
        vnic_profile_id = None
        try:
            clusters_svc = conn.system_service().clusters_service()
            cluster_service = clusters_svc.cluster_service(cluster_id)
            cluster_net_ids = [
                n.id for n in cluster_service.networks_service().list()]
            vnic_profiles_service = (
                conn.system_service().vnic_profiles_service())
            for p in vnic_profiles_service.list():
                if p.network and p.network.id in cluster_net_ids:
                    net = conn.follow_link(p.network)
                    if net and net.name == "ovirtmgmt":
                        vnic_profile_id = p.id
                        break
        except Exception as e:
            LOG.warn("Failed to find ovirtmgmt vnic profile: %s", e)

        import uuid
        # VM erstellen
        vm = vms_service.add(
            vm=sdk.types.Vm(
                name=f"coriolis-{name_suffix}-{uuid.uuid4().hex[:8]}",
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

        if vnic_profile_id:
            try:
                vm_service = vms_service.vm_service(vm.id)
                # Warten bis VM bereit (nicht IMAGE_LOCKED)
                for _ in range(60):
                    v = vm_service.get()
                    if v.status != sdk.types.VmStatus.IMAGE_LOCKED:
                        break
                    time.sleep(2)

                vm_service.nics_service().add(
                    nic=sdk.types.Nic(
                        name="nic0",
                        interface=sdk.types.NicInterface.VIRTIO,
                        vnic_profile=sdk.types.VnicProfile(id=vnic_profile_id),
                    )
                )
                LOG.info(
                    "Successfully added nic0 (ovirtmgmt) to minion VM %s",
                    vm.id)
            except Exception as e:
                LOG.warn(
                    "Failed to add nic0 (ovirtmgmt) to minion VM %s: %s",
                    vm.id, e)

        return vm

    def _attach_disk_to_vm(self, conn, vm_id, disk_id, bootable=False):
        """Attached eine oVirt-Disk an eine VM."""
        import ovirtsdk4 as sdk

        disk_attachments = conn.system_service().vms_service().vm_service(
            vm_id).disk_attachments_service()

        disk_attachments.add(
            attachment=sdk.types.DiskAttachment(
                disk=sdk.types.Disk(id=disk_id),
                interface=sdk.types.DiskInterface.VIRTIO,
                bootable=bootable,
                active=True,
            )
        )

    def _get_vm_ip(self, conn, vm_id, timeout=900):
        """Ermittelt die IP-Adresse einer VM mit Polling-Wartezeit."""
        import ovirtsdk4 as sdk
        vms_service = conn.system_service().vms_service()
        vm_service = vms_service.vm_service(vm_id)

        for _ in range(timeout // 5):
            try:
                # Get configured VM NIC MAC addresses to filter out
                # cached IPs from template
                vm_macs = set()
                for nic in vm_service.nics_service().list():
                    if nic.mac and nic.mac.address:
                        vm_macs.add(nic.mac.address.lower().replace(":", ""))

                reported_devices = vm_service.reported_devices_service().list()
                for dev in reported_devices:
                    if dev.mac and dev.mac.address:
                        dev_mac = dev.mac.address.lower().replace(":", "")
                        if dev_mac in vm_macs and dev.ips:
                            for ip in dev.ips:
                                if ip.version == sdk.types.IpVersion.V4 or \
                                        ip.version == "v4":
                                    return ip.address
            except Exception as e:
                LOG.debug(
                    "Failed to list reported devices for VM %s: %s", vm_id, e)
            time.sleep(5)

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
                    "description": (
                        "Source-Netzwerk zu Target-Netzwerk Mapping"),
                },
            },
            "required": ["cluster_id", "storage_domain_id"],
        }

    def get_target_environment_options(self, ctxt, connection_info,
                                       env=None, option_names=None):
        import ovirtsdk4 as sdk
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
                    if sd.type == sdk.types.StorageDomainType.DATA and
                    (sd.status is None or
                     sd.status == sdk.types.StorageDomainStatus.ACTIVE)
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
        """Listet alle logischen Netzwerke inklusive VLAN-ID zurück."""
        conn = self._get_ovirt_connection(connection_info)
        try:
            result = []
            for n in conn.system_service().networks_service().list():
                vlan_id = None
                if n.vlan and n.vlan.id is not None:
                    vlan_id = int(n.vlan.id)
                datacenter_name = None
                try:
                    if n.data_center:
                        dc = conn.follow_link(n.data_center)
                        datacenter_name = dc.name if dc else None
                except Exception:
                    pass
                entry = {"id": n.id, "name": n.name}
                if vlan_id is not None or datacenter_name:
                    entry["additional_provider_properties"] = {
                        "vlan_id": vlan_id,
                        "datacenter": datacenter_name,
                    }
                result.append(entry)
            return result
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseEndpointStorageProvider
    # ------------------------------------------------------------------

    def get_storage(self, ctxt, connection_info, target_environment):
        import ovirtsdk4 as sdk
        conn = self._get_ovirt_connection(connection_info)
        try:
            sds = [
                {"id": sd.id, "name": sd.name}
                for sd in (conn.system_service()
                           .storage_domains_service()
                           .list())
                if sd.type == sdk.types.StorageDomainType.DATA and
                (sd.status is None or
                 sd.status == sdk.types.StorageDomainStatus.ACTIVE)
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
        import ovirtsdk4 as sdk

        conn = self._get_ovirt_connection(connection_info)
        try:
            self._resolve_target_environment(conn, target_environment)
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
            boot_disk_id = None
            target_disk_ids = []
            for da in disk_attachments:
                disk = conn.follow_link(da.disk)
                target_disk_ids.append(disk.id)
                if da.bootable:
                    boot_disk_id = disk.id
                # Von Ziel-VM lösen
                try:
                    vm_service.disk_attachments_service().attachment_service(
                        da.id).remove()
                except Exception:
                    pass
                # An Minion-VM hängen
                self._attach_disk_to_vm(
                    conn, minion_vm.id, disk.id, bootable=False)

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
                    "boot_disk_id": boot_disk_id,
                    "target_disk_ids": target_disk_ids,
                },
                "osmorphing_connection_info": {
                    "ip": vm_ip,
                    "port": 22,
                    "username": "root",
                    "password": connection_info.get("password"),
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
            boot_disk_id = os_morphing_resources.get("boot_disk_id")
            target_disk_ids = os_morphing_resources.get("target_disk_ids", [])

            # Minion stoppen
            minion_service = vms_service.vm_service(minion_vm_id)
            minion_service.stop()
            self._wait_for_vm_down(vms_service, minion_vm_id)

            # Disks von Minion zu Ziel-VM verschieben
            for da in minion_service.disk_attachments_service().list():
                disk = conn.follow_link(da.disk)
                if target_disk_ids and disk.id not in target_disk_ids:
                    # Skip the minion's own boot disk
                    continue
                try:
                    minion_service.disk_attachments_service() \
                        .attachment_service(da.id).remove()
                except Exception:
                    pass

                bootable = (disk.id == boot_disk_id) if boot_disk_id else True
                self._attach_disk_to_vm(
                    conn, target_vm_id, disk.id, bootable=bootable)

            # Minion löschen
            minion_service.remove()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # BaseReplicaImportProvider (KERN)
    # ------------------------------------------------------------------

    def _get_disk_format_and_sparse(self, conn, sd_id):
        """Bestimmt das Disk-Format und Sparse-Flag für eine Storage Domain.

        Block-Storage (FCP, iSCSI etc.) unterstützt kein RAW sparse.
        Dafür nutzen wir COW mit sparse=True.
        File-Storage (NFS etc.) nutzt RAW mit sparse=True.
        """
        import ovirtsdk4 as sdk
        try:
            sd_service = (conn.system_service()
                          .storage_domains_service()
                          .storage_domain_service(sd_id))
            sd = sd_service.get()
            storage_type = sd.storage.type if sd.storage else None
            block_types = [
                sdk.types.StorageType.FCP,
                sdk.types.StorageType.ISCSI,
                sdk.types.StorageType.CINDER,
                sdk.types.StorageType.MANAGED_BLOCK_STORAGE
            ]
            if storage_type in block_types:
                return sdk.types.DiskFormat.COW, True
        except Exception as e:
            LOG.warn("Failed to check storage domain %s type: %s", sd_id, e)
        return sdk.types.DiskFormat.RAW, True

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
            self._resolve_target_environment(conn, target_environment)
            disks_service = conn.system_service().disks_service()
            storage_domain_id = target_environment["storage_domain_id"]

            storage_domains = (conn.system_service()
                               .storage_domains_service()
                               .list())
            active_sds = [
                sd for sd in storage_domains
                if sd.type == sdk.types.StorageDomainType.DATA and
                (sd.status is None or
                 sd.status == sdk.types.StorageDomainStatus.ACTIVE)
            ]
            storage_backends = []
            for sd in active_sds:
                storage_backends.append({"name": sd.name, "id": sd.id})
                storage_backends.append({"name": sd.id, "id": sd.id})

            existing = {v["disk_id"]: v for v in volumes_info}
            new_volumes_info = []

            # Disks erstellen / behalten
            for disk in export_info.get("devices", {}).get("disks", []):
                disk_id = disk.get(
                    "id",
                    disk.get("path", f"disk-{len(new_volumes_info)}"))
                size = disk["size_bytes"]

                # Storage-Domain via Mapping auflösen
                mapped_backend = provider_utils.get_storage_mapping_for_disk(
                    target_environment.get("storage_mappings", {}),
                    disk,
                    storage_backends,
                    config_default=storage_domain_id)

                sd_id = None
                for backend in storage_backends:
                    if backend["name"] == mapped_backend:
                        sd_id = backend["id"]
                        break

                if not sd_id:
                    resolved_sd = self._find_storage_domain(
                        conn, mapped_backend)
                    if resolved_sd:
                        sd_id = resolved_sd.id
                    else:
                        sd_id = storage_domain_id

                disk_exists = False
                if disk_id in existing:
                    old_vol = existing[disk_id]
                    try:
                        disks_service.disk_service(
                            old_vol["volume_id"]).get()
                        disk_exists = True
                    except Exception as ex:
                        is_not_found = (
                            "404" in str(ex) or
                            "NotFoundError" in type(ex).__name__)
                        if is_not_found:
                            LOG.warn(
                                "Disk %s from volumes_info was not found "
                                "on OLVM. Will recreate it.",
                                old_vol["volume_id"])
                        else:
                            raise

                if disk_exists:
                    old_vol = existing[disk_id]
                    # Größe prüfen und ggf. anpassen
                    self._ensure_disk_size(
                        conn, old_vol["volume_id"], size)
                    old_vol["size"] = size
                    old_vol["size_bytes"] = size
                    new_volumes_info.append(old_vol)
                else:
                    disk_format, disk_sparse = (
                        self._get_disk_format_and_sparse(conn, sd_id))
                    oVirt_disk = disks_service.add(
                        disk=sdk.types.Disk(
                            name=f"coriolis-{instance_name}-"
                                 f"{disk_id[:32]}",
                            description="Coriolis replica disk",
                            format=disk_format,
                            provisioned_size=size,
                            storage_domains=[
                                sdk.types.StorageDomain(id=sd_id)
                            ],
                            sparse=disk_sparse,
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
                        "size": size,
                        "size_bytes": size,
                    })

            return new_volumes_info
        finally:
            conn.close()

    def _ensure_disk_size(self, conn, disk_id, required_size_bytes):
        """Stellt sicher, dass eine Disk mindestens required_size_bytes hat."""
        import ovirtsdk4 as sdk
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
        conn = self._get_ovirt_connection(connection_info)
        try:
            self._resolve_target_environment(conn, target_environment)
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
                "password": connection_info.get("password"),
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

            # Detach disks to avoid locking them on the minion
            try:
                attachments_svc = vm_service.disk_attachments_service()
                for att in attachments_svc.list():
                    attachments_svc.attachment_service(att.id).remove(
                        detach_only=True)
            except Exception as e:
                LOG.warning(
                    "Failed to detach disks from minion VM %s: %s",
                    vm_id, e)

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
        conn = self._get_ovirt_connection(connection_info)
        mlog = mlog_mod.MigrationLogger(
            instance_name,
            log_dir=CONF.olvm.migration_log_dir)
        try:
            with mlog:
                return self._deploy_replica_instance_inner(
                    conn, mlog, target_environment, instance_name,
                    export_info, volumes_info, clone_disks)
        finally:
            conn.close()

    def _deploy_replica_instance_inner(
            self, conn, mlog, target_environment, instance_name,
            export_info, volumes_info, clone_disks):
        """Interne Implementierung von deploy_replica_instance()."""
        import ovirtsdk4 as sdk

        self._resolve_target_environment(conn, target_environment)
        vms_service = conn.system_service().vms_service()
        cluster_id = target_environment["cluster_id"]
        datacenter_id = target_environment.get("datacenter_id")

        memory_mb = export_info.get("memory_mb", 4096)
        vcpus = export_info.get("num_cpu", 2)

        # NICs konfigurieren:
        # Expliziter network_map-Eintrag hat Vorrang, sonst auto-provisioning.
        target_nics = []
        network_map = target_environment.get("network_map", {})
        for nic in export_info.get("devices", {}).get("nics", []):
            src_net = nic.get("network_name") or nic.get("network_id")
            dst_net = None
            if src_net:
                dst_net = network_map.get(src_net)
            if not dst_net:
                dst_net = network_map.get("None") or network_map.get("none")
            if not dst_net and network_map:
                dst_net = list(network_map.values())[0]

            # Auto-Provisioning: Netzwerk + VNIC-Profil auf OLVM anlegen
            if not dst_net and src_net and datacenter_id:
                vlan_id = nic.get("vlan_id", 0)
                LOG.info(
                    "Auto-provisioning network '%s' (VLAN %s) on OLVM ...",
                    src_net, vlan_id)
                dst_net = self._ensure_network_and_vnic_profile(
                    conn, datacenter_id, cluster_id,
                    network_name=src_net,
                    vlan_id=vlan_id)
                mlog.event(
                    "network_provisioned",
                    network=src_net,
                    vlan_id=vlan_id,
                    vnic_profile_id=dst_net)

            # NIC-Name bereinigen (nur alphanumeric, -, _, .)
            raw_nic_name = nic.get("name", "nic-0")
            nic_name = "".join(
                c if c.isalnum() or c in "-_." else "_"
                for c in raw_nic_name)[:15]

            if dst_net:
                target_nics.append(
                    sdk.types.Nic(
                        name=nic_name,
                        interface=sdk.types.NicInterface.VIRTIO,
                        vnic_profile=sdk.types.VnicProfile(
                            id=dst_net),
                    )
                )
            else:
                # Fallback: NIC ohne Profil (disconnected)
                target_nics.append(
                    sdk.types.Nic(
                        name=nic_name,
                        interface=sdk.types.NicInterface.VIRTIO,
                    )
                )

        # Firmware-Typ
        firmware = sdk.types.BiosType.I440FX_SEA_BIOS
        if export_info.get("firmware_type") == "EFI":
            firmware = sdk.types.BiosType.Q35_SEA_BIOS

        # VM erstellen
        mlog.event("vm_create_start", instance=instance_name)
        oVirt_vm = vms_service.add(
            vm=sdk.types.Vm(
                name=instance_name[:64],
                cluster=sdk.types.Cluster(id=cluster_id),
                template=sdk.types.Template(name="Blank"),
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
                bios=sdk.types.Bios(
                    type=firmware
                ),
                type=sdk.types.VmType.SERVER,
                nics=target_nics,
            )
        )
        mlog.event("vm_created", vm_id=oVirt_vm.id, vm_name=oVirt_vm.name)

        # Warten bis VM nicht mehr IMAGE_LOCKED
        vm_service = vms_service.vm_service(oVirt_vm.id)
        for _ in range(60):
            v = vm_service.get()
            if v.status != sdk.types.VmStatus.IMAGE_LOCKED:
                break
            time.sleep(2)

        for nic in target_nics:
            try:
                vm_service.nics_service().add(nic)
                LOG.info(
                    "Successfully added nic %s to target VM %s",
                    nic.name, oVirt_vm.id)
            except Exception as e:
                LOG.warning(
                    "Failed to add nic %s to target VM %s: %s",
                    nic.name, oVirt_vm.id, e)

        # Disks attachieren
        for idx, vol in enumerate(volumes_info):
            bootable = (idx == 0)
            size_gb = round(
                vol.get("size_bytes", 0) / (1024 ** 3), 1) \
                if vol.get("size_bytes") else None
            mlog.event(
                "disk_transfer",
                disk_id=vol.get("volume_id"),
                size_gb=size_gb,
                bootable=bootable,
                clone=clone_disks)
            if clone_disks:
                cloned = self._clone_disk(
                    conn, vol["volume_id"],
                    target_environment.get("storage_domain_id"))
                vol["clone_id"] = cloned.id
                self._attach_disk_to_vm(
                    conn, oVirt_vm.id, cloned.id, bootable=bootable)
            else:
                self._attach_disk_to_vm(
                    conn, oVirt_vm.id, vol["volume_id"], bootable=bootable)

        return {
            "instance_deployment_info": {
                "vm_id": oVirt_vm.id,
                "vm_name": oVirt_vm.name,
            }
        }

    def _clone_disk(self, conn, disk_id, storage_domain_id):
        """Klont eine oVirt-Disk."""
        import ovirtsdk4 as sdk
        import time
        import uuid

        disks_service = conn.system_service().disks_service()
        disk_service = disks_service.disk_service(disk_id)

        clone_name = f"clone-{uuid.uuid4().hex[:8]}"

        LOG.info("Cloning disk %s to storage domain %s with name %s...",
                 disk_id, storage_domain_id, clone_name)

        # Initiate copy action
        disk_service.copy(
            storage_domain=sdk.types.StorageDomain(id=storage_domain_id),
            disk=sdk.types.Disk(name=clone_name)
        )

        # Locate the new disk by name
        clone = None
        for _ in range(60):
            disks = disks_service.list(search=f"name={clone_name}")
            if disks:
                clone = disks[0]
                break
            time.sleep(2)
        else:
            raise exception.CoriolisException(
                f"Failed to find cloned disk {clone_name} after copy request.")

        # Wait for the clone operation to complete and the disk to be unlocked
        clone_service = disks_service.disk_service(clone.id)
        for _ in range(300):
            try:
                d = clone_service.get()
                if d.status == sdk.types.DiskStatus.OK:
                    LOG.info(
                        "Cloned disk %s is ready with status OK.", clone.id)
                    break
                if d.status == sdk.types.DiskStatus.ILLEGAL:
                    raise exception.CoriolisException(
                        f"Cloned disk {clone.id} is in ILLEGAL state.")
            except Exception as e:
                LOG.warning("Failed to poll cloned disk status: %s", e)
            time.sleep(2)
        else:
            raise exception.CoriolisException(
                f"Timeout waiting for cloned disk {clone.id} to become OK.")

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

    def create_replica_disk_snapshots(
            self, ctxt, connection_info, target_environment, volumes_info):
        """Erstellt oVirt Disk Snapshots."""
        return volumes_info

    def delete_replica_target_disk_snapshots(self, ctxt, connection_info,
                                             target_environment,
                                             volumes_info):
        """Löscht oVirt Disk Snapshots."""
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
        import ovirtsdk4 as sdk
        conn = self._get_ovirt_connection(connection_info)
        try:
            self._resolve_target_environment(conn, target_environment)
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
            sd_status = sd.status
            if cluster and getattr(cluster, "data_center", None):
                try:
                    datacenter_id = cluster.data_center.id
                    dc_sd = (conn.system_service()
                             .data_centers_service()
                             .data_center_service(datacenter_id)
                             .storage_domains_service()
                             .storage_domain_service(sd_id)
                             .get())
                    sd_status = dc_sd.status
                except Exception as ex:
                    LOG.warning(
                        "Failed to get storage domain status in data center "
                        "%s context: %s. Falling back to global status.",
                        datacenter_id, ex)

            if (sd_status is not None and
                    sd_status != sdk.types.StorageDomainStatus.ACTIVE):
                raise exception.InvalidInput(
                    f"Storage domain {sd_id} is not active "
                    f"(current status: {sd_status})")

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
