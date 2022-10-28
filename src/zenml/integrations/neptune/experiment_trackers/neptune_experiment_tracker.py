import os
from uuid import uuid4
from typing import TYPE_CHECKING, Any, Optional, cast

from zenml.experiment_trackers.base_experiment_tracker import (
    BaseExperimentTracker,
    BaseExperimentTrackerConfig,
)
from zenml.integrations.neptune.neptune_utils import singleton

if TYPE_CHECKING:
    from zenml.config.step_run_info import StepRunInfo


PROJECT_NAME = "PROJECT_NAME"
NEPTUNE_API_TOKEN = "NEPTUNE_API_TOKEN"


class NeptuneExperimentTrackerConfig(BaseExperimentTrackerConfig):
    project: Optional[str] = None
    api_token: Optional[str] = None


class MockRun:
    def __init__(self, project_name, api_token):
        self.project_name = project_name
        self.api_token = api_token
        self.storage = {}
        self.id = uuid4()

    def log(self, key, val):
        self.storage[key] = val
        print(f"stored {val} as {key}")

    def get_id(self) -> str:
        return str(self.id)


def mock_init_run(project, api_token) -> MockRun:
    print(f"Initializing project {project} with token {api_token}")
    return MockRun(project, api_token)


@singleton
class NeptuneRunState:
    def __init__(self):
        self._run = None

    def store_run(self, run_instance):
        self._run = run_instance

    def get_active_run(self):
        if self._run:
            return self._run
        raise ValueError("No active run present at the moment")



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
        self.run_state = NeptuneRunState()

    @property
    def config(self) -> NeptuneExperimentTrackerConfig:
        """Returns the `MLFlowExperimentTrackerConfig` config.

        Returns:
            The configuration.
        """
        return cast(NeptuneExperimentTrackerConfig, self._config)

    def prepare_step_run(self, info: "StepRunInfo") -> None:
        project = self.config.project or os.getenv(PROJECT_NAME)
        token = self.config.api_token or os.getenv(NEPTUNE_API_TOKEN)
        run = mock_init_run(project, token)
        self.run_state.store_run(run)
