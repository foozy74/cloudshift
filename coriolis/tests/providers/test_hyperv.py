# Copyright 2024 thesolution.at
# All Rights Reserved.

from unittest import mock

from coriolis import exception
from coriolis.providers.hyperv import imp
from coriolis.tests import test_base


class HyperVImportProviderTestCase(test_base.CoriolisBaseTestCase):
    """Test suite for HyperVImportProvider."""

    def setUp(self):
        super(HyperVImportProviderTestCase, self).setUp()
        self.mock_event_manager = mock.MagicMock()
        self.provider = imp.HyperVImportProvider(self.mock_event_manager)
        imp.CONF.set_override(
            "minion_template_vhdx", "C:\\templates\\ubuntu.vhdx",
            group="hyperv")
        imp.CONF.set_override("minion_memory_mb", 4096, group="hyperv")
        imp.CONF.set_override("minion_vcpus", 2, group="hyperv")
        imp.CONF.set_override("writer_port", 6677, group="hyperv")
        imp.CONF.set_override("default_vm_path", "C:\\VMs", group="hyperv")

    def test_platform(self):
        self.assertEqual("hyperv", self.provider.platform)

    def test_get_connection_info_schema(self):
        schema = self.provider.get_connection_info_schema()
        self.assertIn("host", schema["properties"])
        self.assertIn("username", schema["properties"])
        self.assertIn("password", schema["properties"])
        self.assertEqual(
            schema["required"], ["host", "username", "password"])

    def test_get_target_environment_schema(self):
        schema = self.provider.get_target_environment_schema()
        self.assertIn("vm_path", schema["properties"])
        self.assertIn("default_switch", schema["properties"])
        self.assertIn("vm_generation", schema["properties"])
        self.assertIn("network_map", schema["properties"])

    @mock.patch.object(imp.HyperVImportProvider, "_get_winrm_session")
    def test_validate_connection(self, mock_get_session):
        mock_session = mock.MagicMock()
        mock_get_session.return_value = mock_session
        result = mock.MagicMock()
        result.status_code = 0
        result.std_out = b'{"Name": "HV01"}'
        mock_session.run_ps.return_value = result

        connection_info = {
            "host": "hv01", "username": "Administrator", "password": "pwd"}
        self.provider.validate_connection(None, connection_info)

        mock_get_session.assert_called_once_with(connection_info)
        mock_session.run_ps.assert_called_once()

    def test_run_ps_raises_on_failure(self):
        mock_session = mock.MagicMock()
        result = mock.MagicMock()
        result.status_code = 1
        result.std_err = b"boom"
        mock_session.run_ps.return_value = result

        self.assertRaises(
            exception.CoriolisException,
            self.provider._run_ps, mock_session, "Get-VM")

    @mock.patch.object(imp.HyperVImportProvider, "_get_winrm_session")
    def test_get_networks(self, mock_get_session):
        mock_session = mock.MagicMock()
        mock_get_session.return_value = mock_session
        result = mock.MagicMock()
        result.status_code = 0
        result.std_out = (
            b'[{"Id": "s-1", "Name": "External"}, '
            b'{"Id": "s-2", "Name": "Internal"}]')
        mock_session.run_ps.return_value = result

        nets = self.provider.get_networks(None, {"host": "hv"}, None)
        self.assertEqual(2, len(nets))
        self.assertEqual("External", nets[0]["name"])
        self.assertEqual("s-1", nets[0]["id"])

    @mock.patch.object(imp.HyperVImportProvider, "_get_winrm_session")
    def test_deploy_replica_disks_creates_vhdx(self, mock_get_session):
        mock_session = mock.MagicMock()
        mock_get_session.return_value = mock_session
        # get_storage returns no usable backends -> falls back to vm_path
        empty = mock.MagicMock()
        empty.status_code = 0
        empty.std_out = b''
        mock_session.run_ps.return_value = empty

        export_info = {
            "devices": {
                "disks": [
                    {"id": "disk-1", "size_bytes": 1024,
                     "storage_backend_identifier": "datastore1"},
                ]
            }
        }
        volumes = self.provider.deploy_replica_disks(
            None, {"host": "hv"}, {}, "myvm", export_info, [])

        self.assertEqual(1, len(volumes))
        self.assertEqual("disk-1", volumes[0]["disk_id"])
        self.assertTrue(volumes[0]["volume_id"].endswith(".vhdx"))
        self.assertEqual(1024, volumes[0]["size_bytes"])

    def test_get_optimal_flavor_is_none(self):
        self.assertIsNone(
            self.provider.get_optimal_flavor(None, {}, {}, {}))

    @mock.patch.object(imp.HyperVImportProvider, "_get_winrm_session")
    def test_validate_requires_minion_template(self, mock_get_session):
        mock_session = mock.MagicMock()
        mock_get_session.return_value = mock_session
        ok = mock.MagicMock()
        ok.status_code = 0
        ok.std_out = b''
        mock_session.run_ps.return_value = ok
        imp.CONF.set_override(
            "minion_template_vhdx", None, group="hyperv")

        self.assertRaises(
            exception.InvalidInput,
            self.provider.validate_replica_import_input,
            None, {"host": "hv"}, {"default_switch": None}, {})

    @mock.patch.object(imp.HyperVImportProvider, "_get_vm_ip")
    @mock.patch.object(imp.HyperVImportProvider, "_wait_for_vm_state")
    @mock.patch.object(imp.HyperVImportProvider, "_get_winrm_session")
    def test_deploy_os_morphing_resources(
            self, mock_get_session, mock_wait, mock_ip):
        mock_session = mock.MagicMock()
        mock_get_session.return_value = mock_session
        mock_ip.return_value = "10.0.0.9"

        def fake_run_ps(session, script):
            if "Get-VMHardDiskDrive" in script and "ConvertTo-Json" in script:
                return '[{"Path": "C:\\\\VMs\\\\boot.vhdx"}]'
            if ".State" in script:
                return "Off"
            return ""
        self.provider._run_ps = mock.MagicMock(side_effect=fake_run_ps)
        imp.CONF.set_override(
            "minion_template_vhdx", "C:\\templates\\ubuntu.vhdx",
            group="hyperv")

        instance_deployment_info = {
            "vm_name": "myvm",
            "os_type": "linux",
            "disk_paths": ["C:\\VMs\\boot.vhdx"],
            "boot_disk_path": "C:\\VMs\\boot.vhdx",
            "nics_info": [{"name": "nic-0", "mac_address": "00:11"}],
        }
        result = self.provider.deploy_os_morphing_resources(
            None, {"host": "hv"}, {"default_switch": "External"},
            instance_deployment_info)

        self.assertIn("os_morphing_resources", result)
        self.assertIn("osmorphing_connection_info", result)
        conn = result["osmorphing_connection_info"]
        self.assertEqual("10.0.0.9", conn["ip"])
        self.assertEqual(22, conn["port"])
        self.assertEqual("linux", result["osmorphing_info"]["os_type"])
        self.assertEqual(
            "myvm", result["os_morphing_resources"]["target_vm_name"])
        self.assertTrue(
            result["os_morphing_resources"]["minion_vm_name"].startswith(
                "coriolis-osmorphing-"))

    @mock.patch.object(imp.HyperVImportProvider, "_stop_vm")
    @mock.patch.object(imp.HyperVImportProvider, "_get_winrm_session")
    def test_delete_os_morphing_resources_reattaches(
            self, mock_get_session, mock_stop):
        mock_session = mock.MagicMock()
        mock_get_session.return_value = mock_session
        self.provider._run_ps = mock.MagicMock(return_value="")
        self.provider._attach_disk_to_vm = mock.MagicMock()
        self.provider._detach_disk_from_vm = mock.MagicMock()
        self.provider._delete_vm = mock.MagicMock()

        os_morphing_resources = {
            "minion_vm_name": "coriolis-osmorphing-abc",
            "minion_boot_vhdx": "C:\\VMs\\minion-boot.vhdx",
            "target_vm_name": "myvm",
            "boot_disk_path": "C:\\VMs\\boot.vhdx",
            "disk_paths": ["C:\\VMs\\boot.vhdx", "C:\\VMs\\data.vhdx"],
        }
        self.provider.delete_os_morphing_resources(
            None, {"host": "hv"}, {}, os_morphing_resources)

        self.assertEqual(2, self.provider._attach_disk_to_vm.call_count)
        self.provider._attach_disk_to_vm.assert_any_call(
            mock_session, "myvm", "C:\\VMs\\boot.vhdx")
        self.provider._delete_vm.assert_called_once_with(
            mock_session, "coriolis-osmorphing-abc",
            delete_boot_vhdx="C:\\VMs\\minion-boot.vhdx")

    def test_delete_os_morphing_resources_noop_on_empty(self):
        with mock.patch.object(
                imp.HyperVImportProvider, "_get_winrm_session") as m:
            self.provider.delete_os_morphing_resources(
                None, {"host": "hv"}, {}, None)
            m.assert_not_called()

    def test_get_os_morphing_tools_linux(self):
        from coriolis import constants
        tools = self.provider.get_os_morphing_tools(
            constants.OS_TYPE_LINUX, {})
        self.assertTrue(len(tools) > 0)

    def test_get_os_morphing_tools_unknown(self):
        self.assertEqual(
            [], self.provider.get_os_morphing_tools("solaris", {}))

    def test_deploy_replica_instance_default(self):
        mock_session = mock.MagicMock()
        self.provider._run_ps = mock.MagicMock()
        self.provider._get_default_switch = mock.MagicMock(return_value="Default Switch")
        self.provider._get_vm_path = mock.MagicMock(return_value="C:\\VMs")
        self.provider._attach_disk_to_vm = mock.MagicMock()

        export_info = {
            "memory_mb": 2048,
            "num_cpu": 2,
            "firmware_type": "BIOS",
            "devices": {
                "nics": [
                    {
                        "name": "nic1",
                        "mac_address": "00:11:22:33:44:55",
                        "network_name": "net1",
                    },
                    {
                        "name": "nic2",
                        "mac_address": "aa:bb:cc:dd:ee:ff",
                        "network_name": "net2",
                    }
                ]
            }
        }
        target_environment = {
            "default_switch": "SwitchA",
            "network_map": {"net1": "SwitchA", "net2": "SwitchB"},
        }
        volumes_info = [{"volume_id": "vol1.vhdx"}]

        with mock.patch.object(self.provider, "_get_winrm_session", return_value=mock_session):
            res = self.provider.deploy_replica_instance(
                None, {"host": "hv"}, target_environment, "test-vm",
                export_info, volumes_info, clone_disks=False)

        self.assertEqual("test-vm", res["instance_deployment_info"]["vm_id"])
        
        ps_calls = [c[1][1] for c in self.provider._run_ps.mock_calls]
        self.assertTrue(any("Connect-VMNetworkAdapter -VMName 'test-vm' -SwitchName 'SwitchA'" in call for call in ps_calls))
        self.assertTrue(any("Add-VMNetworkAdapter -VMName 'test-vm' -SwitchName 'SwitchB'" in call for call in ps_calls))
        self.assertFalse(any("Set-VMNetworkAdapter" in call for call in ps_calls))
        self.assertFalse(any("-MacAddress" in call for call in ps_calls))

    def test_deploy_replica_instance_preserve_mac(self):
        mock_session = mock.MagicMock()
        self.provider._run_ps = mock.MagicMock()
        self.provider._get_default_switch = mock.MagicMock(return_value="Default Switch")
        self.provider._get_vm_path = mock.MagicMock(return_value="C:\\VMs")
        self.provider._attach_disk_to_vm = mock.MagicMock()

        export_info = {
            "memory_mb": 2048,
            "num_cpu": 2,
            "firmware_type": "BIOS",
            "devices": {
                "nics": [
                    {
                        "name": "nic1",
                        "mac_address": "00:11:22:33:44:55",
                        "network_name": "net1",
                    },
                    {
                        "name": "nic2",
                        "mac_address": "aa:bb:cc:dd:ee:ff",
                        "network_name": "net2",
                    }
                ]
            }
        }
        target_environment = {
            "default_switch": "SwitchA",
            "network_map": {"net1": "SwitchA", "net2": "SwitchB"},
            "preserve_mac_addresses": True,
        }
        volumes_info = [{"volume_id": "vol1.vhdx"}]

        with mock.patch.object(self.provider, "_get_winrm_session", return_value=mock_session):
            res = self.provider.deploy_replica_instance(
                None, {"host": "hv"}, target_environment, "test-vm",
                export_info, volumes_info, clone_disks=False)

        self.assertEqual("test-vm", res["instance_deployment_info"]["vm_id"])
        
        ps_calls = [c[1][1] for c in self.provider._run_ps.mock_calls]
        self.assertTrue(any("Connect-VMNetworkAdapter -VMName 'test-vm' -SwitchName 'SwitchA'" in call for call in ps_calls))
        self.assertTrue(any("Set-VMNetworkAdapter -VMName 'test-vm' -MacAddress '001122334455' -StaticMacAddress $true" in call for call in ps_calls))
        self.assertTrue(any("Add-VMNetworkAdapter -VMName 'test-vm' -SwitchName 'SwitchB' -MacAddress 'aabbccddeeff' -StaticMacAddress $true" in call for call in ps_calls))

