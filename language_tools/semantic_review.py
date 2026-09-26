"""External semantic-review hook (DESIGN.md section 15.2, third-priority
"LLM 语义 QA" entry -- this is the *skeleton only*, deliberately not the
feature).

What this module is: the one architectural position the third-priority
entry asked for -- "架构上预留 reviewer 接口... 不能进默认流程" -- made
concrete and testable *before* any model integration exists. What it is
not: a QA check. Nothing in ``language_tools`` calls into this module on
any default code path (``api.convert()``, ``tm/qa_report``, the GUI's
QA-check page are all untouched), and there is no built-in reviewer
implementation -- an *external* reviewer is only ever reached when a
caller explicitly injects one (today: ``tmtool qa --semantic-review``;
the GUI intentionally has no entry point yet).

Why the hook ships without any model/network code (README's
"不需要联网、不上传文件" promise, promoted from a docs claim to a
tested invariant by ``tests/test_no_network_in_core.py``): the moment a
reviewer implementation lives *inside* the library, "default path never
leaves the machine" stops being a structural fact and becomes a promise
someone has to keep remembering. So the library defines only the shape
(``Reviewer``/``SemanticIssue``) and the plumbing (``attach()``); whoever
plugs in an LLM -- local small model or user-supplied remote endpoint --
supplies and runs that code themselves, outside this package. Credentials
are likewise never stored here (the toolbox's only persistence channel is
QSettings, i.e. a plaintext registry file on Windows -- wrong place for
an API key even if a built-in reviewer ever existed).

Semantics follow the term-check ``approved`` direction's precedent (DESIGN.md
15.1 Phase G3): injected results are *to-verify hints*, not defect
verdicts. They therefore live in a dedicated channel --
``meta['semantic_issues']`` -- and are never merged into
``meta['qa_issues']``/``meta['qa_confidence']`` (the same reason
``meta['term_issues']`` is separate): those fields are the rule checks'
own verdict and feed the CSV's status column and the GUI's confidence
sort, and an outside opinion diluting that score would make "LOW
confidence" mean something different depending on who injected what.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from language_tools.model import TranslationUnit


@dataclass
class SemanticIssue:
    """One to-verify hint about one unit, produced by an injected reviewer.

    ``type`` is a machine-readable code the *reviewer* chooses; ``SEM_`` is
    the recommended prefix (e.g. ``SEM_MISTRANSLATION``/``SEM_OMISSION``) so
    a semantic hit can never collide with a rule-check code from
    ``qa.ISSUE_LABELS`` -- there is deliberately no central registry of
    valid types, because this library cannot enumerate what outside
    reviewers will invent. ``description`` is free text for the human
    reviewer to read; ``span_hint`` optionally points at the offending
    substring (nothing in this repo renders highlights for semantic hits
    yet -- CSV/GUI highlighting is wired to the rule checks'
    ``qa.SPAN_FINDERS`` only -- so it is carried for the future consumer
    and may be ``None``).
    """

    type: str
    description: str
    span_hint: str | None = None


@runtime_checkable
class Reviewer(Protocol):
    """Anything with ``review(unit) -> list[SemanticIssue]`` qualifies.

    Per-unit (not per-corpus) so the injection point can't quietly receive
    a batch of units it doesn't have full context for -- a reviewer that
    *wants* corpus-wide context can still take the whole list itself and
    expose a per-unit view here; the reverse doesn't work. Must be
    side-effect-free on the units it is handed; all persistence of its
    findings goes through ``attach()``.
    """

    def review(self, unit: TranslationUnit) -> list[SemanticIssue]: ...


def attach(units, reviewer):
    """Runs ``reviewer.review(unit)`` once per unit and stores the result
    list in ``unit.meta['semantic_issues']`` (always set -- an empty list
    records "this unit was reviewed and nothing was flagged", so a
    downstream consumer can tell "reviewed, clean" apart from "never
    reviewed at all"). Mutates units in place and returns them, matching
    ``qa.run()``/``terms.check.run()``.

    No default reviewer, no try/except around ``review()``: a broken or
    misconfigured injected reviewer should surface loudly at the call site
    (the CLI reports it as a reviewer-loading failure), not be silently
    swallowed into an all-clean pass.
    """
    for u in units:
        u.meta['semantic_issues'] = list(reviewer.review(u))
    return units


def summarize(units):
    """Returns ``{'total': N, 'flagged': N, 'by_type': {type: count}}``
    over ``meta['semantic_issues']`` -- same shape as
    ``qa_report.summarize()``/``terms.check.summarize()``, but iterating
    the types that actually occurred (sorted for stable output) rather
    than a fixed ``ISSUE_TYPES``-style constant, because hit types come
    from whatever reviewer was injected and this library can't enumerate
    them. Units never reviewed (key absent) count toward ``total``, not
    ``flagged`` -- indistinguishable in the output from "reviewed,
    clean", which is fine: the caller decides whether to run ``attach()``
    at all, so a summarize result with everything clean-on-flagged never
    mixes the two situations in one report.
    """
    total = len(units)
    flagged = 0
    by_type = {}
    for u in units:
        issues = u.meta.get('semantic_issues', [])
        if issues:
            flagged += 1
        for issue in issues:
            by_type[issue.type] = by_type.get(issue.type, 0) + 1
    return {'total': total, 'flagged': flagged, 'by_type': by_type}
