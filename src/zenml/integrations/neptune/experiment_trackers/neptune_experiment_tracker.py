from uuid import uuid4
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import neptune.new as neptune

from zenml.experiment_trackers.base_experiment_tracker import (
    BaseExperimentTracker,
    BaseExperimentTrackerConfig,
)

from zenml.utils.secret_utils import SecretField

if TYPE_CHECKING:
    from zenml.config.step_run_info import StepRunInfo


NEPTUNE_RUN_TYPE = Union[neptune.Run, "MockRun", None]


class NeptuneExperimentTrackerConfig(BaseExperimentTrackerConfig):
    project: Optional[str] = None
    api_token: str = SecretField()


class MockRun:
    def __init__(self, project_name, api_token) -> None:
        self.project_name = project_name
        self.api_token = api_token
        self.storage = {}
        self.id = uuid4()

    def log(self, key, val) -> None:
        self.storage[key] = val
        print(f"stored {val} as {key}")

    def get_id(self) -> str:
        return str(self.id)


def mock_init_run(project, api_token) -> NEPTUNE_RUN_TYPE:
    print(f"Initializing project {project} with token {api_token}")
    return MockRun(project, api_token)


class NeptuneExperimentTracker(BaseExperimentTracker):
    """
    Track experiments using neptune.ai
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the experiment tracker.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)

    @property
    def config(self) -> NeptuneExperimentTrackerConfig:
        """Returns the `NeptuneExperimentTrackerConfig` config.

        Returns:
            The configuration.
        """
        return cast(NeptuneExperimentTrackerConfig, self._config)

    def prepare_step_run(self, info: "StepRunInfo") -> None:
        """Initializes neptune run and stores it in the run_state
        object, so that it can be accessed later from other places
        e.g. step."""
        ...
