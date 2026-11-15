"""Chunkers: fixed-size (V0 baseline) and structure-aware (sections for prose, one chunk per code file)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from rag.ingest.loaders import Document


@dataclass
class Chunk:
    chunk_id: str
    item_id: str
    text: str
    meta: dict = field(default_factory=dict)
    context: str = ""            # V6: generated context line

    @property
    def indexed_text(self) -> str:
        return (self.context + "\n" + self.text) if self.context else self.text


def _cid(item_id: str, i: int, text: str) -> str:
    return f"{item_id}#{i}-{hashlib.md5(text.encode()).hexdigest()[:6]}"


def fixed_chunks(docs: list[Document], size: int = 900, overlap: int = 120) -> list[Chunk]:
    out = []
    for d in docs:
        t = d.text
        step = max(1, size - overlap)
        for i, start in enumerate(range(0, max(1, len(t)), step)):
            piece = t[start:start + size]
            if piece.strip():
                out.append(Chunk(_cid(d.item_id, i, piece + d.path), d.item_id, piece, d.meta()))
            if start + size >= len(t):
                break
    return out


def structured_chunks(docs: list[Document], size: int = 900) -> list[Chunk]:
    """Markdown split by headings; code files kept whole (truncated); short docs as one chunk."""
    out = []
    for d in docs:
        if d.kind in ("code", "review", "proposal") or len(d.text) <= size:
            pieces = [d.text[: size * 2]]
        else:
            sections = re.split(r"\n(?=#{1,3} )", d.text)
            pieces, buf = [], ""
            for s in sections:
                if len(buf) + len(s) > size and buf:
                    pieces.append(buf)
                    buf = ""
                buf += ("\n" if buf else "") + s
            if buf:
                pieces.append(buf)
        head = f"{d.title}\n" if d.title and d.kind != "code" else ""
        for i, p in enumerate(pieces):
            text = (head + p) if i > 0 else p
            out.append(Chunk(_cid(d.item_id, i, text + d.path), d.item_id, text, d.meta()))
    return out
