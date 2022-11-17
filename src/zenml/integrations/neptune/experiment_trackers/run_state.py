import functools

import neptune.new as neptune

from zenml.client import Client
from zenml.integrations.constants import NEPTUNE


def singleton(class_):
    instances = {}

    def getinstance(*args, **kwargs):
        if class_ not in instances:
            instances[class_] = class_(*args, **kwargs)
        return instances[class_]

    return getinstance


class NoActiveRunException(Exception):
    pass


class InvalidExperimentTrackerSelected(Exception):
    pass


@singleton
class RunState:
    def __init__(self):
        self._run_id = ""  # potentially redundant
        self._active_run = None

    def set_active_run(
        self, neptune_run: neptune.metadata_containers.Run
    ) -> None:
        self._active_run = neptune_run

    @property
    def active_run(self) -> neptune.metadata_containers.Run:
        if self._active_run is None:
            raise NoActiveRunException("No active run at the moment")
        return self._active_run


def get_neptune_run() -> neptune.metadata_containers.Run:
    client = Client()
    experiment_tracker = client.active_stack.experiment_tracker
    if experiment_tracker.flavor == NEPTUNE:
        return experiment_tracker.run_state.active_run
    raise InvalidExperimentTrackerSelected("Fetching neptune run works only with neptune flavor of"
                                           "experiment tracker selected. Current selection is %s"
                                           % experiment_tracker.flavor)


def neptune_step(step):
    client = Client()
    experiment_tracker = client.active_stack.experiment_tracker.name

    @functools.wraps(step)
    def wrapper(*args, **kwargs):
        return step(*args, experiment_tracker=experiment_tracker, **kwargs)

    return wrapper
