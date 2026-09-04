"""Canonical intermediate representation shared by every reader/writer.

Known fields are typed on ``TranslationUnit`` directly. ``meta`` is only for
format-specific information that isn't yet common across formats -- do not
smuggle guid/timestamp/source-file info in there, it already has a home.
"""
from dataclasses import dataclass, field


@dataclass
class TranslationUnit:
    """One aligned sentence pair: the common currency between all formats."""

    src_lang: str
    tgt_lang: str
    src_text: str
    tgt_text: str
    guid: str | None = None
    source_file: str | None = None
    source_key: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class ParagraphPair:
    """One paragraph/row pair from a bilingual source file, pre-alignment.

    ``key`` is the original paragraph number / row index, kept around purely
    for diagnostics (missing-pair warnings, QA reports); it is not assumed to
    be numeric or sequential by any downstream code.
    """

    key: str
    src_text: str
    tgt_text: str
