"""RAG variants. Each module defines NAME and FLAGS (a preset of rag.pipeline.Flags)."""

import importlib
import pkgutil

from rag.pipeline import Flags


def all_variants() -> dict[str, Flags]:
    out = {}
    for m in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(f"{__name__}.{m.name}")
        if hasattr(mod, "FLAGS"):
            out[mod.NAME] = mod.FLAGS
    return dict(sorted(out.items()))


def get(name: str) -> Flags:
    return importlib.import_module(f"{__name__}.{name}").FLAGS
