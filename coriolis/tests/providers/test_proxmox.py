# Copyright 2026 Thesolution.at
# All Rights Reserved.

from unittest import mock

from oslo_config import cfg

from coriolis import exception
from coriolis.providers.proxmox import imp
from coriolis.tests import test_base

CONF = cfg.CONF


class ProxmoxImportProviderTestCase(test_base.CoriolisBaseTestCase):
    """Test suite for ProxmoxImportProvider."""

    def setUp(self):
        super(ProxmoxImportProviderTestCase, self).setUp()
        self.mock_event_manager = mock.MagicMock()
        self.provider = imp.ProxmoxImportProvider(self.mock_event_manager)

        # Mock out Config options
        imp.CONF.set_override(
            "minion_template_id", "test-template", group="proxmox")
        imp.CONF.set_override("minion_memory_mb", 4096, group="proxmox")
        imp.CONF.set_override("minion_vcpus", 2, group="proxmox")
        imp.CONF.set_override("writer_port", 6677, group="proxmox")

    def test_get_connection_info_schema(self):
        schema = self.provider.get_connection_info_schema()
        self.assertIn("url", schema["properties"])
        self.assertIn("username", schema["properties"])
        self.assertEqual(schema["required"], ["url", "username"])

    @mock.patch.object(imp.ProxmoxImportProvider, "_get_proxmox_connection")
    def test_validate_connection(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_conn.nodes.get.return_value = [
            {"node": "pve1"}, {"node": "pve2"}]

        connection_info = {
            "url": "https://pve",
            "username": "root@pam",
            "password": "pwd"}
        self.provider.validate_connection(None, connection_info)

        mock_get_conn.assert_called_once_with(connection_info)
        mock_conn.nodes.get.assert_called_once()

    def test_get_target_environment_schema(self):
        schema = self.provider.get_target_environment_schema()
        self.assertIn("node", schema["properties"])
        self.assertIn("storage", schema["properties"])
        self.assertEqual(schema["required"], ["node", "storage"])

    @mock.patch.object(imp.ProxmoxImportProvider, "_get_proxmox_connection")
    def test_get_target_environment_options(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_conn.nodes.get.return_value = [{"node": "pve1"}]
        mock_conn.storage.get.return_value = [
            {"storage": "local-lvm", "active": 1},
            {"storage": "ceph-storage", "active": 0}
        ]

        options = self.provider.get_target_environment_options(None, {})
        self.assertEqual(len(options), 2)
        self.assertEqual(options[0]["name"], "node")
        self.assertEqual(options[0]["values"][0]["id"], "pve1")
        self.assertEqual(options[1]["name"], "storage")
        self.assertEqual(options[1]["values"][0]["id"], "local-lvm")

    @mock.patch.object(imp.ProxmoxImportProvider, "_get_proxmox_connection")
    def test_get_networks(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_conn.nodes.get.return_value = [{"node": "pve1"}]
        mock_network = mock_conn.nodes.return_value.network
        mock_network.get.return_value = [
            {"iface": "vmbr0", "type": "bridge", "active": 1},
            {"iface": "eth0", "type": "eth", "active": 1}
        ]

        networks = self.provider.get_networks(None, {}, {"node": "pve1"})
        self.assertEqual(len(networks), 1)
        self.assertEqual(networks[0]["id"], "vmbr0")

    @mock.patch.object(imp.ProxmoxImportProvider, "_get_proxmox_connection")
    def test_get_storage(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn

        mock_storage = mock_conn.nodes.return_value.storage.return_value
        mock_storage.status.get.return_value = {
            "total": 1000, "avail": 600, "used": 400
        }

        storage_info = self.provider.get_storage(
            None, {}, {"node": "pve1", "storage": "local-lvm"})
        self.assertEqual(storage_info["available_bytes"], 600)
        self.assertEqual(storage_info["total_bytes"], 1000)

    def test_get_optimal_flavor(self):
        export_info = {"vcpus": 4, "memory_mb": 8192}
        flavor = self.provider.get_optimal_flavor(
            None, {}, "test-vm", export_info)
        self.assertEqual(flavor["vcpus"], 4)
        self.assertEqual(flavor["memory_mb"], 8192)

    @mock.patch.object(imp.ProxmoxImportProvider, "_find_vm_by_name")
    @mock.patch.object(imp.ProxmoxImportProvider, "_get_proxmox_connection")
    def test_deploy_replica_disks(self, mock_get_conn, mock_find_vm):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_find_vm.return_value = ("pve1", 100)

        # Storage get mock
        mock_storage = mock_conn.nodes.return_value.storage.return_value
        mock_content = mock_storage.content
        mock_content.return_value.get.side_effect = Exception("Not Found")
        mock_content.post.return_value = "local-lvm:vm-100-disk-0"

        export_info = {
            "devices": {
                "disks": [
                    # 10 GB
                    {"id": "disk-1", "size_bytes": 10737418240}
                ]
            }
        }
        volumes = self.provider.deploy_replica_disks(
            None, {}, {"node": "pve1", "storage": "local-lvm"},
            "test-vm", export_info, [])

        self.assertEqual(len(volumes), 1)
        self.assertEqual(volumes[0]["volume_id"], "local-lvm:vm-100-disk-0")

    @mock.patch.object(imp.ProxmoxImportProvider, "_get_vm_ip")
    @mock.patch.object(imp.ProxmoxImportProvider, "_wait_for_vm_up")
    @mock.patch.object(imp.ProxmoxImportProvider, "_create_minion_vm")
    @mock.patch.object(imp.ProxmoxImportProvider, "_get_proxmox_connection")
    @mock.patch(
        "coriolis.providers.backup_writers."
        "HTTPBackupWriterBootstrapper")
    @mock.patch("coriolis.utils.exec_ssh_cmd")
    def test_deploy_replica_target_resources(
            self, mock_ssh, mock_bootstrapper_cls, mock_get_conn,
            mock_create_minion, mock_wait_up, mock_get_ip):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_create_minion.return_value = 999
        mock_get_ip.return_value = "10.0.0.5"

        mock_bootstrapper = mock.MagicMock()
        mock_bootstrapper_cls.return_value = mock_bootstrapper
        mock_bootstrapper.setup_writer.return_value = {"details": "data"}

        # ssh response for finding disk
        mock_ssh.return_value = "/dev/sdb"

        volumes_info = [
            {"disk_id": "disk-1", "volume_id": "local-lvm:vm-100-disk-0"}
        ]
        res = self.provider.deploy_replica_target_resources(
            None, {}, {"node": "pve1", "storage": "local-lvm"}, volumes_info)

        self.assertEqual(res["migr_resources"]["minion_vm_id"], 999)
        self.assertEqual(res["volumes_info"][0]["volume_dev"], "/dev/sdb")

    @mock.patch.object(imp.ProxmoxImportProvider, "_wait_for_vm_down")
    @mock.patch.object(imp.ProxmoxImportProvider, "_get_proxmox_connection")
    def test_delete_replica_target_resources(
            self, mock_get_conn, mock_wait_down):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_qemu = mock_conn.nodes.return_value.qemu.return_value
        mock_qemu.status.current.get.return_value = {"status": "running"}
        mock_qemu.config.get.return_value = {
            "scsi0": "bootdisk", "scsi1": "replica-disk"
        }

        migr_resources = {"minion_vm_id": 999}
        self.provider.delete_replica_target_resources(
            None, {}, {"node": "pve1"}, migr_resources)

        mock_qemu.config.post.assert_any_call(delete="scsi1")
        mock_qemu.delete.assert_called_once()

    @mock.patch.object(imp.ProxmoxImportProvider, "_wait_for_task")
    @mock.patch.object(imp.ProxmoxImportProvider, "_find_vm_by_name")
    @mock.patch.object(imp.ProxmoxImportProvider, "_get_proxmox_connection")
    def test_deploy_replica_instance(
            self, mock_get_conn, mock_find_vm, mock_wait_task):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_find_vm.return_value = (None, None)
        mock_conn.cluster.nextid.get.return_value = 100

        export_info = {
            "vcpus": 2,
            "memory_mb": 4096,
            "devices": {"nics": []}
        }
        volumes_info = [{"volume_id": "local-lvm:vm-100-disk-0"}]

        res = self.provider.deploy_replica_instance(
            None, {}, {"node": "pve1", "storage": "local-lvm"}, "test-vm",
            export_info, volumes_info, clone_disks=True)

        self.assertEqual(res["vm_id"], 100)
        mock_qemu = mock_conn.nodes.return_value.qemu.return_value
        mock_qemu.move_volume.post.assert_called_once()

    @mock.patch.object(imp.ProxmoxImportProvider, "_get_proxmox_connection")
    def test_validate_replica_import_input(self, mock_get_conn):
        mock_conn = mock.MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.nodes.get.return_value = [{"node": "pve1"}]
        mock_storage = mock_conn.nodes.return_value.storage.return_value
        mock_storage.status.get.return_value = {
            "avail": 20 * 1024 * 1024 * 1024
        }

        export_info = {
            "devices": {
                # 10 GB
                "disks": [{"size_bytes": 10 * 1024 * 1024 * 1024}]
            }
        }

        # Should pass
        self.provider.validate_replica_import_input(
            None, {}, {"node": "pve1", "storage": "local-lvm"}, export_info)

        # Should fail due to node not found
        self.assertRaises(
            exception.InvalidInput,
            self.provider.validate_replica_import_input,
            None, {}, {"node": "pve-invalid", "storage": "local-lvm"},
            export_info)

        # Should fail due to space
        export_info_large = {
            "devices": {
                # 30 GB
                "disks": [{"size_bytes": 30 * 1024 * 1024 * 1024}]
            }
        }
        self.assertRaises(
            exception.InvalidInput,
            self.provider.validate_replica_import_input,
            None, {}, {"node": "pve1", "storage": "local-lvm"},
            export_info_large)
