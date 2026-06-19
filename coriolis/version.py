# Copyright 2024 CloudShift / Coriolis
# All Rights Reserved.

import pbr.version

version_info = pbr.version.VersionInfo('cloudshift')


def version_string():
    try:
        ver = version_info.version_string()
        # If PBR defaults to 0.0.1 due to missing git tags,
        # fallback to our current release version.
        if ver in ('0.0.1', '0.0.1.dev1'):
            return '1.3.0'
        return ver
    except Exception:
        return '1.3.0'
