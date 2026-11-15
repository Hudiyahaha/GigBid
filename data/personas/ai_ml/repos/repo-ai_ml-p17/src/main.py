import spacy
from transformers import AutoModelForSequenceClassification
import torch
import torch.nn as nn


def run(config: dict) -> dict:
    """Entry point used by the scheduler."""
    results = {}
    # load, transform, score, persist
    return results

