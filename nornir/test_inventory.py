from nornir import InitNornir
from nornir.core.task import Result, Task
from nornir_utils.plugins.functions import print_result

def hello_world(task: Task) -> Result:
    """A task that returns a greeting."""
    return Result(
        host=task.host,
        result=f"Hello from {task.host.name}!"
    )

def main():
    # Initialize Nornir
    nr = InitNornir(config_file="config.yaml")

    # Run the hello_world task on all hosts
    results = nr.run(task=hello_world)

    # Display results
    print_result(results)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())