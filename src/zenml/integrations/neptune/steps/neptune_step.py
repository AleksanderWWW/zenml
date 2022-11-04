import os

import neptune.new as neptune
from neptune.new.metadata_containers import Run


from zenml.steps import step
from zenml.client import Client
from zenml.integrations.neptune.neptune_utils import NeptuneRunMaterializer
from zenml.integrations.neptune.neptune_constants import (
    NEPTUNE_API_TOKEN,
    NEPTUNE_PROJECT,
    NEPTUNE_RUN_ID,
)


@step(output_materializers=NeptuneRunMaterializer, enable_cache=False)
def neptune_step() -> Run:
    client = Client()
    config = client.active_stack.experiment_tracker.config

    project = os.getenv(NEPTUNE_PROJECT) or config.project
    token = os.getenv(NEPTUNE_API_TOKEN) or config.api_token  # TODO: switch places

    run = neptune.init_run(project=project, api_token=token)
    run_id = run["sys/id"].fetch()

    os.environ[NEPTUNE_RUN_ID] = run_id

    return run
