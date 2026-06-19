# Copyright 2024 Cloudbase Solutions Srl
# All Rights Reserved.

from unittest import mock

from coriolis.osmorphing.osmount import redhat
from coriolis.tests import test_base


class BaseRedHatOSMountToolsTestCase(test_base.CoriolisBaseTestCase):
    """Test suite for the RedHatOSMountTools class."""

    @mock.patch.object(redhat.base.BaseSSHOSMountTools, '_connect')
    def setUp(self, mock_connect):
        super(BaseRedHatOSMountToolsTestCase, self).setUp()
        self.ssh = mock.MagicMock()

        self.tools = redhat.RedHatOSMountTools(
            self.ssh, mock.sentinel.event_manager,
            mock.sentinel.ignore_devices,
            mock.sentinel.operation_timeout)

        mock_connect.assert_called_once_with()

        self.tools._ssh = self.ssh

    @mock.patch.object(redhat.utils, 'get_linux_os_info')
    def test_check_os(self, mock_get_linux_os_info):
        mock_get_linux_os_info.return_value = ['RedHatEnterpriseServer']

        result = self.tools.check_os()
        self.assertTrue(result)

    @mock.patch.object(redhat.base.BaseSSHOSMountTools, '_exec_cmd')
    @mock.patch.object(redhat.base.BaseSSHOSMountTools, 'setup')
    def test_setup_yum_success(self, mock_setup, mock_exec_cmd):
        result = self.tools.setup()
        self.assertIsNone(result)

        proxy_env = (
            'HTTP_PROXY="http://172.23.218.23:8080" '
            'HTTPS_PROXY="http://172.23.218.23:8080" '
            'NO_PROXY="127.0.0.1,localhost,.it.internal,sandbox.it.internal" '
            'http_proxy="http://172.23.218.23:8080" '
            'https_proxy="http://172.23.218.23:8080" '
            'no_proxy="127.0.0.1,localhost,.it.internal,sandbox.it.internal" '
        )
        mock_setup.assert_called_once_with()
        mock_exec_cmd.assert_has_calls([
            mock.call("sudo -E %syum install -y lvm2 psmisc" % proxy_env),
            mock.call("sudo modprobe dm-mod"),
            mock.call("sudo rm -f /etc/lvm/devices/system.devices")
        ])

    @mock.patch.object(redhat.base.BaseSSHOSMountTools, '_exec_cmd')
    @mock.patch.object(redhat.base.BaseSSHOSMountTools, 'setup')
    def test_setup_yum_fails_dnf_success(self, mock_setup, mock_exec_cmd):
        def exec_side_effect(cmd):
            if "yum" in cmd:
                raise Exception("yum not found")
            return None
        mock_exec_cmd.side_effect = exec_side_effect

        result = self.tools.setup()
        self.assertIsNone(result)

        proxy_env = (
            'HTTP_PROXY="http://172.23.218.23:8080" '
            'HTTPS_PROXY="http://172.23.218.23:8080" '
            'NO_PROXY="127.0.0.1,localhost,.it.internal,sandbox.it.internal" '
            'http_proxy="http://172.23.218.23:8080" '
            'https_proxy="http://172.23.218.23:8080" '
            'no_proxy="127.0.0.1,localhost,.it.internal,sandbox.it.internal" '
        )
        mock_setup.assert_called_once_with()
        mock_exec_cmd.assert_has_calls([
            mock.call("sudo -E %syum install -y lvm2 psmisc" % proxy_env),
            mock.call("sudo -E %sdnf install -y lvm2 psmisc" % proxy_env),
            mock.call("sudo modprobe dm-mod"),
            mock.call("sudo rm -f /etc/lvm/devices/system.devices")
        ])

    @mock.patch.object(redhat.base.BaseSSHOSMountTools, '_exec_cmd')
    @mock.patch.object(redhat.base.BaseSSHOSMountTools, 'setup')
    def test_setup_all_fail(self, mock_setup, mock_exec_cmd):
        def exec_side_effect(cmd):
            if "install" in cmd:
                raise Exception("not found")
            return None
        mock_exec_cmd.side_effect = exec_side_effect

        result = self.tools.setup()
        self.assertIsNone(result)

        proxy_env = (
            'HTTP_PROXY="http://172.23.218.23:8080" '
            'HTTPS_PROXY="http://172.23.218.23:8080" '
            'NO_PROXY="127.0.0.1,localhost,.it.internal,sandbox.it.internal" '
            'http_proxy="http://172.23.218.23:8080" '
            'https_proxy="http://172.23.218.23:8080" '
            'no_proxy="127.0.0.1,localhost,.it.internal,sandbox.it.internal" '
        )
        mock_setup.assert_called_once_with()
        mock_exec_cmd.assert_has_calls([
            mock.call("sudo -E %syum install -y lvm2 psmisc" % proxy_env),
            mock.call("sudo -E %sdnf install -y lvm2 psmisc" % proxy_env),
            mock.call("sudo -E %smicrodnf install -y lvm2 psmisc" % proxy_env),
            mock.call("sudo modprobe dm-mod"),
            mock.call("sudo rm -f /etc/lvm/devices/system.devices")
        ])

    @mock.patch.object(redhat.base.BaseSSHOSMountTools, '_exec_cmd')
    @mock.patch.object(redhat.base.BaseSSHOSMountTools, 'setup')
    def test_setup_dynamic_proxy(self, mock_setup, mock_exec_cmd):
        self.tools._proxy_settings = {
            'url': 'http://proxy.example.com:3128',
            'no_proxy': ['localhost', '127.0.0.1']
        }
        result = self.tools.setup()
        self.assertIsNone(result)

        expected_proxy = (
            'HTTP_PROXY="http://proxy.example.com:3128" '
            'HTTPS_PROXY="http://proxy.example.com:3128" '
            'NO_PROXY="localhost,127.0.0.1" '
            'http_proxy="http://proxy.example.com:3128" '
            'https_proxy="http://proxy.example.com:3128" '
            'no_proxy="localhost,127.0.0.1" '
        )
        mock_setup.assert_called_once_with()
        mock_exec_cmd.assert_has_calls([
            mock.call("sudo -E %syum install -y lvm2 psmisc" % expected_proxy),
            mock.call("sudo modprobe dm-mod"),
            mock.call("sudo rm -f /etc/lvm/devices/system.devices")
        ])

    @mock.patch.object(redhat.base.BaseSSHOSMountTools, '_exec_cmd')
    @mock.patch.object(redhat.utils, 'restart_service')
    def test__allow_ssh_env_vars(self, mock_restart_service, mock_exec_cmd):
        result = self.tools._allow_ssh_env_vars()
        self.assertTrue(result)

        mock_exec_cmd.assert_called_once_with(
            'sudo sed -i -e "\$aAcceptEnv *" /etc/ssh/sshd_config')
        mock_restart_service.assert_called_once_with(self.ssh, "sshd")
