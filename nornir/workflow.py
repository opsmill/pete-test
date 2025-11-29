#!/usr/bin/env python3
"""Network automation workflow using Nornir and Infrahub artifacts.

This module implements a complete configuration management workflow that:
1. Connects to Infrahub to load device inventory
2. Regenerates device configurations using Infrahub's artifact system
3. Retrieves and validates the generated configurations
4. Deploys configurations to network devices (with user confirmation)

The workflow is designed to work with the Infrahub sandbox environment and
targets edge devices that have the "Startup Config for Edge devices" artifact
definition configured.

Requirements:
    - nornir: Core automation framework
    - nornir-infrahub: Infrahub inventory and task plugins
    - nornir-netmiko: Device configuration deployment
    - nornir-utils: Result printing utilities

Example:
    Run the workflow from the command line::

        $ python workflow.py

    Or import and customize::

        from workflow import main
        main()

Note:
    The backup functionality requires a "running-config" artifact definition
    in Infrahub, which is not available in the public sandbox.
"""

import logging
from datetime import datetime
from pathlib import Path

from nornir import InitNornir
from nornir.core.task import Task, Result
from nornir_utils.plugins.functions import print_result
from nornir_netmiko.tasks import netmiko_send_config
from nornir_infrahub.plugins.tasks import (
    get_artifact,
    regenerate_host_artifact,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def retrieve_configuration(task: Task) -> Result:
    """Retrieve device configuration from Infrahub artifacts.

    Fetches the generated configuration artifact from Infrahub and saves it
    locally for validation and deployment. The configuration is saved to
    the `configs/` directory with the filename `{hostname}.cfg`.

    Args:
        task: Nornir task object containing host information and Infrahub client.

    Returns:
        Result object with:
            - On success: Path to saved configuration file
            - On failure: Error message describing the issue

    Raises:
        No exceptions are raised; all errors are captured in the Result object.
    """
    try:
        # Get the configuration artifact from Infrahub
        # Using the artifact name from the sandbox
        result = get_artifact(
            task,
            artifact="Startup Config for Edge devices",
        )

        if result.failed:
            return Result(
                host=task.host,
                failed=True,
                result=f"Failed to retrieve artifact: {result.result}",
            )

        # Check if we got actual content
        if not result.result or result.result.strip() == "":
            return Result(
                host=task.host,
                failed=True,
                result="Artifact exists but has no content",
            )

        # Save configuration locally for deployment
        output_dir = Path("configs")
        output_dir.mkdir(exist_ok=True)

        config_file = output_dir / f"{task.host.name}.cfg"
        config_file.write_text(result.result)

        return Result(
            host=task.host,
            result=f"Configuration retrieved from Infrahub and saved to {config_file}",
        )

    except Exception as e:
        error_msg = str(e)
        if "NodeNotFoundError" in error_msg or "Unable to find" in error_msg:
            return Result(
                host=task.host,
                failed=True,
                result="No artifact found for this device (may not be configured in Infrahub)",
            )
        return Result(
            host=task.host,
            failed=True,
            result=f"Failed to retrieve configuration: {error_msg}",
        )


def regenerate_configuration(task: Task) -> Result:
    """Trigger regeneration of device configuration in Infrahub.

    Requests Infrahub to regenerate the configuration artifact for the host.
    This ensures the latest data from Infrahub is used to generate a fresh
    configuration before retrieval.

    Args:
        task: Nornir task object containing host information and Infrahub client.

    Returns:
        Result object with:
            - On success: Confirmation message
            - On failure: Error message describing the issue
    """
    try:
        # Regenerate the artifact in Infrahub
        result = regenerate_host_artifact(
            task,
            artifact="Startup Config for Edge devices",
        )

        if result.failed:
            return Result(
                host=task.host,
                failed=True,
                result=f"Failed to regenerate artifact: {result.result}",
            )

        return Result(
            host=task.host, result="Configuration regenerated successfully in Infrahub"
        )

    except Exception as e:
        error_msg = str(e)
        if "NodeNotFoundError" in error_msg or "Unable to find" in error_msg:
            return Result(
                host=task.host,
                failed=True,
                result="No artifact definition found for this device",
            )
        return Result(
            host=task.host,
            failed=True,
            result=f"Failed to regenerate configuration: {error_msg}",
        )


def validate_configuration(task: Task) -> Result:
    """Validate the retrieved configuration before deployment.

    Performs basic validation checks on the configuration file to ensure
    it is suitable for deployment. Currently validates that the configuration
    is not empty.

    Args:
        task: Nornir task object containing host information.

    Returns:
        Result object with:
            - On success: Validation passed message with file size
            - On failure: List of failed validation checks
    """
    config_file = Path("configs") / f"{task.host.name}.cfg"

    if not config_file.exists():
        return Result(
            host=task.host, failed=True, result="Configuration file not found"
        )

    config_content = config_file.read_text()

    # Basic validation checks - relaxed for sandbox artifacts
    validations = {
        "not_empty": len(config_content.strip()) > 0,
    }

    failed_checks = [check for check, passed in validations.items() if not passed]

    if failed_checks:
        return Result(
            host=task.host,
            failed=True,
            result=f"Validation failed: {', '.join(failed_checks)}",
        )

    return Result(
        host=task.host,
        result=f"Configuration validation passed ({len(config_content)} bytes)",
    )


def deploy_configuration(task: Task) -> Result:
    """Deploy configuration to the network device via Netmiko.

    Reads the configuration from the local `configs/` directory and pushes
    it to the device using Netmiko's send_config method. Requires the device
    to have proper connection parameters configured in the Nornir inventory.

    Args:
        task: Nornir task object containing host information and connection details.

    Returns:
        Result object with:
            - On success: Deployment confirmation message
            - On failure: Error message from Netmiko or file not found error
    """
    config_file = Path("configs") / f"{task.host.name}.cfg"

    if not config_file.exists():
        return Result(
            host=task.host, failed=True, result="Configuration file not found"
        )

    # Read configuration
    config_commands = config_file.read_text().splitlines()

    # Deploy via Netmiko
    netmiko_result = netmiko_send_config(task=task, config_commands=config_commands)

    if netmiko_result.failed:
        return Result(
            host=task.host,
            failed=True,
            result=f"Deployment failed: {netmiko_result.result}",
        )

    return Result(host=task.host, result="Configuration deployed successfully")


def backup_current_config(task: Task) -> Result:
    """Backup current device configuration using Infrahub artifacts.

    Triggers generation of a running-config artifact in Infrahub, then
    retrieves and saves it locally. Backups are stored in timestamped
    directories under `backups/`.

    Note:
        This function requires a "running-config" artifact definition in
        Infrahub. The public sandbox does not have this artifact configured,
        so this step is skipped in the main workflow.

    Args:
        task: Nornir task object containing host information and Infrahub client.

    Returns:
        Result object with:
            - On success: Path to the backup file
            - On failure: Error message describing the issue
    """
    # Trigger artifact generation for this host
    result = regenerate_host_artifact(task=task, artifact="running-config")

    if result.failed:
        return Result(
            host=task.host, failed=True, result="Failed to generate backup artifact"
        )

    # Retrieve the generated artifact
    artifact_result = get_artifact(task=task, artifact="running-config")

    # Save backup locally
    backup_dir = Path("backups") / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_file = backup_dir / f"{task.host.name}_running.cfg"
    backup_file.write_text(artifact_result.result)

    return Result(host=task.host, result=f"Configuration backed up to {backup_file}")


def main() -> int:
    """Execute the complete network automation workflow.

    Orchestrates the following steps:
        1. Load device inventory from Infrahub
        2. Filter to edge devices (which have startup config artifacts)
        3. Skip backup (not available in sandbox)
        4. Regenerate configurations in Infrahub
        5. Retrieve configurations to local `configs/` directory
        6. Validate all retrieved configurations
        7. Deploy configurations (requires user confirmation)

    The workflow will abort if any validation failures occur, preventing
    deployment of invalid configurations.

    Returns:
        Exit code: 0 for success, 1 for validation failures.
    """
    # Initialize Nornir
    nr = InitNornir(config_file="config.yaml")

    logger.info(f"Loaded {len(nr.inventory.hosts)} hosts from Infrahub")

    # Filter to only edge devices (which have the Startup Config artifact)
    edge_devices = nr.filter(filter_func=lambda h: "edge" in h.name)
    logger.info(
        f"Filtered to {len(edge_devices.inventory.hosts)} edge devices with artifacts"
    )

    # Step 1: Skip backup (no running-config artifact in sandbox)
    logger.info("Step 1: Skipping backup (no running-config artifact in sandbox)")

    # Step 2: Regenerate configurations in Infrahub
    logger.info("Step 2: Regenerating configurations in Infrahub...")
    regen_results = edge_devices.run(task=regenerate_configuration)
    print_result(regen_results)

    # Step 3: Retrieve updated configurations from Infrahub
    logger.info("Step 3: Retrieving configurations from Infrahub...")
    retrieve_results = edge_devices.run(task=retrieve_configuration)
    print_result(retrieve_results)

    # Step 4: Validate configurations
    logger.info("Step 4: Validating configurations...")
    validation_results = edge_devices.run(task=validate_configuration)
    print_result(validation_results)

    # Check for validation failures
    failed_hosts = [
        host for host, result in validation_results.items() if result.failed
    ]

    if failed_hosts:
        logger.error(f"Validation failed for hosts: {failed_hosts}")
        logger.info("Aborting deployment due to validation failures")
        return 1

    # Step 5: Deploy configurations (with confirmation)
    logger.info("Step 5: Ready to deploy configurations")
    response = input("Deploy configurations to all devices? (yes/no): ")

    if response.lower() == "yes":
        logger.info("Deploying configurations...")
        deploy_results = edge_devices.run(task=deploy_configuration)
        print_result(deploy_results)

        # Generate completion report
        successful = len([r for r in deploy_results.values() if not r.failed])
        failed = len([r for r in deploy_results.values() if r.failed])

        logger.info(f"Deployment complete: {successful} successful, {failed} failed")
    else:
        logger.info("Deployment cancelled by user")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
