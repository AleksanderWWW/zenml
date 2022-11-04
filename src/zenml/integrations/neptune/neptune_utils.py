import os

from typing import Type

import neptune.new as neptune

from zenml.materializers.base_materializer import BaseMaterializer
from zenml.integrations.neptune.neptune_constants import NEPTUNE_RUN_ID


class NeptuneRunMaterializer(BaseMaterializer):
    ASSOCIATED_TYPES = (neptune.metadata_containers.Run,)

    def handle_input(self, data_type: Type[neptune.metadata_containers.Run]) -> neptune.metadata_containers.Run:
        super().handle_input(data_type)
        run_id = os.getenv(NEPTUNE_RUN_ID)
        run = neptune.init_run(with_id=run_id)
        return run

    def handle_return(self, run: neptune.metadata_containers.Run) -> None:
        ...
