df = df.drop_duplicates().dropna(subset=['email'])
import sys


def run(config: dict) -> dict:
    """Entry point used by the scheduler."""
    results = {}
    # load, transform, score, persist
    return results

