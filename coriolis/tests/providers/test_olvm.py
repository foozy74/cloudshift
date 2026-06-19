# Copyright 2024 YourCompany
# All Rights Reserved.

from unittest import mock

from coriolis import exception
from coriolis.providers.olvm import imp
from coriolis.tests import test_base


class OLVMoVirtImportProviderTestCase(test_base.CoriolisBaseTestCase):
    """Test suite for OLVMoVirtImportProvider."""

    def setUp(self):
        super(OLVMoVirtImportProviderTestCase, self).setUp()
        self.mock_event_manager = mock.MagicMock()
        self.provider = imp.OLVMoVirtImportProvider(self.mock_event_manager)
        imp.CONF.set_override(
            "minion_template_name", "test-template", group="olvm")
        imp.CONF.set_override("minion_memory_mb", 4096, group="olvm")
        imp.CONF.set_override("minion_vcpus", 2, group="olvm")
        imp.CONF.set_override("writer_port", 6677, group="olvm")

    def test_get_connection_info_schema(self):
        schema = self.provider.get_connection_info_schema()
        self.assertIn("url", schema["properties"])
        self.assertIn("username", schema["properties"])
        self.assertIn("password", schema["properties"])
        self.assertEqual(schema["required"], ["url", "username", "password"])

    @mock.patch.object(imp.OLVMoVirtImportProvider, "_get_ovirt_connection")
    def test_validate_connection(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_system = mock_conn.system_service.return_value
        mock_system.get.return_value.product_info.name = "oVirt Engine"
        mock_system.get.return_value.product_info.version.full_version = (
            "4.5.3")

        connection_info = {
            "url": "https://ovirt", "username": "admin", "password": "pwd"}
        self.provider.validate_connection(None, connection_info)

        mock_get_conn.assert_called_once_with(connection_info)
        mock_system.get.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_get_target_environment_schema(self):
        schema = self.provider.get_target_environment_schema()
        self.assertIn("cluster_id", schema["properties"])
        self.assertIn("storage_domain_id", schema["properties"])
        self.assertEqual(
            schema["required"], ["cluster_id", "storage_domain_id"])

    @mock.patch.object(imp.OLVMoVirtImportProvider, "_get_ovirt_connection")
    def test_get_target_environment_options(self, mock_get_conn):
        from ovirtsdk4 import types

        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_cluster1 = mock.MagicMock()
        mock_cluster1.id = "c-1"
        mock_cluster1.name = "Default"

        mock_sd1 = mock.MagicMock()
        mock_sd1.id = "sd-1"
        mock_sd1.name = "DataDomain"
        mock_sd1.status = types.StorageDomainStatus.ACTIVE
        mock_sd1.type = types.StorageDomainType.DATA

        mock_system = mock_conn.system_service.return_value
        mock_system.clusters_service.return_value.list.return_value = [
            mock_cluster1]
        mock_system.storage_domains_service.return_value.list.return_value = [
            mock_sd1]

        options = self.provider.get_target_environment_options(None, {})
        self.assertEqual(len(options), 2)

        # Check Cluster options
        self.assertEqual(options[0]["name"], "cluster_id")
        self.assertEqual(options[0]["values"][0]["id"], "c-1")

        # Check Storage options
        self.assertEqual(options[1]["name"], "storage_domain_id")
        self.assertEqual(options[1]["values"][0]["id"], "sd-1")

    @mock.patch.object(imp.OLVMoVirtImportProvider, "_get_ovirt_connection")
    def test_get_networks(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_net = mock.MagicMock()
        mock_net.id = "n-1"
        mock_net.name = "VM Network"

        mock_system = mock_conn.system_service.return_value
        mock_system.networks_service.return_value.list.return_value = [
            mock_net]

        networks = self.provider.get_networks(None, {}, {})
        self.assertEqual(len(networks), 1)
        self.assertEqual(networks[0]["id"], "n-1")
        self.assertEqual(networks[0]["name"], "VM Network")

    @mock.patch.object(imp.OLVMoVirtImportProvider, "_get_ovirt_connection")
    def test_get_storage(self, mock_get_conn):
        from ovirtsdk4 import types

        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_sd = mock.MagicMock()
        mock_sd.id = "sd-1"
        mock_sd.name = "DataDomain"
        mock_sd.status = types.StorageDomainStatus.ACTIVE
        mock_sd.type = types.StorageDomainType.DATA

        mock_system = mock_conn.system_service.return_value
        mock_system.storage_domains_service.return_value.list.return_value = [
            mock_sd]

        storage = self.provider.get_storage(None, {}, {})
        self.assertEqual(len(storage["storage_backends"]), 1)
        self.assertEqual(storage["storage_backends"][0]["id"], "sd-1")

    @mock.patch.object(imp.OLVMoVirtImportProvider, "_get_ovirt_connection")
    def test_get_optimal_flavor(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_it1 = mock.MagicMock()
        mock_it1.name = "Small"
        mock_it1.cpu.topology.cores = 1
        mock_it1.memory = 2048 * 1024 * 1024

        mock_it2 = mock.MagicMock()
        mock_it2.name = "Medium"
        mock_it2.cpu.topology.cores = 2
        mock_it2.memory = 4096 * 1024 * 1024

        mock_system = mock_conn.system_service.return_value
        mock_system.instance_types_service.return_value.list.return_value = [
            mock_it1, mock_it2]

        export_info = {"num_cpu": 2, "memory_mb": 4000}
        flavor = self.provider.get_optimal_flavor(None, {}, {}, export_info)
        self.assertEqual(flavor, "Medium")

    @mock.patch.object(imp.OLVMoVirtImportProvider, "_get_ovirt_connection")
    def test_validate_replica_import_input(self, mock_get_conn):
        from ovirtsdk4 import types

        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_cluster = mock.MagicMock()
        mock_cluster.id = "c-1"
        mock_cluster.data_center = None

        mock_sd = mock.MagicMock()
        mock_sd.id = "sd-1"
        mock_sd.name = "DataDomain"
        mock_sd.status = types.StorageDomainStatus.ACTIVE
        mock_sd.available = 50 * 1024 * 1024 * 1024  # 50 GB available

        mock_system = mock_conn.system_service.return_value
        clusters = mock_system.clusters_service.return_value
        clusters.cluster_service.return_value.get.return_value = mock_cluster
        sd_svc = mock_system.storage_domains_service.return_value
        sd_svc.storage_domain_service.return_value.get.return_value = mock_sd

        target_env = {"cluster_id": "c-1", "storage_domain_id": "sd-1"}
        export_info = {
            "devices": {
                "disks": [
                    {"id": "disk-1",
                     "size_bytes": 10 * 1024 * 1024 * 1024}  # 10 GB
                ]
            }
        }

        # Should validate successfully
        self.provider.validate_replica_import_input(
            None, {}, target_env, export_info)

        # Should raise InvalidInput if space is not enough
        export_info_large = {
            "devices": {
                "disks": [
                    {"id": "disk-1",
                     "size_bytes": 60 * 1024 * 1024 * 1024}  # 60 GB
                ]
            }
        }
        self.assertRaises(
            exception.InvalidInput,
            self.provider.validate_replica_import_input,
            None, {}, target_env, export_info_large)

    @mock.patch.object(imp.OLVMoVirtImportProvider, "_find_storage_domain")
    @mock.patch.object(imp.OLVMoVirtImportProvider, "_find_cluster")
    @mock.patch.object(imp.OLVMoVirtImportProvider, "_get_ovirt_connection")
    def test_deploy_replica_disks_with_mapping(
            self, mock_get_conn, mock_find_cluster, mock_find_sd):
        from ovirtsdk4 import types

        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_cluster = mock.MagicMock()
        mock_cluster.id = "c-1"
        mock_find_cluster.return_value = mock_cluster

        mock_sd_default = mock.MagicMock()
        mock_sd_default.id = "sd-1"
        mock_sd_default.name = "DataDomain1"
        mock_find_sd.return_value = mock_sd_default

        mock_sd1 = mock.MagicMock()
        mock_sd1.id = "sd-1"
        mock_sd1.name = "DataDomain1"
        mock_sd1.type = types.StorageDomainType.DATA
        mock_sd1.status = types.StorageDomainStatus.ACTIVE

        mock_sd2 = mock.MagicMock()
        mock_sd2.id = "sd-2"
        mock_sd2.name = "DataDomain2"
        mock_sd2.type = types.StorageDomainType.DATA
        mock_sd2.status = types.StorageDomainStatus.ACTIVE

        system = mock_conn.system_service.return_value
        system.storage_domains_service.return_value.list.return_value = [
            mock_sd1, mock_sd2]

        mock_new_disk = mock.MagicMock()
        mock_new_disk.id = "new-disk-uuid"
        mock_new_disk.name = "coriolis-my-instance-disk-1"
        system.disks_service.return_value.add.return_value = mock_new_disk

        mock_disk_service = mock.MagicMock()
        mock_disk_status = mock.MagicMock()
        mock_disk_status.status = types.DiskStatus.OK
        mock_disk_service.get.return_value = mock_disk_status
        system.disks_service.return_value.disk_service.return_value = (
            mock_disk_service)

        target_env = {
            "cluster_id": "c-1",
            "storage_domain_id": "sd-1",
            "storage_mappings": {
                "disk_mappings": [
                    {"disk_id": "disk-1", "destination": "DataDomain2"}
                ]
            }
        }
        export_info = {
            "devices": {
                "disks": [
                    {"id": "disk-1", "size_bytes": 1024}
                ]
            }
        }

        volumes_info = []
        new_vols = self.provider.deploy_replica_disks(
            None, {}, target_env, "my-instance", export_info, volumes_info)

        self.assertEqual(len(new_vols), 1)
        self.assertEqual(new_vols[0]["volume_id"], "new-disk-uuid")
        self.assertEqual(new_vols[0]["disk_id"], "disk-1")

        # Verify it was added to DataDomain2 (sd-2)
        added_call_args = system.disks_service.return_value.add.call_args[1]
        added_disk = added_call_args["disk"]
        self.assertEqual(added_disk.storage_domains[0].id, "sd-2")

    @mock.patch('time.sleep', mock.MagicMock())
    def test_get_vm_ip_success(self):
        from ovirtsdk4 import types
        mock_conn = mock.MagicMock()
        system_svc = mock_conn.system_service.return_value
        vms_svc = system_svc.vms_service.return_value
        vm_svc = vms_svc.vm_service.return_value

        # Mock NICs list
        mock_nic = mock.MagicMock()
        mock_nic.mac.address = "00:1A:2b:3C:4d:5E"
        vm_svc.nics_service.return_value.list.return_value = [mock_nic]

        # Mock reported devices
        # Device 1: mismatching MAC
        mock_dev1 = mock.MagicMock()
        mock_dev1.mac.address = "11:22:33:44:55:66"
        mock_ip1 = mock.MagicMock()
        mock_ip1.version = types.IpVersion.V4
        mock_ip1.address = "10.0.0.1"
        mock_dev1.ips = [mock_ip1]

        # Device 2: matching MAC but no IPs or non-v4 IP (e.g. v6)
        mock_dev2 = mock.MagicMock()
        mock_dev2.mac.address = "00:1a:2b:3c:4d:5e"
        mock_ip2 = mock.MagicMock()
        mock_ip2.version = types.IpVersion.V6
        mock_ip2.address = "fe80::1"
        mock_dev2.ips = [mock_ip2]

        # Device 3: matching MAC with v4 IP
        mock_dev3 = mock.MagicMock()
        mock_dev3.mac.address = "00:1A:2B:3C:4D:5E"
        mock_ip3 = mock.MagicMock()
        mock_ip3.version = types.IpVersion.V4
        mock_ip3.address = "192.168.1.50"
        mock_dev3.ips = [mock_ip3]

        vm_svc.reported_devices_service.return_value.list.return_value = [
            mock_dev1, mock_dev2, mock_dev3
        ]

        ip = self.provider._get_vm_ip(mock_conn, "test-vm-id", timeout=5)
        self.assertEqual("192.168.1.50", ip)

    @mock.patch('time.sleep', mock.MagicMock())
    def test_get_vm_ip_timeout(self):
        mock_conn = mock.MagicMock()
        system_svc = mock_conn.system_service.return_value
        vms_svc = system_svc.vms_service.return_value
        vm_svc = vms_svc.vm_service.return_value

        # Mock NICs list empty
        vm_svc.nics_service.return_value.list.return_value = []
        vm_svc.reported_devices_service.return_value.list.return_value = []

        self.assertRaises(
            exception.NotFound,
            self.provider._get_vm_ip,
            mock_conn, "test-vm-id", timeout=10)

    @mock.patch.object(imp.OLVMoVirtImportProvider, "_wait_for_vm_down")
    @mock.patch.object(imp.OLVMoVirtImportProvider, "_get_ovirt_connection")
    def test_delete_replica_target_resources(
            self, mock_get_conn, mock_wait_down):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        system_svc = mock_conn.system_service.return_value
        vms_svc = system_svc.vms_service.return_value
        vm_svc = vms_svc.vm_service.return_value

        mock_da1 = mock.MagicMock()
        mock_da1.id = "attachment-1"
        vm_svc.disk_attachments_service.return_value.list.return_value = [
            mock_da1]

        attachment_svc = (vm_svc.disk_attachments_service.return_value
                          .attachment_service.return_value)

        migr_resources_dict = {"minion_vm_id": "test-minion-id"}

        self.provider.delete_replica_target_resources(
            None, {}, {}, migr_resources_dict)

        mock_get_conn.assert_called_once()
        vm_svc.stop.assert_called_once()
        mock_wait_down.assert_called_once_with(vms_svc, "test-minion-id")
        vm_svc.disk_attachments_service.return_value.list.assert_called_once()
        vm_svc.disk_attachments_service.return_value \
            .attachment_service.assert_called_once_with(
                "attachment-1")
        attachment_svc.remove.assert_called_once_with(detach_only=True)
        vm_svc.remove.assert_called_once()
        mock_conn.close.assert_called_once()

    @mock.patch('time.sleep', mock.MagicMock())
    def test_clone_disk_success(self):
        from ovirtsdk4 import types
        mock_conn = mock.MagicMock()
        system_svc = mock_conn.system_service.return_value
        disks_svc = system_svc.disks_service.return_value
        disk_svc = disks_svc.disk_service.return_value

        mock_disk = mock.MagicMock()
        mock_disk.id = "cloned-disk-id"
        mock_disk.status = types.DiskStatus.OK
        disk_svc.get.return_value = mock_disk

        # Mock list to find our disk
        disks_svc.list.return_value = [mock_disk]

        res = self.provider._clone_disk(
            mock_conn, "source-disk-id", "storage-domain-id")

        self.assertEqual(mock_disk, res)
        disk_svc.copy.assert_called_once()
        disks_svc.list.assert_called_once()
        disk_svc.get.assert_called_once()

    @mock.patch('time.sleep', mock.MagicMock())
    def test_create_minion_vm_config(self):
        mock_conn = mock.MagicMock()
        mock_system = mock_conn.system_service.return_value
        mock_vms_service = mock_system.vms_service.return_value
        mock_vm = mock.MagicMock()
        mock_vm.id = "test-vm-id"
        mock_vms_service.add.return_value = mock_vm

        # Mock clusters and vnic profiles services to avoid errors
        mock_system.clusters_service.side_effect = Exception("skip clusters")

        res = self.provider._create_minion_vm(mock_conn, "cluster-id", {})

        self.assertEqual(mock_vm, res)
        mock_vms_service.add.assert_called_once()
        added_vm = mock_vms_service.add.call_args[1]['vm']
        self.assertEqual("test-template", added_vm.template.name)

    @mock.patch('time.sleep', mock.MagicMock())
    def test_create_minion_vm_target_env(self):
        mock_conn = mock.MagicMock()
        mock_system = mock_conn.system_service.return_value
        mock_vms_service = mock_system.vms_service.return_value
        mock_vm = mock.MagicMock()
        mock_vm.id = "test-vm-id"
        mock_vms_service.add.return_value = mock_vm

        # Mock clusters and vnic profiles services to avoid errors
        mock_system.clusters_service.side_effect = Exception("skip clusters")

        res = self.provider._create_minion_vm(
            mock_conn, "cluster-id",
            {"minion_template_name": "custom-template"})

        self.assertEqual(mock_vm, res)
        mock_vms_service.add.assert_called_once()
        added_vm = mock_vms_service.add.call_args[1]['vm']
        self.assertEqual("custom-template", added_vm.template.name)
