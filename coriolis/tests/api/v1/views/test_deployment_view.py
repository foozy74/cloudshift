# Copyright 2026 Cloudbase Solutions Srl
# All Rights Reserved.

from unittest import mock

from coriolis.api.v1.views import deployment_view
from coriolis.api.v1.views import transfer_tasks_execution_view as view
from coriolis.api.v1.views import utils as view_utils
from coriolis.tests import test_base


class DeploymentViewTestCase(test_base.CoriolisApiViewsTestCase):
    """Test suite for the Coriolis api v1 deployment views."""

    def setUp(self):
        super(DeploymentViewTestCase, self).setUp()
        self._format_fun = deployment_view._format_deployment

    @mock.patch.object(view, 'format_transfer_tasks_execution')
    @mock.patch.object(view_utils, 'format_opt')
    def test_format_deployment(self, mock_format_opt,
                               mock_format_transfer_tasks_execution):
        mock_format_opt.return_value = {
            "executions": [{'id': 'mock_id1'}],
            "mock_key": "mock_value",
        }
        mock_format_transfer_tasks_execution.return_value = {
            "tasks": ["mock_task"]}

        result = deployment_view._format_deployment(
            mock.sentinel.deployment, mock.sentinel.keys)

        mock_format_opt.assert_called_once_with(
            mock.sentinel.deployment, mock.sentinel.keys)
        self.assertEqual(
            {"mock_key": "mock_value", "tasks": ["mock_task"]}, result)

    @mock.patch.object(view_utils, 'format_opt')
    def test_format_deployment_redacts_task_info(self, mock_format_opt):
        mock_format_opt.return_value = {
            "info": {
                "instance1": {
                    "osmorphing_connection_info": {
                        "ip": "10.0.0.5",
                        "password": "engine_secret",
                        "pkey": "private_key_data"}}}
        }

        expected_result = {
            "info": {
                "instance1": {
                    "osmorphing_connection_info": {
                        "ip": "10.0.0.5",
                        "password": "***",
                        "pkey": "***"}}}
        }

        result = deployment_view._format_deployment(
            mock.sentinel.deployment, mock.sentinel.keys)

        self.assertEqual(expected_result, result)

    def test_single(self):
        fun = getattr(deployment_view, 'single')
        self._single_view_test(fun, 'deployment')

    def test_collection(self):
        fun = getattr(deployment_view, 'collection')
        self._collection_view_test(fun, 'deployments')
