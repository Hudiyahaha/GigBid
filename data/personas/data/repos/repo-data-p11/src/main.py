df = df.drop_duplicates().dropna(subset=['email'])
from google.cloud import bigquery


def run(config: dict) -> dict:
    """Entry point used by the scheduler."""
    results = {}
    # load, transform, score, persist
    return results

