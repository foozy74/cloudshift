# Copyright 2016 Cloudbase Solutions Srl
# All Rights Reserved.

import coriolis  # noqa: F401
import sys

from oslo_config import cfg

from coriolis.db import api as db_api
from coriolis import utils

from coriolis import version

CONF = cfg.CONF


def main():
    CONF(sys.argv[1:], project='coriolis',
         version=version.version_string())
    utils.setup_logging()

    db_api.db_sync(db_api.get_engine())


if __name__ == "__main__":
    main()
