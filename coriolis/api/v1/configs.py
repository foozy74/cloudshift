# Copyright 2026 The Solution
# All Rights Reserved.

import os

from webob import exc

from coriolis.api import wsgi as api_wsgi

ALLOWED_CONFIGS = ["coriolis.conf", "api-paste.ini", "policy.yaml", "users.yaml"]
CONFIG_DIR = "/etc/coriolis"

SLUG_MAP = {
    "coriolis": "coriolis.conf",
    "coriolis.conf": "coriolis.conf",
    "api-paste": "api-paste.ini",
    "api-paste.ini": "api-paste.ini",
    "policy": "policy.yaml",
    "policy.yaml": "policy.yaml",
    "users": "users.yaml",
    "users.yaml": "users.yaml",
}


class ConfigsController(api_wsgi.Controller):
    def index(self, req):
        configs = []
        for name in ALLOWED_CONFIGS:
            path = os.path.join(CONFIG_DIR, name)
            exists = os.path.exists(path)
            configs.append({"id": name, "name": name, "exists": exists})
        return {"configs": configs}

    def show(self, req, id):
        filename = SLUG_MAP.get(id, id)
        if filename not in ALLOWED_CONFIGS:
            raise exc.HTTPBadRequest(explanation=f"Invalid config file: {id}")

        path = os.path.join(CONFIG_DIR, filename)
        if not os.path.exists(path):
            raise exc.HTTPNotFound(explanation=f"Config file not found: {id}")

        try:
            with open(path, 'r') as f:
                content = f.read()
        except Exception as e:
            raise exc.HTTPInternalServerError(explanation=str(e))

        return {"config": {"id": id, "name": id, "content": content}}

    def update(self, req, id, body):
        filename = SLUG_MAP.get(id, id)
        if filename not in ALLOWED_CONFIGS:
            raise exc.HTTPBadRequest(explanation=f"Invalid config file: {id}")

        path = os.path.join(CONFIG_DIR, filename)

        config_body = body.get("config", {})
        content = config_body.get("content")
        if content is None:
            raise exc.HTTPBadRequest(
                explanation="Missing 'content' field in request body")

        try:
            with open(path, 'w') as f:
                f.write(content)
        except Exception as e:
            raise exc.HTTPInternalServerError(explanation=str(e))

        return {"config": {"id": id, "name": id, "content": content}}


def create_resource():
    return api_wsgi.Resource(ConfigsController())
