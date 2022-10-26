from zenml.enums import StackComponentType


def test_neptune_experiment_tracker_attributes(neptune_experiment_tracker) -> None:
    assert neptune_experiment_tracker.type == StackComponentType.EXPERIMENT_TRACKER
    assert neptune_experiment_tracker.flavor == "neptune"
