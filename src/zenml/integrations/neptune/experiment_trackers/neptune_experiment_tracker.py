from typing import Any, cast

from zenml.experiment_trackers.base_experiment_tracker import (
    BaseExperimentTracker,
)
from zenml.integrations.neptune.flavors.neptune_experiment_tracker_flavor import (
    NeptuneExperimentTrackerConfig,
)


class NeptuneExperimentTracker(BaseExperimentTracker):
    """
    Track experiments using neptune.ai
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the experiment tracker and validate the tracking uri.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)

    @property
    def config(self) -> NeptuneExperimentTrackerConfig:
        """Returns the `MLFlowExperimentTrackerConfig` config.

        Returns:
            The configuration.
        """
        return cast(NeptuneExperimentTrackerConfig, self._config)
