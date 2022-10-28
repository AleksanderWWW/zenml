import threading
from uuid import uuid4

from faker import Faker

from neptune.new.metadata_containers import Project
from neptune.new.internal.backends.offline_neptune_backend import OfflineNeptuneBackend
from neptune.new.types.mode import Mode
from neptune.new.internal.backgroud_job_list import BackgroundJobList

from zenml.enums import StackComponentType


def test_neptune_experiment_tracker_attributes(neptune_experiment_tracker) -> None:
    assert neptune_experiment_tracker.type == StackComponentType.EXPERIMENT_TRACKER
    assert neptune_experiment_tracker.flavor == "neptune"
