# Copyright 2024 YourCompany
# All Rights Reserved.

from unittest import mock

# Mock pyVmomi and pyVim before importing providers if needed,
# or mock them locally in the tests since they are in requirements.txt.
# We will use mock patches for pyVmomi and pyVim.

from coriolis import exception
from coriolis.providers.vmware import exp
from coriolis.tests import test_base


class VMwareVSphereExportProviderTestCase(test_base.CoriolisBaseTestCase):
    """Test suite for VMwareVSphereExportProvider."""

    def setUp(self):
        super(VMwareVSphereExportProviderTestCase, self).setUp()
        self.mock_event_manager = mock.MagicMock()
        self.provider = exp.VMwareVSphereExportProvider(
            self.mock_event_manager)

    def test_get_connection_info_schema(self):
        schema = self.provider.get_connection_info_schema()
        self.assertIn("host", schema["properties"])
        self.assertIn("username", schema["properties"])
        self.assertIn("password", schema["properties"])
        self.assertEqual(schema["required"], ["host", "username", "password"])

    @mock.patch("pyVim.connect.Disconnect")
    @mock.patch.object(exp.VMwareVSphereExportProvider, "_get_vcenter_session")
    def test_validate_connection(self, mock_get_session, mock_disconnect):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si
        mock_si.RetrieveContent.return_value.about.fullName = (
            "VMware vCenter 8.0")

        connection_info = {"host": "vc", "username": "user", "password": "pwd"}
        self.provider.validate_connection(None, connection_info)

        mock_get_session.assert_called_once_with(connection_info)
        mock_si.RetrieveContent.assert_called_once()
        mock_disconnect.assert_called_once_with(mock_si)

    @mock.patch("pyVim.connect.Disconnect")
    @mock.patch.object(exp.VMwareVSphereExportProvider, "_get_vcenter_session")
    def test_get_instances(self, mock_get_session, mock_disconnect):

        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_vm1 = mock.MagicMock()
        mock_vm1._moId = "vm-1"
        mock_vm1.name = "test-vm-1"
        mock_vm1.config.hardware.numCPU = 2
        mock_vm1.config.hardware.memoryMB = 4096
        mock_vm1.config.guestId = "ubuntu64Guest"
        mock_vm1.config.firmware = "bios"

        mock_vm2 = mock.MagicMock()
        mock_vm2._moId = "vm-2"
        mock_vm2.name = "other-vm"
        mock_vm2.config.hardware.numCPU = 4
        mock_vm2.config.hardware.memoryMB = 8192
        mock_vm2.config.guestId = "winNetEnterpriseGuest"
        mock_vm2.config.firmware = "efi"

        mock_container = mock.MagicMock()
        mock_container.view = [mock_vm1, mock_vm2]
        view_mgr = mock_si.RetrieveContent.return_value.viewManager
        view_mgr.CreateContainerView.return_value = mock_container

        connection_info = {"host": "vc", "username": "user", "password": "pwd"}

        # Test listing all
        instances = self.provider.get_instances(None, connection_info, {})
        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[0]["id"], "vm-1")
        self.assertEqual(instances[0]["os_type"], "linux")
        self.assertEqual(instances[1]["id"], "vm-2")
        self.assertEqual(instances[1]["os_type"], "windows")

        # Test listing with pattern
        instances = self.provider.get_instances(
            None, connection_info, {}, instance_name_pattern="test")
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]["name"], "test-vm-1")

        mock_container.Destroy.assert_called()
        mock_disconnect.assert_called()

    @mock.patch("pyVim.connect.Disconnect")
    @mock.patch.object(exp.VMwareVSphereExportProvider, "_get_vcenter_session")
    def test_get_instance(self, mock_get_session, mock_disconnect):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_vm = mock.MagicMock()
        mock_vm._moId = "vm-1"
        mock_vm.name = "test-vm-1"
        mock_vm.config.hardware.numCPU = 2
        mock_vm.config.hardware.memoryMB = 4096
        mock_vm.config.guestId = "ubuntu64Guest"
        mock_vm.config.firmware = "bios"

        with mock.patch.object(
                self.provider, "_find_vm_by_name", return_value=mock_vm):
            instance = self.provider.get_instance(None, {}, {}, "test-vm-1")
            self.assertEqual(instance["id"], "vm-1")
            self.assertEqual(instance["name"], "test-vm-1")
            self.assertEqual(instance["num_cpu"], 2)
            self.assertEqual(instance["memory_mb"], 4096)

    def test_get_source_environment_options(self):
        opts = self.provider.get_source_environment_options(None, {})
        self.assertEqual(len(opts), 1)
        self.assertEqual(opts[0]["name"], "shutdown_instances")

    def test_get_source_environment_schema(self):
        schema = self.provider.get_source_environment_schema()
        self.assertIn("shutdown_instances", schema["properties"])
        self.assertIn("worker_ip", schema["properties"])
        self.assertIn("worker_ssh_user", schema["properties"])
        self.assertIn("worker_ssh_password", schema["properties"])
        self.assertIn("worker_ssh_pkey", schema["properties"])

    @mock.patch("pyVim.connect.Disconnect")
    @mock.patch.object(exp.VMwareVSphereExportProvider, "_get_vcenter_session")
    def test_validate_replica_export_input(
            self, mock_get_session, mock_disconnect):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_vm = mock.MagicMock()
        mock_vm.config = None  # inaccessible config

        with mock.patch.object(
                self.provider, "_find_vm_by_name", return_value=mock_vm):
            self.assertRaises(
                exception.InvalidInput,
                self.provider.validate_replica_export_input,
                None, {}, "test-vm", {})

    @mock.patch("pyVim.connect.Disconnect")
    @mock.patch.object(exp.VMwareVSphereExportProvider, "_get_vcenter_session")
    def test_get_replica_instance_info(
            self, mock_get_session, mock_disconnect):
        from pyVmomi import vim

        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_vm = mock.MagicMock()
        mock_vm._moId = "vm-1"
        mock_vm.name = "test-vm-1"
        mock_vm.config.hardware.numCPU = 2
        mock_vm.config.hardware.memoryMB = 4096
        mock_vm.config.guestId = "ubuntu64Guest"
        mock_vm.config.firmware = "bios"
        mock_vm.config.flags = {}
        mock_vm.config.nestedHVEnabled = True

        # Mock devices
        with mock.patch(
                "pyVmomi.VmomiSupport.CheckField", lambda info, val: None):
            mock_disk = vim.vm.device.VirtualDisk()
            mock_disk.key = 2000
            mock_disk.capacityInKB = 10 * 1024 * 1024
            mock_disk.unitNumber = 0
            mock_disk.backing = mock.MagicMock()
            mock_disk.backing.fileName = "[ds1] test/test.vmdk"
            mock_disk.backing.datastore.name = "ds1"

            mock_nic = vim.vm.device.VirtualEthernetCard()
            mock_nic.key = 4000
            mock_nic.unitNumber = 1
            mock_nic.macAddress = "00:11:22:33:44:55"
            mock_nic.deviceInfo = mock.MagicMock()
            mock_nic.deviceInfo.label = "Nic 1"
            mock_nic.backing = mock.MagicMock()
            mock_nic.backing.network.name = "VM Network"
            mock_nic.backing.deviceName = "net-1"

        mock_vm.config.hardware.device = [mock_disk, mock_nic]
        mock_vm.config.bootOptions.bootOrder = []

        with mock.patch.object(
                self.provider, "_find_vm_by_name", return_value=mock_vm):
            info = self.provider.get_replica_instance_info(
                None, {}, {}, "test-vm-1")
            self.assertEqual(info["id"], "vm-1")
            self.assertEqual(info["nested_virtualization"], True)
            self.assertEqual(len(info["devices"]["disks"]), 1)
            self.assertEqual(
                info["devices"]["disks"][0]["id"], "disk-2000")
            self.assertEqual(
                info["devices"]["disks"][0]["size_bytes"],
                10 * 1024 * 1024 * 1024)
            self.assertEqual(len(info["devices"]["nics"]), 1)
            self.assertEqual(
                info["devices"]["nics"][0]["mac_address"],
                "00:11:22:33:44:55")

    def test_deploy_replica_source_resources(self):
        export_info = {"hostname": "192.168.1.100"}
        source_environment = {
            "worker_ssh_pkey": "key",
            "worker_ssh_user": "admin",
            "esxi_host": "esxi-1"
        }
        res = self.provider.deploy_replica_source_resources(
            None, {}, export_info, source_environment)

        self.assertEqual(res["connection_info"]["ip"], "192.168.1.100")
        self.assertEqual(res["connection_info"]["username"], "admin")
        self.assertEqual(res["connection_info"]["pkey"], "key")
        self.assertEqual(res["migr_resources"]["esxi_host"], "esxi-1")

    @mock.patch("socket.socket")
    def test_deploy_replica_source_resources_missing_ip(self, mock_socket):
        # Ensure socket resolution fails to trigger exception
        mock_socket.side_effect = Exception("failed connect")
        export_info = {}
        source_environment = {}
        self.assertRaises(
            exception.InvalidInput,
            self.provider.deploy_replica_source_resources,
            None, {}, export_info, source_environment)

    def test_deploy_replica_source_resources_config_ip(self):
        exp.CONF.set_override("worker_ip", "10.10.10.10", group="vmware")
        self.addCleanup(exp.CONF.clear_override, "worker_ip", group="vmware")
        export_info = {}
        source_environment = {}
        res = self.provider.deploy_replica_source_resources(
            None, {}, export_info, source_environment)
        self.assertEqual(res["connection_info"]["ip"], "10.10.10.10")

    def test_deploy_replica_source_resources_config_password(self):
        exp.CONF.set_override("worker_ip", "10.10.10.10", group="vmware")
        self.addCleanup(exp.CONF.clear_override, "worker_ip", group="vmware")
        exp.CONF.set_override(
            "worker_ssh_password", "test-pass", group="vmware")
        self.addCleanup(
            exp.CONF.clear_override, "worker_ssh_password", group="vmware")
        export_info = {}
        source_environment = {}
        res = self.provider.deploy_replica_source_resources(
            None, {}, export_info, source_environment)
        self.assertEqual(res["connection_info"]["password"], "test-pass")
        self.assertIsNone(res["connection_info"]["pkey"])

    @mock.patch("os.path.exists")
    @mock.patch("builtins.open", new_callable=mock.mock_open,
                read_data="mocked-pkey")
    def test_deploy_replica_source_resources_config_pkey_path(
            self, mock_open, mock_exists):
        mock_exists.return_value = True
        exp.CONF.set_override("worker_ip", "10.10.10.10", group="vmware")
        self.addCleanup(exp.CONF.clear_override, "worker_ip", group="vmware")
        exp.CONF.set_override(
            "worker_ssh_pkey_path", "/path/to/pkey", group="vmware")
        self.addCleanup(
            exp.CONF.clear_override, "worker_ssh_pkey_path", group="vmware")
        export_info = {}
        source_environment = {}
        res = self.provider.deploy_replica_source_resources(
            None, {}, export_info, source_environment)
        self.assertEqual(res["connection_info"]["pkey"], "mocked-pkey")
        self.assertIsNone(res["connection_info"]["password"])
        mock_exists.assert_called_once_with("/path/to/pkey")
        mock_open.assert_called_once_with("/path/to/pkey", "r")

    @mock.patch("time.sleep")
    @mock.patch("pyVim.connect.Disconnect")
    @mock.patch.object(exp.VMwareVSphereExportProvider, "_get_vcenter_session")
    def test_shutdown_instance(
            self, mock_get_session, mock_disconnect, mock_sleep):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_vm = mock.MagicMock()
        mock_vm.runtime.powerState = "poweredOn"
        mock_vm.guest.toolsRunningStatus = "guestToolsRunning"

        with mock.patch.object(
                self.provider, "_find_vm_by_name", return_value=mock_vm):
            self.provider.shutdown_instance(
                None, {}, {"shutdown_instances": True}, "test-vm")
            mock_vm.ShutdownGuest.assert_called_once()

    @mock.patch("pyVim.connect.Disconnect")
    @mock.patch.object(exp.VMwareVSphereExportProvider, "_get_vcenter_session")
    @mock.patch("coriolis.providers.backup_writers.BackupWritersFactory")
    @mock.patch("coriolis.providers.replicator.Replicator")
    def test_replicate_disks(
            self, mock_replicator_cls, mock_writer_factory,
            mock_get_session, mock_disconnect):
        from pyVmomi import vim

        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_vm = mock.MagicMock()
        check_field_path = "pyVmomi.VmomiSupport.CheckField"
        with mock.patch(check_field_path, lambda info, val: None):
            mock_disk = vim.vm.device.VirtualDisk()
            mock_disk.key = 2000
            mock_disk.capacityInKB = 10 * 1024 * 1024
        mock_vm.config.hardware.device = [mock_disk]

        with mock.patch.object(
                self.provider, "_find_vm_by_name", return_value=mock_vm):
            mock_replicator = mock.MagicMock()
            mock_replicator_cls.return_value = mock_replicator
            mock_replicator.get_replica_state.return_value = "replica-state"
            mock_replicator._cli.get_status.return_value = []

            mock_writer = mock.MagicMock()
            mock_writer_factory.return_value.get_writer.return_value = (
                mock_writer)

            volumes_info = [
                {
                    "disk_id": "disk-2000",
                    "size_bytes": 1000,
                }
            ]

            res = self.provider.replicate_disks(
                None, {}, {}, "test-vm", {}, {}, {}, volumes_info, True)

            mock_replicator_cls.assert_called_once_with(
                {}, self.provider._event_manager, volumes_info, None,
                use_compression=False)
            mock_replicator.init_replicator.assert_called_once()
            mock_replicator.wait_for_chunks.assert_called_once()
            expected_source_vols = [
                {"disk_id": "disk-2000",
                 "disk_path": "/dev/mapper/coriolis-disk-2000"}]
            mock_replicator.replicate_disks.assert_called_once_with(
                expected_source_vols, mock_writer)
            mock_writer_factory.assert_called_once_with({}, volumes_info)
            self.assertEqual(res, volumes_info)
