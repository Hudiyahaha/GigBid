from langgraph.graph import StateGraph, START, END
import re
from fastapi import FastAPI
import faiss


def run(config: dict) -> dict:
    """Entry point used by the scheduler."""
    results = {}
    # load, transform, score, persist
    return results

