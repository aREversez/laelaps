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
# 'approved' (the default) marks a preferred/standard translation. Since
# Phase G3 ``check.py`` can also check this direction ("source term present
# but target doesn't use the approved string"), opt-in via
# ``check_approved=True`` -- opt-in because the question is genuinely
# harder (synonyms, pronoun substitution, and legitimate rewording all
# make "term didn't literally appear" a poor signal on its own), so those
# hits are surfaced as a to-verify hint list rather than a defect verdict.
# Modeled as data from the start so the glossary file format never needed a
# breaking change when the check eventually shipped.
# That check only acts on rows that *explicitly* declared 'approved' --
# see ``status_declared`` below for how the two cases stay distinguishable.
STATUSES = ('approved', 'forbidden')


@dataclass
class TermEntry:
    src_lang: str
    tgt_lang: str
    src_term: str
    tgt_term: str
    status: str = 'approved'
    # False when the status value is a fallback rather than a choice:
    # ``glossary.read()`` sets it for rows whose status cell was blank or
    # unrecognized (both default to status='approved' so the row still
    # displays/round-trips as before). ``check.run(check_approved=True)``
    # skips these -- an unset status must not silently become a
    # to-verify-hint worklist once the opt-in approved direction is
    # switched on. Defaults True so entries built in code or through the
    # GUI form (where a status was actively picked) are covered.
    status_declared: bool = True
    domain: str | None = None
    note: str | None = None
    guid: str | None = None
    source_file: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
