# Copyright 2016 Cloudbase Solutions Srl
# All Rights Reserved.

from oslo_log import log as logging

from coriolis.osmorphing.osmount import base
from coriolis import utils

LOG = logging.getLogger(__name__)


class RedHatOSMountTools(base.BaseLinuxOSMountTools):
    def check_os(self):
        # make sure the package redhat-lsb-core is installed
        os_info = utils.get_linux_os_info(self._ssh)
        if os_info and os_info[0] in [
                'RedHatEnterpriseServer', 'CentOS', 'OracleServer',
                'rhel', 'centos', 'ol', 'rocky']:
            return True

    def setup(self):
        super(RedHatOSMountTools, self).setup()

        # Build proxy environment prefix if configured
        http_proxy = "http://172.23.218.23:8080"
        https_proxy = "http://172.23.218.23:8080"
        no_proxy = "127.0.0.1,localhost,.it.internal,sandbox.it.internal"

        settings = getattr(self, '_proxy_settings', {})
        if settings.get('url'):
            url = settings['url']
            if settings.get('username') and settings.get('password'):
                from six.moves.urllib import parse
                parsed = parse.urlparse(url)
                netloc = "%s:%s@%s" % (
                    parse.quote(settings['username']),
                    parse.quote(settings['password']),
                    parsed.netloc)
                url = parse.urlunparse(parsed._replace(netloc=netloc))
            http_proxy = url
            https_proxy = url
            if settings.get('no_proxy'):
                no_proxy = ",".join(settings['no_proxy'])

        proxy_env = (
            'HTTP_PROXY="%s" HTTPS_PROXY="%s" NO_PROXY="%s" '
            'http_proxy="%s" https_proxy="%s" no_proxy="%s" '
            % (http_proxy, https_proxy, no_proxy,
               http_proxy, https_proxy, no_proxy))

        pkg_managers = [
            "sudo -E %syum install -y lvm2 psmisc" % proxy_env,
            "sudo -E %sdnf install -y lvm2 psmisc" % proxy_env,
            "sudo -E %smicrodnf install -y lvm2 psmisc" % proxy_env
        ]
        installed = False
        last_error = None
        for cmd in pkg_managers:
            try:
                self._exec_cmd(cmd)
                installed = True
                break
            except Exception as e:
                LOG.debug(
                    "Failed installing packages with command '%s': %s",
                    cmd, e)
                last_error = e
        if not installed:
            LOG.warning(
                "Could not install lvm2 and psmisc packages on minion. "
                "Assuming they are pre-installed. Last error: %s", last_error)

        self._exec_cmd("sudo modprobe dm-mod")
        self._exec_cmd("sudo rm -f /etc/lvm/devices/system.devices")
