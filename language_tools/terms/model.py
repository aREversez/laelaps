"""Term-management data model (DESIGN.md section 15.1, Phase G0).

``TermEntry`` is the ``TranslationUnit``-equivalent for a glossary: one
bilingual term pair plus the metadata that distinguishes a term-base entry
from a plain TM segment. Same "known fields typed on the dataclass, not
stuffed into a meta dict" principle as ``TranslationUnit`` (see
``language_tools/model.py``).

``src_lang``/``tgt_lang`` live on the entry itself (not threaded around as
separate parameters everywhere) so any code holding a list of entries --
merged from more than one glossary file, say -- can always tell which
language pair a given entry belongs to without extra bookkeeping. That
said, ``glossary.py``'s read/write treat the language pair as one
file-level value, not a per-row column: see that module's docstring for
why asking someone hand-maintaining a glossary to repeat "en-US,zh-CN" on
every row would be pure busywork.
"""
from dataclasses import dataclass

# Recognized values for TermEntry.status.
#
# 'forbidden' is the direction ``terms/check.py``'s v1 TERM_FORBIDDEN
# check actually acts on: "this source term must never be translated as
# this specific (wrong) target string" -- a match either is or isn't
# present, essentially zero false-positive risk.
#
# 'approved' (the default) marks a preferred/standard translation but is
# NOT yet checked against anything -- "does the target text use the
# approved term" is a much harder question (synonyms, pronoun
# substitution, and legitimate rewording all make "term didn't literally
# appear" a poor signal on its own) that needs real false-positive/
# false-negative data before committing to a matching strategy. Modeled
# here regardless of the deferred check, so the glossary file format
# doesn't need a breaking change whenever that check eventually ships.
STATUSES = ('approved', 'forbidden')


@dataclass
class TermEntry:
    src_lang: str
    tgt_lang: str
    src_term: str
    tgt_term: str
    status: str = 'approved'
    domain: str | None = None
    note: str | None = None
    guid: str | None = None
    source_file: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
