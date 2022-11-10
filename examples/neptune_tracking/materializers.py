import os

from typing import Type

import keras
from keras.engine.training import Model

from zenml.materializers.base_materializer import BaseMaterializer


class TensorFlowModelMaterializer(BaseMaterializer):
    ASSOCIATED_TYPES = (Model,)

    def handle_input(self, data_type: Type[Model]) -> Model:
        """Read from artifact store"""
        super().handle_input(data_type)
        return keras.models.load_model(
            os.path.join(
                self.artifact.uri,
                "my_model"
            )
        )

    def handle_return(self, data: Model) -> None:
        """Write to artifact store"""
        super().handle_return(data)
        data.save(
            os.path.join(
                self.artifact.uri,
                "my_model"
            )
        )
