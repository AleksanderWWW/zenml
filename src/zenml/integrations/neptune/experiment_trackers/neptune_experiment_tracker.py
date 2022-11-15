import hashlib
import os
from typing import TYPE_CHECKING, Any, Optional, Type, cast

import neptune.new as neptune

from zenml.config.base_settings import BaseSettings
from zenml.experiment_trackers.base_experiment_tracker import (
    BaseExperimentTracker,
    BaseExperimentTrackerConfig,
)
from zenml.integrations.neptune.experiment_trackers.run_state import RunState
from zenml.integrations.neptune.neptune_constants import (
    NEPTUNE_API_TOKEN,
    NEPTUNE_PROJECT,
)
from zenml.utils.secret_utils import SecretField

if TYPE_CHECKING:
    from zenml.config.step_run_info import StepRunInfo


class NeptuneExperimentTrackerConfig(BaseExperimentTrackerConfig):
    project: Optional[str] = None
    api_token: str = SecretField()


class NeptuneExperimentTrackerSettings(BaseSettings):
    tags = set()


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
        self.run_state: RunState = RunState()

    @property
    def config(self) -> NeptuneExperimentTrackerConfig:
        """Returns the `NeptuneExperimentTrackerConfig` config.

        Returns:
            The configuration.
        """
        return cast(NeptuneExperimentTrackerConfig, self._config)

    @property
    def settings_class(self) -> Optional[Type["BaseSettings"]]:
        """Settings class for the Neptune experiment tracker.

        Returns:
            The settings class.
        """
        return NeptuneExperimentTrackerSettings

    def prepare_step_run(self, info: "StepRunInfo") -> None:
        """Initializes neptune run and stores it in the run_state
        object, so that it can be accessed later from other places
        e.g. step."""

        settings = cast(
            NeptuneExperimentTrackerSettings,
            self.get_settings(info) or NeptuneExperimentTrackerSettings()
        )

        run_name = info.run_name

        run_id = hashlib.md5(run_name.encode()).hexdigest()

        project = self.config.project or os.getenv(NEPTUNE_PROJECT)
        token = self.config.api_token or os.getenv(NEPTUNE_API_TOKEN)

        run = neptune.init_run(
            project=project, api_token=token, custom_run_id=run_id, tags=list(settings.tags)
        )

        self.run_state.set_active_run(run)

    def cleanup_step_run(self, info: "StepRunInfo") -> None:
        ...
