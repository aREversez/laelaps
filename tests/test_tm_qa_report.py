from conftest import tmx_path

from language_tools.tm import qa_report


def test_run_populates_qa_meta_on_every_unit():
    units = qa_report.run(tmx_path('inline_markup_qa.tmx'))
    assert len(units) == 8
    for u in units:
        assert 'qa_issues' in u.meta
        assert 'qa_confidence' in u.meta


def test_run_flags_the_expected_issues_on_the_inline_markup_fixture():
    # Same fixture used for qa.py's own tests (tests/test_qa.py) -- reuse
    # rather than a new fixture, since the expected issues per row are
    # already documented there.
    units = qa_report.run(tmx_path('inline_markup_qa.tmx'))
    assert units[1].meta['qa_issues'] == ['TAG_MISMATCH']  # tu 2: dropped bold
    assert units[2].meta['qa_issues'] == ['TAG_MISMATCH']  # tu 3: added <hi>
    assert 'PLACEHOLDER_MISMATCH' in units[5].meta['qa_issues']  # tu 6: renamed var
    assert 'URL_MISMATCH' in units[7].meta['qa_issues']  # tu 8: dropped URL
    assert units[0].meta['qa_issues'] == []  # tu 1: reordered tag, not a defect


def test_run_raises_for_unsupported_format(tmp_path):
    bad = tmp_path / 'in.txt'
    bad.write_text('not a corpus file')
    try:
        qa_report.run(str(bad))
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'unsupported corpus format' in str(e)


def test_summarize_counts_total_and_flagged():
    units = qa_report.run(tmx_path('inline_markup_qa.tmx'))
    s = qa_report.summarize(units)
    assert s['total'] == 8
    assert s['flagged'] == 6  # tu 1 and tu 4 have no issues


def test_summarize_by_type_only_includes_types_that_occurred():
    units = qa_report.run(tmx_path('inline_markup_qa.tmx'))
    s = qa_report.summarize(units)
    assert s['by_type']['TAG_MISMATCH'] == 2
    assert s['by_type']['PLACEHOLDER_MISMATCH'] == 1
    assert s['by_type']['URL_MISMATCH'] == 1
    assert 'NUMBER_MISMATCH' not in s['by_type']
    assert 'EMPTY_SOURCE' not in s['by_type']


def test_summarize_empty_corpus_does_not_raise():
    s = qa_report.summarize([])
    assert s == {'total': 0, 'flagged': 0, 'by_type': {}}


def test_issue_types_constant_matches_what_qa_run_can_actually_produce():
    # Kill-test-style guard against ISSUE_TYPES silently drifting out of
    # sync with qa.py if a new check is added there without updating this
    # list (which the CLI --type validation and GUI filter dropdown both
    # rely on being complete).
    units = qa_report.run(tmx_path('inline_markup_qa.tmx'))
    s = qa_report.summarize(units)
    for issue_type in s['by_type']:
        assert issue_type in qa_report.ISSUE_TYPES
