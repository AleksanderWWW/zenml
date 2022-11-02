import os

from typing import Type

import neptune.new as neptune

from zenml.steps import step
from zenml.client import Client
from zenml.materializers.base_materializer import BaseMaterializer


class NeptuneRunMaterializer(BaseMaterializer):
    ASSOCIATED_TYPES = (neptune.metadata_containers.Run,)

    def handle_input(self, data_type: Type[neptune.metadata_containers.Run]) -> neptune.metadata_containers.Run:
        super().handle_input(data_type)

        run_id = os.getenv("NEPTUNE_RUN_ID")
        run = neptune.init_run(with_id=run_id)
        return run

    def handle_return(self, run: neptune.metadata_containers.Run) -> None:
        ...


@step(output_materializers=NeptuneRunMaterializer)
def neptune_step() -> neptune.metadata_containers.Run:
    client = Client()
    config = client.active_stack.experiment_tracker.config
    project = os.getenv("NEPTUNE_PROJECT") or config.project
    token = os.getenv("NEPTUNE_API_TOKEN") or config.api_token
    run = neptune.init_run(project=project, api_token=token)
    run_id = run["sys/id"].fetch()
    os.environ["NEPTUNE_RUN_ID"] = run_id
    return run
