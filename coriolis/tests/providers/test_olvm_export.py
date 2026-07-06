# Copyright 2026 Thesolution.at
# All Rights Reserved.

from unittest import mock

from oslo_config import cfg

from coriolis import exception
from coriolis.providers.olvm import exp
from coriolis.tests import test_base

CONF = cfg.CONF


class OLVMoVirtExportProviderTestCase(test_base.CoriolisBaseTestCase):
    """Test suite for OLVMoVirtExportProvider."""

    def setUp(self):
        super(OLVMoVirtExportProviderTestCase, self).setUp()
        self.mock_event_manager = mock.MagicMock()
        self.provider = exp.OLVMoVirtExportProvider(self.mock_event_manager)

    def test_get_connection_info_schema(self):
        schema = self.provider.get_connection_info_schema()
        self.assertIn("url", schema["properties"])
        self.assertIn("username", schema["properties"])
        self.assertEqual(
            schema["required"], ["url", "username", "password"])

    @mock.patch.object(exp.OLVMoVirtExportProvider, "_get_ovirt_connection")
    def test_validate_connection(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_system = mock_conn.system_service.return_value
        mock_system.get.return_value.product_info.name = "oVirt Engine"
        mock_system.get.return_value.product_info.version.full_version = (
            "4.5.3")

        connection_info = {
            "url": "https://ovirt",
            "username": "admin",
            "password": "pwd"}
        self.provider.validate_connection(None, connection_info)

        mock_get_conn.assert_called_once_with(connection_info)
        mock_system.get.assert_called_once()
        mock_conn.close.assert_called_once()

    @mock.patch.object(exp.OLVMoVirtExportProvider, "_get_ovirt_connection")
    def test_get_instances(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_vm = mock.MagicMock()
        mock_vm.id = "vm-1"
        mock_vm.name = "test-vm"
        mock_vm.status = "up"
        mock_vm.memory = 4096 * 1024 * 1024
        mock_vm.cpu = None

        mock_system = mock_conn.system_service.return_value
        mock_system.vms_service.return_value.list.return_value = [mock_vm]

        instances = self.provider.get_instances(None, {}, {})
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]["id"], "vm-1")
        self.assertEqual(instances[0]["name"], "test-vm")

    @mock.patch.object(exp.OLVMoVirtExportProvider, "_find_vm_by_name")
    @mock.patch.object(exp.OLVMoVirtExportProvider, "_get_ovirt_connection")
    def test_get_instance(self, mock_get_conn, mock_find_vm):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_vm = mock.MagicMock()
        mock_vm.id = "vm-1"
        mock_vm.name = "test-vm"
        mock_vm.status = "up"
        mock_vm.memory = 2048 * 1024 * 1024
        mock_vm.cpu = None
        mock_find_vm.return_value = mock_vm

        instance = self.provider.get_instance(None, {}, {}, "test-vm")
        self.assertEqual(instance["id"], "vm-1")
        self.assertEqual(instance["memory_mb"], 2048)

    @mock.patch.object(exp.OLVMoVirtExportProvider, "_get_ovirt_connection")
    def test_get_networks(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_net = mock.MagicMock()
        mock_net.id = "net-1"
        mock_net.name = "ovirtmgmt"

        mock_system = mock_conn.system_service.return_value
        mock_system.networks_service.return_value.list.return_value = [
            mock_net]

        networks = self.provider.get_networks(None, {}, {})
        self.assertEqual(len(networks), 1)
        self.assertEqual(networks[0]["id"], "net-1")

    @mock.patch.object(exp.OLVMoVirtExportProvider, "_get_ovirt_connection")
    def test_get_storage(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_sd = mock.MagicMock()
        mock_sd.id = "sd-1"
        mock_sd.name = "data"
        mock_sd.available = 1000
        mock_sd.used = 500

        mock_system = mock_conn.system_service.return_value
        mock_system.storage_domains_service.return_value.list.return_value = [
            mock_sd]

        storage = self.provider.get_storage(None, {}, {})
        self.assertEqual(len(storage["storage_backends"]), 1)
        self.assertEqual(storage["storage_backends"][0]["id"], "sd-1")

    @mock.patch.object(exp.OLVMoVirtExportProvider, "_find_vm_by_name")
    @mock.patch.object(exp.OLVMoVirtExportProvider, "_get_ovirt_connection")
    def test_validate_replica_export_input(self, mock_get_conn, mock_find_vm):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_find_vm.return_value = None

        self.assertRaises(
            exception.InvalidInput,
            self.provider.validate_replica_export_input,
            None, {}, {}, "invalid-vm")

    @mock.patch.object(exp.OLVMoVirtExportProvider, "_find_vm_by_name")
    @mock.patch.object(exp.OLVMoVirtExportProvider, "_get_ovirt_connection")
    def test_deploy_replica_source_resources(
            self, mock_get_conn, mock_find_vm):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_vm = mock.MagicMock()
        mock_vm.id = "vm-1"
        mock_find_vm.return_value = mock_vm

        mock_system = mock_conn.system_service.return_value
        mock_vms = mock_system.vms_service.return_value.vm_service.return_value
        mock_snapshots = mock_vms.snapshots_service.return_value

        mock_snap = mock.MagicMock()
        mock_snap.id = "snap-1"
        mock_snapshots.add.return_value = mock_snap

        mock_snap_serv = mock_snapshots.snapshot_service.return_value
        mock_snap_curr = mock.MagicMock()
        mock_snap_curr.snapshot_status = "ok"
        mock_snap_serv.get.return_value = mock_snap_curr

        resources = self.provider.deploy_replica_source_resources(
            None, {}, {}, "test-vm", [])

        self.assertEqual(resources["source_vm_id"], "vm-1")
        self.assertEqual(resources["snapshot_id"], "snap-1")

    @mock.patch.object(exp.OLVMoVirtExportProvider, "_get_ovirt_connection")
    def test_delete_replica_source_resources(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_system = mock_conn.system_service.return_value
        mock_vms = mock_system.vms_service.return_value.vm_service.return_value
        mock_snapshots = mock_vms.snapshots_service.return_value
        mock_snap_serv = mock_snapshots.snapshot_service.return_value

        source_resources = {"source_vm_id": "vm-1", "snapshot_id": "snap-1"}
        self.provider.delete_replica_source_resources(
            None, {}, {}, source_resources)

        mock_snap_serv.remove.assert_called_once()
