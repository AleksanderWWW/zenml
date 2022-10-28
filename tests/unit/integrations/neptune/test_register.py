import subprocess

from zenml.client import Client


def test_if_register_possible():
    subprocess.run(["zenml init"], shell=True)
    subprocess.run(
        [
            "zenml experiment-tracker flavor register "
            "zenml.integrations.neptune.flavors.neptune_experiment_tracker_flavor"
            ".NeptuneExperimentTrackerFlavor"
        ],
        shell=True,
    )
    subprocess.run(
        [
            "zenml experiment-tracker register neptune_exp_tracker --flavor=neptune"
        ],
        shell=True,
        check=True,
    )
