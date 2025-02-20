# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.azclierror import UnknownError
from azure.cli.core.commands import LongRunningOperation
from azext_aks_preview.azurecontainerstorage._consts import (
    CONST_ACSTOR_K8S_EXTENSION_NAME,
    CONST_EXT_INSTALLATION_NAME,
    CONST_K8S_EXTENSION_CLIENT_FACTORY_MOD_NAME,
    CONST_K8S_EXTENSION_CUSTOM_MOD_NAME,
    CONST_STORAGE_POOL_DEFAULT_SIZE,
    CONST_STORAGE_POOL_DEFAULT_SIZE_ESAN,
    CONST_STORAGE_POOL_OPTION_NVME,
    CONST_STORAGE_POOL_OPTION_SSD,
    CONST_STORAGE_POOL_SKU_PREMIUM_LRS,
    CONST_STORAGE_POOL_TYPE_AZURE_DISK,
    CONST_STORAGE_POOL_TYPE_ELASTIC_SAN,
    CONST_STORAGE_POOL_TYPE_EPHEMERAL_DISK,
)
from azext_aks_preview.azurecontainerstorage._helpers import (
    check_if_extension_is_installed,
    generate_random_storage_pool_name,
    get_k8s_extension_module,
    perform_role_operations_on_managed_rg,
    register_dependent_rps,
    should_create_storagepool,
)
from azext_aks_preview.azurecontainerstorage._validators import validate_nodepool_names_with_cluster_nodepools
from knack.log import get_logger
from knack.prompting import prompt_y_n

logger = get_logger(__name__)


def perform_enable_azure_container_storage(
    cmd,
    subscription_id,
    resource_group,
    cluster_name,
    node_resource_group,
    kubelet_identity_object_id,
    storage_pool_name,
    storage_pool_type,
    storage_pool_size,
    storage_pool_sku,
    storage_pool_option,
    nodepool_names,
    agentpool_details,
    is_cluster_create,
):
    # Step 1: Check and register the dependent provider for ManagedClusters i.e.
    # Microsoft.KubernetesConfiguration
    if not register_dependent_rps(cmd, subscription_id):
        return

    # Step 2: Check if extension already installed incase of an update call
    if not is_cluster_create and check_if_extension_is_installed(cmd, resource_group, cluster_name):
        logger.error(
            "Extension type {0} already installed on cluster."
            "\nAborting installation of Azure Container Storage."
            .format(CONST_ACSTOR_K8S_EXTENSION_NAME)
        )
        return

    if nodepool_names is None:
        nodepool_names = "nodepool1"
    if storage_pool_type == CONST_STORAGE_POOL_TYPE_EPHEMERAL_DISK:
        if storage_pool_option is None:
            storage_pool_option = CONST_STORAGE_POOL_OPTION_NVME
        if storage_pool_option == CONST_STORAGE_POOL_OPTION_SSD:
            storage_pool_option = "temp"

    validate_nodepool_names_with_cluster_nodepools(nodepool_names, agentpool_details)

    # Step 3: Validate if storagepool should be created.
    # Depends on the following:
    #   3a: Grant AKS cluster's node identity the following
    #       roles on the AKS managed resource group:
    #       1. Reader
    #       2. Network Contributor
    #       3. Elastic SAN Owner
    #       4. Elastic SAN Volume Group Owner
    #       Ensure grant was successful if creation of
    #       Elastic SAN storagepool is requested.
    #   3b: Ensure Ls series nodepool is present if creation
    #       of Ephemeral NVMe Disk storagepool is requested.
    create_storage_pool = should_create_storagepool(
        cmd,
        subscription_id,
        node_resource_group,
        kubelet_identity_object_id,
        storage_pool_type,
        storage_pool_option,
        agentpool_details,
        nodepool_names,
    )

    # Step 4: Configure the storagepool parameters
    config_settings = []
    if create_storage_pool:
        if storage_pool_name is None:
            storage_pool_name = generate_random_storage_pool_name()
        if storage_pool_size is None:
            storage_pool_size = CONST_STORAGE_POOL_DEFAULT_SIZE_ESAN if \
                storage_pool_type == CONST_STORAGE_POOL_TYPE_ELASTIC_SAN else \
                CONST_STORAGE_POOL_DEFAULT_SIZE
        config_settings.extend(
            [
                {"cli.storagePool.create": True},
                {"cli.storagePool.name": storage_pool_name},
                {"cli.storagePool.size": storage_pool_size},
                {"cli.storagePool.type": storage_pool_type},
                {"cli.node.nodepools": nodepool_names},
            ]
        )

        if storage_pool_type == CONST_STORAGE_POOL_TYPE_EPHEMERAL_DISK:
            config_settings.append({"cli.storagePool.ephemeralDisk.diskType": storage_pool_option.lower()})
        else:
            if storage_pool_sku is None:
                storage_pool_sku = CONST_STORAGE_POOL_SKU_PREMIUM_LRS
            if storage_pool_type == CONST_STORAGE_POOL_TYPE_ELASTIC_SAN:
                config_settings.append({"cli.storagePool.elasticSan.sku": storage_pool_sku})
            elif storage_pool_type == CONST_STORAGE_POOL_TYPE_AZURE_DISK:
                config_settings.append({"cli.storagePool.azureDisk.sku": storage_pool_sku})
    else:
        config_settings.append({"cli.storagePool.create": False})

    # Step 5: Install the k8s_extension 'microsoft.azurecontainerstorage'
    client_factory = get_k8s_extension_module(CONST_K8S_EXTENSION_CLIENT_FACTORY_MOD_NAME)
    client = client_factory.cf_k8s_extension_operation(cmd.cli_ctx)

    k8s_extension_custom_mod = get_k8s_extension_module(CONST_K8S_EXTENSION_CUSTOM_MOD_NAME)
    try:
        result = k8s_extension_custom_mod.create_k8s_extension(
            cmd,
            client,
            resource_group,
            cluster_name,
            CONST_EXT_INSTALLATION_NAME,
            "managedClusters",
            CONST_ACSTOR_K8S_EXTENSION_NAME,
            auto_upgrade_minor_version=True,
            release_train="stable",
            scope="cluster",
            release_namespace="acstor",
            configuration_settings=config_settings,
        )

        create_result = LongRunningOperation(cmd.cli_ctx)(result)
        if create_result.provisioning_state == "Succeeded":
            logger.warning("Azure Container Storage successfully installed.")
    except Exception as ex:
        if is_cluster_create:
            logger.error("Azure Container Storage failed to install.\nError: {0}".format(ex.message))
            logger.warning(
                "AKS cluster is created. "
                "Please run `az aks update` along with `--enable-azure-container-storage` "
                "to enable Azure Container Storage."
            )
        else:
            logger.error("AKS update to enable Azure Container Storage failed.\nError: {0}".format(ex.message))


