import os

from pathlib import Path

from zenml.client import Client


def setup_stack():
    client = Client()

    cwd = Path(os.getcwd())
    zen_dir = cwd / ".zen"

    if not zen_dir.exists():
        client.initialize()

    if client.active_stack.name == "neptune_stack":
        return

    if "neptune_stack" not in [stack.name for stack in client.stacks]:
        os.system("zenml stack register neptune_stack -a default -o default -e neptune_exp_tracker --set")
    else:
        os.system("zenml stack set neptune_stack")


if __name__ == "__main__":
    setup_stack()
