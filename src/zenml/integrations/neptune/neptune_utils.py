import os
import warnings

from typing import Type, Callable, TypeVar
from functools import partial

import neptune.new as neptune

from zenml.materializers.base_materializer import BaseMaterializer
from zenml.integrations.neptune.neptune_constants import NEPTUNE_RUN_ID


NEPTUNE_F = TypeVar("NEPTUNE_F", bound=Callable[..., neptune.metadata_containers.Run])


def singleton(class_):
    instances = {}

    def getinstance(*args, **kwargs):
        if class_ not in instances:
            instances[class_] = class_(*args, **kwargs)
        return instances[class_]
    return getinstance


class RunIDNotSet(Exception):
    pass


class NoActiveRunException(Exception):
    pass


@singleton
class RunState:
    def __init__(self):
        self._run_id = ""  # potentially redundant
        self._active_run = None

    def set_active_run(self, neptune_run: neptune.metadata_containers.Run) -> None:
        self._active_run = neptune_run

    @property
    def active_run(self) -> neptune.metadata_containers.Run:
        if self._active_run is None:
            raise NoActiveRunException("No active run at the moment")
        return self._active_run

    # BELOW RUN_ID-BASED SOLUTION

    @property
    def run_id(self) -> str:
        return self._run_id

    @run_id.setter
    def run_id(self, run_id: str) -> None:
        self._run_id = run_id

    @property
    def get_active_run(self) -> NEPTUNE_F:
        return partial(neptune.init_run, with_id=self.run_id)

    def init_run(self, *args, **kwargs) -> neptune.metadata_containers.Run:

        if not self.run_id:
            raise RunIDNotSet

        if "with_id" in kwargs:
            warnings.warn("Overwriting run id will cause connection to a run that was not created by neptune "
                          "ZenML integration in the current session")
            self.run_id = kwargs.pop("with_id")

        run = neptune.init_run(*args, with_id=self.run_id, **kwargs)

        return run


class NeptuneRunMaterializer(BaseMaterializer):
    ASSOCIATED_TYPES = (neptune.metadata_containers.Run,)

    def handle_input(self, data_type: Type[neptune.metadata_containers.Run]) -> neptune.metadata_containers.Run:
        super().handle_input(data_type)
        run_id = os.getenv(NEPTUNE_RUN_ID)
        run = neptune.init_run(with_id=run_id)
        return run

    def handle_return(self, run: neptune.metadata_containers.Run) -> None:
        ...
