"""Structural typing contracts for readers/writers.

These are Protocols, not base classes to inherit from -- any callable object
matching the shape satisfies the contract. Keep implementations stateless:
no module-level mutable globals (the original single-file script's global
``REPAIR`` dict is exactly the anti-pattern to avoid here, since a stateful
module would leak repair rules between unrelated conversions run in the same
process).
"""
from typing import Protocol

from language_tools.model import ParagraphPair, TranslationUnit


class BilingualReader(Protocol):
    """Bilingual source file -> paragraph-level pairs (not yet sentence-split)."""

    def read(self, path: str, **opts) -> list[ParagraphPair]:
        ...


class CorpusReader(Protocol):
    """Corpus file (tmx/sdltm) -> sentence-level units (already final grain)."""

    def read(self, path: str) -> list[TranslationUnit]:
        ...


class CorpusWriter(Protocol):
    """Sentence-level units -> corpus file."""

    def write(self, path: str, units: list[TranslationUnit], **opts) -> None:
        ...