def perform_disable_azure_container_storage(
    cmd,
    subscription_id,
    resource_group,
    cluster_name,
    node_resource_group,
    kubelet_identity_object_id,
    perform_validation,
):
    # Step 1: Check if show_k8s_extension returns an extension already installed
    if not check_if_extension_is_installed(cmd, resource_group, cluster_name):
        raise UnknownError(
            "Extension type {0} not installed on cluster."
            "\nAborting disabling of Azure Container Storage."
            .format(CONST_ACSTOR_K8S_EXTENSION_NAME)
        )

    client_factory = get_k8s_extension_module(CONST_K8S_EXTENSION_CLIENT_FACTORY_MOD_NAME)
    client = client_factory.cf_k8s_extension_operation(cmd.cli_ctx)
    k8s_extension_custom_mod = get_k8s_extension_module(CONST_K8S_EXTENSION_CUSTOM_MOD_NAME)
    no_wait_delete_op = False
    # Step 2: Perform validation if accepted by user
    if perform_validation:
        config_settings = [{"cli.storagePool.uninstallValidation": True}]
        try:
            update_result = k8s_extension_custom_mod.update_k8s_extension(
                cmd,
                client,
                resource_group,
                cluster_name,
                CONST_EXT_INSTALLATION_NAME,
                "managedClusters",
                configuration_settings=config_settings,
                yes=True,
                no_wait=False,
            )

            update_long_op_result = LongRunningOperation(cmd.cli_ctx)(update_result)
            if update_long_op_result.provisioning_state == "Succeeded":
                logger.warning("Validation succeeded. Disabling Azure Container Storage...")

            # Since, pre uninstall validation will ensure deletion of storagepools,
            # we don't need to long wait while performing the delete operation.
            # Setting no_wait_delete_op = True.
            no_wait_delete_op = True
        except Exception as ex:
            config_settings = [{"cli.storagePool.uninstallValidation": False}]
            k8s_extension_custom_mod.update_k8s_extension(
                cmd,
                client,
                resource_group,
                cluster_name,
                CONST_EXT_INSTALLATION_NAME,
                "managedClusters",
                configuration_settings=config_settings,
                yes=True,
                no_wait=True,
            )

            if ex.message.__contains__("pre-upgrade hooks failed"):
                raise UnknownError(
                    "Validation failed. "
                    "Please ensure that storagepools are not being used. "
                    "Unable to disable Azure Container Storage. "
                    "Reseting cluster state."
                )
            else:
                raise UnknownError("Validation failed. Unable to disable Azure Container Storage. Reseting cluster state.")

    # Step 3: If the extension is installed and validation succeeded or skipped, call delete_k8s_extension
    try:
        delete_op_result = k8s_extension_custom_mod.delete_k8s_extension(
            cmd,
            client,
            resource_group,
            cluster_name,
            CONST_EXT_INSTALLATION_NAME,
            "managedClusters",
            yes=True,
            no_wait=no_wait_delete_op,
        )

        if not no_wait_delete_op:
            LongRunningOperation(cmd.cli_ctx)(delete_op_result)
    except Exception as delete_ex:
        raise UnknownError("Failure observed while disabling Azure Container Storage.\nError: {0}".format(delete_ex.message))

    logger.warning("Azure Container Storage has been disabled.")

    # Step 4: Revoke AKS cluster's node identity the following
    # roles on the AKS managed resource group:
    # 1. Reader
    # 2. Network Contributor
    # 3. Elastic SAN Owner
    # 4. Elastic SAN Volume Group Owner
    perform_role_operations_on_managed_rg(cmd, subscription_id, node_resource_group, kubelet_identity_object_id, False)
