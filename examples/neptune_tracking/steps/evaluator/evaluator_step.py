import numpy as np
import tensorflow as tf

from zenml.steps import step
from zenml.integrations.neptune.neptune_utils import get_neptune_run, neptune_step


@neptune_step
@step
def tf_evaluator(
    x_test: np.ndarray,
    y_test: np.ndarray,
    model: tf.keras.Model,
) -> float:
    """Calculate the loss for the model for each epoch in a graph"""
    neptune_run = get_neptune_run()
    _, test_acc = model.evaluate(x_test, y_test, verbose=2)
    neptune_run["metrics/val_accuracy"] = test_acc
    return test_acc
