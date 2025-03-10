# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
import os
import unittest  # pylint: disable=unused-import

from azure.cli.testsdk import (ResourceGroupPreparer)
from azure.cli.testsdk.decorators import serial_test
from azext_containerapp.tests.latest.common import (
    ContainerappComposePreviewScenarioTest,  # pylint: disable=unused-import
    write_test_file,
    clean_up_test_file,
    TEST_DIR, TEST_LOCATION)

from .utils import prepare_containerapp_env_for_app_e2e_tests


class ContainerappComposePreviewResourceSettingsScenarioTest(ContainerappComposePreviewScenarioTest):
    @serial_test()
    @ResourceGroupPreparer(name_prefix='cli_test_containerapp_preview', location='eastus')
    def test_containerapp_compose_create_with_resources_from_service_cpus(self, resource_group):
        self.cmd('configure --defaults location={}'.format(TEST_LOCATION))
        compose_text = f"""
services:
  foo:
    image: mcr.microsoft.com/azuredocs/aks-helloworld:v1
    cpus: 1.25
    expose:
      - "3000"
"""
        compose_file_name = f"{self._testMethodName}_compose.yml"
        write_test_file(compose_file_name, compose_text)
        env = prepare_containerapp_env_for_app_e2e_tests(self)

        self.kwargs.update({
            'environment': env,
            'compose': compose_file_name,
        })

        command_string = 'containerapp compose create'
        command_string += ' --compose-file-path {compose}'
        command_string += ' --resource-group {rg}'
        command_string += ' --environment {environment}'
        self.cmd(command_string, checks=[
            self.check(f'[?name==`foo`].properties.template.containers[0].resources.cpu', [1.25]),
        ])
        self.cmd(f'containerapp delete -n foo -g {resource_group} --yes', expect_failure=False)

        clean_up_test_file(compose_file_name)

    @serial_test()
    @ResourceGroupPreparer(name_prefix='cli_test_containerapp_preview', location='eastus')
    def test_containerapp_compose_create_with_resources_from_deploy_cpu(self, resource_group):
        self.cmd('configure --defaults location={}'.format(TEST_LOCATION))
        app = self.create_random_name(prefix='composewithres', length=24)
        compose_text = f"""
services:
  foo:
    image: mcr.microsoft.com/azuredocs/aks-helloworld:v1
    deploy:
      resources:
        reservations:
          cpus: 1.25
    expose:
      - "3000"
"""
        compose_file_name = f"{self._testMethodName}_compose.yml"
        write_test_file(compose_file_name, compose_text)
        env = prepare_containerapp_env_for_app_e2e_tests(self)

        self.kwargs.update({
            'environment': env,
            'compose': compose_file_name,
        })

        command_string = 'containerapp compose create'
        command_string += ' --compose-file-path {compose}'
        command_string += ' --resource-group {rg}'
        command_string += ' --environment {environment}'
        self.cmd(command_string, checks=[
            self.check(f'[?name==`foo`].properties.template.containers[0].resources.cpu', [1.25]),
        ])
        self.cmd(f'containerapp delete -n foo -g {resource_group} --yes', expect_failure=False)

        clean_up_test_file(compose_file_name)

    @serial_test()
    @ResourceGroupPreparer(name_prefix='cli_test_containerapp_preview', location='eastus')
    def test_containerapp_compose_create_with_resources_from_both_cpus_and_deploy_cpu(self, resource_group):
        self.cmd('configure --defaults location={}'.format(TEST_LOCATION))
        compose_text = f"""
services:
  foo:
    image: mcr.microsoft.com/azuredocs/aks-helloworld:v1
    cpus: 0.75
    deploy:
      resources:
        reservations:
          cpus: 1.25
    expose:
      - "3000"
"""
        compose_file_name = f"{self._testMethodName}_compose.yml"
        write_test_file(compose_file_name, compose_text)
        env = prepare_containerapp_env_for_app_e2e_tests(self)

        self.kwargs.update({
            'environment': env,
            'compose': compose_file_name,
        })
        
        command_string = 'containerapp compose create'
        command_string += ' --compose-file-path {compose}'
        command_string += ' --resource-group {rg}'
        command_string += ' --environment {environment}'
        self.cmd(command_string, checks=[
            self.check(f'[?name==`foo`].properties.template.containers[0].resources.cpu', [1.25]),
        ])
        self.cmd(f'containerapp delete -n foo -g {resource_group} --yes', expect_failure=False)

        clean_up_test_file(compose_file_name)
