"""Minimal *external* reviewer used by the semantic-review tests (and
usable as a copy-paste starting point for a real one, e.g. an LLM-backed
reviewer living outside this repo -- which is exactly where DESIGN.md
15.2 says model integrations must live, per language_tools/
semantic_review.py's docstring).

Importable as ``semantic_stub`` with ``tests/`` on sys.path; the CLI
end-to-end test passes ``semantic_stub:IdenticalTextReviewer`` as
``--semantic-review``'s SPEC and adds this file's directory to PYTHONPATH.
"""
from language_tools.model import TranslationUnit
from language_tools.semantic_review import SemanticIssue


class IdenticalTextReviewer:
    """Fake "semantic" check: flags units whose src and tgt are literally
    the same non-empty text (an untranslated copy-paste -- the one
    semantic-class finding that needs no model to detect, which is why
    this stub is a believable stand-in for the injection plumbing).
    """

    def review(self, unit: TranslationUnit) -> list[SemanticIssue]:
        src = unit.src_text.strip()
        tgt = unit.tgt_text.strip()
        if src and src == tgt:
            return [SemanticIssue('SEM_SUSPECT_IDENTICAL',
                                  'target identical to source (possible untranslated copy)',
                                  span_hint=src)]
        return []


# Pre-built singleton, so the CLI tests can cover the "spec names an
# instance, not a class" form as well as the bare-class form.
REVIEWER = IdenticalTextReviewer()
