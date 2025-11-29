from nornir import InitNornir
from nornir_utils.plugins.functions import print_result


def main():
    # Initialize Nornir with your configuration
    nr = InitNornir(config_file="config.yaml")

    # Display discovered inventory
    print("Discovered hosts:")
    for host in nr.inventory.hosts.values():
        print(f"  - {host.name} ({host.hostname})")

    print("\nDiscovered groups:")
    for group in nr.inventory.groups.values():
        print(f"  - {group.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
