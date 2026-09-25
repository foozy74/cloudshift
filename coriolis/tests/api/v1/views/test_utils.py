# Copyright 2023 Cloudbase Solutions Srl
# All Rights Reserved.

from coriolis.api.v1.views import utils as view_utils
from coriolis.tests import test_base


class ViewUtilsTestCase(test_base.CoriolisBaseTestCase):
    """Test suite for the Coriolis api v1 views."""

    def test_format_opt(self):
        mock_option = {"mock_key_1": "value_1", "mock_key_2": "value_2"}
        mock_keys = {"mock_key_1"}

        expected_result = {"mock_key_1": "value_1"}

        result = view_utils.format_opt(mock_option, mock_keys)

        self.assertEqual(
            expected_result,
            result
        )

    def test_format_opt_key_not_in_options(self):
        mock_option = {"mock_key_1": "value_1", "mock_key_2": "value_2"}
        mock_keys = {"mock_key_3"}

        expected_result = {}

        result = view_utils.format_opt(mock_option, mock_keys)

        self.assertEqual(
            expected_result,
            result
        )

    def test_format_opt_keys_none(self):
        mock_option = {"mock_key_1": "value_1", "mock_key_2": "value_2"}
        mock_keys = None

        expected_result = mock_option

        result = view_utils.format_opt(mock_option, mock_keys)

        self.assertEqual(
            expected_result,
            result
        )

    def test_redact_sensitive_info(self):
        task_info = {
            "instance_name": "web01",
            "target_resources_connection_info": {
                "ip": "10.0.0.5",
                "username": "root",
                "password": "engine_secret",
                "pkey": "-----BEGIN RSA PRIVATE KEY-----",
            },
            "osmorphing_connection_info": {
                "minion_password": "minion_secret",
                "certificates": {"client_key": "key_data"},
            },
            "volumes_info": [
                {"disk_id": "disk1", "private_key": "vol_secret"}],
        }

        expected_result = {
            "instance_name": "web01",
            "target_resources_connection_info": {
                "ip": "10.0.0.5",
                "username": "root",
                "password": "***",
                "pkey": "***",
            },
            "osmorphing_connection_info": {
                "minion_password": "***",
                "certificates": {"client_key": "***"},
            },
            "volumes_info": [
                {"disk_id": "disk1", "private_key": "***"}],
        }

        result = view_utils.redact_sensitive_info(task_info)

        self.assertEqual(expected_result, result)

    def test_redact_sensitive_info_does_not_mutate_input(self):
        task_info = {"conn": {"pkey": "secret"}}

        view_utils.redact_sensitive_info(task_info)

        self.assertEqual({"conn": {"pkey": "secret"}}, task_info)

    def test_redact_sensitive_info_keeps_empty_values(self):
        task_info = {"conn": {"pkey": None, "password": ""}}

        result = view_utils.redact_sensitive_info(task_info)

        self.assertEqual(task_info, result)

    def test_redact_sensitive_info_non_container(self):
        self.assertEqual("value", view_utils.redact_sensitive_info("value"))
        self.assertIsNone(view_utils.redact_sensitive_info(None))
