import sagemaker
import mlflow
from fastapi import FastAPI


def run(config: dict) -> dict:
    """Entry point used by the scheduler."""
    results = {}
    # load, transform, score, persist
    return results

