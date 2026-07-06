# Copyright 2026 Thesolution.at
# All Rights Reserved.

from unittest import mock

from oslo_config import cfg

from coriolis.providers.vmware import imp
from coriolis.tests import test_base

CONF = cfg.CONF


class VMwareVSphereImportProviderTestCase(test_base.CoriolisBaseTestCase):
    """Test suite for VMwareVSphereImportProvider."""

    def setUp(self):
        super(VMwareVSphereImportProviderTestCase, self).setUp()
        self.mock_event_manager = mock.MagicMock()
        self.provider = imp.VMwareVSphereImportProvider(
            self.mock_event_manager)

        # Mock config options
        imp.CONF.set_override(
            "minion_template_name", "test-template", group="vmware_import")
        imp.CONF.set_override("minion_memory_mb", 4096, group="vmware_import")
        imp.CONF.set_override("minion_vcpus", 2, group="vmware_import")
        imp.CONF.set_override("writer_port", 6677, group="vmware_import")

    def test_get_connection_info_schema(self):
        schema = self.provider.get_connection_info_schema()
        self.assertIn("host", schema["properties"])
        self.assertIn("username", schema["properties"])
        self.assertEqual(
            schema["required"], ["host", "username", "password"])

    @mock.patch("pyVim.connect.Disconnect")
    @mock.patch.object(imp.VMwareVSphereImportProvider, "_get_vcenter_session")
    def test_validate_connection(self, mock_get_session, mock_disconnect):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_content = mock_si.RetrieveContent.return_value
        mock_content.about.fullName = "VMware vCenter Server 7.0.3"

        connection_info = {
            "host": "vcenter",
            "username": "admin",
            "password": "pwd"}
        self.provider.validate_connection(None, connection_info)

        mock_get_session.assert_called_once_with(connection_info)
        mock_si.RetrieveContent.assert_called_once()
        mock_disconnect.assert_called_once_with(mock_si)

    def test_get_target_environment_schema(self):
        schema = self.provider.get_target_environment_schema()
        self.assertIn("datacenter", schema["properties"])
        self.assertIn("cluster", schema["properties"])
        self.assertIn("datastore", schema["properties"])
        self.assertEqual(
            schema["required"], ["datacenter", "cluster", "datastore"])

    @mock.patch.object(imp.VMwareVSphereImportProvider, "_get_vcenter_session")
    def test_get_target_environment_options(self, mock_get_session):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_content = mock_si.RetrieveContent.return_value
        mock_view = mock_content.viewManager.CreateContainerView.return_value

        mock_dc = mock.MagicMock()
        mock_dc.name = "Datacenter"

        mock_cluster = mock.MagicMock()
        mock_cluster.name = "Cluster"

        mock_ds = mock.MagicMock()
        mock_ds.name = "datastore1"
        mock_ds.summary.accessible = True

        mock_view.view = [mock_dc, mock_cluster, mock_ds]

        options = self.provider.get_target_environment_options(None, {})
        self.assertEqual(len(options), 3)
        self.assertEqual(options[0]["name"], "datacenter")
        self.assertEqual(options[1]["name"], "cluster")
        self.assertEqual(options[2]["name"], "datastore")

    @mock.patch.object(imp.VMwareVSphereImportProvider, "_get_vcenter_session")
    def test_get_networks(self, mock_get_session):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_content = mock_si.RetrieveContent.return_value
        mock_view = mock_content.viewManager.CreateContainerView.return_value

        mock_net = mock.MagicMock()
        mock_net.name = "VM Network"
        mock_view.view = [mock_net]

        networks = self.provider.get_networks(None, {}, {})
        self.assertEqual(len(networks), 1)
        self.assertEqual(networks[0]["id"], "VM Network")

    @mock.patch.object(imp.VMwareVSphereImportProvider, "_get_vcenter_session")
    def test_get_storage(self, mock_get_session):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_content = mock_si.RetrieveContent.return_value
        mock_view = mock_content.viewManager.CreateContainerView.return_value

        mock_ds = mock.MagicMock()
        mock_ds.name = "datastore1"
        mock_ds.summary.capacity = 2000
        mock_ds.summary.freeSpace = 1200
        mock_view.view = [mock_ds]

        target_env = {"datastore": "datastore1"}
        storage = self.provider.get_storage(None, {}, target_env)
        self.assertEqual(storage["total_bytes"], 2000)
        self.assertEqual(storage["available_bytes"], 1200)

    def test_get_optimal_flavor(self):
        export_info = {"vcpus": 4, "memory_mb": 8192}
        flavor = self.provider.get_optimal_flavor(
            None, {}, "test-vm", export_info)
        self.assertEqual(flavor["vcpus"], 4)
        self.assertEqual(flavor["memory_mb"], 8192)

    @mock.patch.object(imp.VMwareVSphereImportProvider, "_get_vcenter_session")
    def test_deploy_replica_disks(self, mock_get_session):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        export_info = {
            "devices": {
                "disks": [
                    {"id": "disk-1", "size_bytes": 1024}
                ]
            }
        }
        target_env = {"datastore": "datastore1"}
        volumes = self.provider.deploy_replica_disks(
            None, {}, target_env, "test-vm", export_info, [])

        self.assertEqual(len(volumes), 1)
        self.assertEqual(
            volumes[0]["volume_id"], "[datastore1] test-vm/disk-0.vmdk")

    @mock.patch.object(imp.VMwareVSphereImportProvider, "_find_vm_by_name")
    @mock.patch.object(imp.VMwareVSphereImportProvider, "_get_vcenter_session")
    def test_deploy_replica_target_resources(
            self, mock_get_session, mock_find_vm):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_template = mock.MagicMock()
        mock_template.name = "test-template"
        mock_find_vm.return_value = mock_template

        volumes_info = [{"volume_id": "[ds1] vm/disk-0.vmdk"}]
        res = self.provider.deploy_replica_target_resources(
            None, {}, {"datastore": "ds1"}, volumes_info)

        self.assertIn("minion_vm_name", res["migr_resources"])

    @mock.patch.object(imp.VMwareVSphereImportProvider, "_wait_for_task")
    @mock.patch.object(imp.VMwareVSphereImportProvider, "_find_vm_by_name")
    @mock.patch.object(imp.VMwareVSphereImportProvider, "_get_vcenter_session")
    def test_delete_replica_target_resources(
            self, mock_get_session, mock_find_vm, mock_wait_task):
        mock_si = mock.MagicMock()
        mock_get_session.return_value = mock_si

        mock_minion = mock.MagicMock()
        mock_minion.runtime.powerState = "poweredOn"
        mock_find_vm.return_value = mock_minion

        migr_resources = {"minion_vm_name": "minion-1"}
        self.provider.delete_replica_target_resources(
            None, {}, {}, migr_resources)

        mock_minion.PowerOffVM_Task.assert_called_once()
        mock_minion.Destroy_Task.assert_called_once()
