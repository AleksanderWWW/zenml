from zenml.pipelines import pipeline


@pipeline(enable_cache=False,)
def neptune_example_pipeline(
    importer,
    normalizer,
    trainer,
):
    # Link all the steps artifacts together
    x_train, y_train, x_test, y_test = importer()
    x_trained_normed, x_test_normed = normalizer(x_train=x_train, x_test=x_test)
    trainer(x_train=x_trained_normed, y_train=y_train)
