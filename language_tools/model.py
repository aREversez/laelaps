"""Canonical intermediate representation shared by every reader/writer.

Known fields are typed on ``TranslationUnit`` directly. ``meta`` is only for
format-specific information that isn't yet common across formats -- do not
smuggle guid/timestamp/source-file info in there, it already has a home.

Inline markup (TMX ``<bpt>/<ept>/<ph>/<hi>``, future XLIFF/SDLTM tag runs)
lives on ``src_markup``/``tgt_markup`` as a list of ``InlineNode`` -- a
deliberately small IR that any future tagged format can map into/out of
without reshaping ``TranslationUnit`` itself. ``None`` means "no markup
captured / plain text only", which is the case for every shipped reader
except ``tmx_reader`` when a <seg> contains inline tags.
"""
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class InlineNode:
    """One piece of a tagged segment -- either visible text or one inline
    element (e.g. TMX ``<bpt>/<ept>/<ph>``, future XLIFF ``<mrk>/<bx>/<ex>``).

    Kept deliberately minimal: ``kind`` is 'text' for plain visible text or
    'tag' for one inline element; ``content`` holds the text for 'text'
    nodes or the raw XML fragment for 'tag' nodes. No nested structure for
    now -- a ``<bpt>...</bpt>`` pair is just two separate 'tag' nodes, the
    opening one carrying the start markup, the closing one carrying the end
    markup. That's enough to round-trip TMX inline markup losslessly today
    and gives a stable shape to extend (e.g. add attributes or a type
    discriminator) when XLIFF/SRT/SDLTM tagged input actually arrives.
    """

    kind: Literal['text', 'tag']
    content: str


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
    # Optional inline-markup IR. None = plain text only (the case for every
    # shipped reader today except tmx_reader when a <seg> has inline tags).
    # When populated, ``src_text``/``tgt_text`` are still the visible text
    # (markup stripped) so existing QA/writer code that doesn't know about
    # markup keeps working unchanged.
    src_markup: list[InlineNode] | None = None
    tgt_markup: list[InlineNode] | None = None
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
