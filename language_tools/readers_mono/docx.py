"""Monolingual .docx reader: a Word document -> its non-empty body paragraphs.

The counterpart to ``readers/docx.py`` for the leverage-analysis input, where
the file is an ordinary single-language document (no source/target pairs to
detect). Extraction rules -- what counts as body text -- live in
``readers/_ooxml.iter_text_paragraphs``; this module only drops empty
paragraphs.
"""
from language_tools.readers._ooxml import iter_text_paragraphs


def read(path):
    """Returns the non-empty paragraph texts in document order."""
    return [text for text in iter_text_paragraphs(path) if text]
