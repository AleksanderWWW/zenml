from datetime import datetime
from uuid import uuid4

import pytest

from zenml.enums import StackComponentType
from zenml.integrations.neptune.experiment_trackers import NeptuneExperimentTracker, NeptuneExperimentTrackerConfig


@pytest.fixture(scope="session")
def neptune_experiment_tracker_config() -> NeptuneExperimentTrackerConfig:
    return NeptuneExperimentTrackerConfig()


@pytest.fixture(scope="session")
def neptune_experiment_tracker() -> NeptuneExperimentTracker:
    return NeptuneExperimentTracker(
        name="",
        id=uuid4(),
        config=neptune_experiment_tracker_config,
        flavor="neptune",
        type=StackComponentType.EXPERIMENT_TRACKER,
        user=uuid4(),
        project=uuid4(),
        created=datetime.now(),
        updated=datetime.now(),
    )
