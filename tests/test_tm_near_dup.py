import random
from difflib import SequenceMatcher

from language_tools.model import TranslationUnit
from language_tools.tm import near_dup as near_dup_module


def _u(src, tgt='x', src_lang='en-US', tgt_lang='zh-CN', source_file=None):
    return TranslationUnit(src_lang=src_lang, tgt_lang=tgt_lang, src_text=src, tgt_text=tgt,
                            source_file=source_file)


def test_near_identical_segments_cluster_together():
    units = [
        _u('Click OK to continue.'),
        _u('Click OK to continue!'),
        _u('Click Cancel to abort.'),
    ]
    clusters = near_dup_module.find_clusters(units, threshold=0.85)
    assert len(clusters) == 1
    assert clusters[0]['size'] == 2
    texts = {u.src_text for u in clusters[0]['units']}
    assert texts == {'Click OK to continue.', 'Click OK to continue!'}


def test_exact_duplicates_also_cluster():
    units = [_u('Save changes before exiting.'), _u('Save changes before exiting.')]
    clusters = near_dup_module.find_clusters(units, threshold=0.85)
    assert len(clusters) == 1
    assert clusters[0]['size'] == 2


def test_unrelated_segments_do_not_cluster():
    units = [_u('Click OK to continue.'), _u('The weather today is sunny and warm.')]
    clusters = near_dup_module.find_clusters(units, threshold=0.85)
    assert clusters == []


def test_singleton_is_not_reported_as_a_cluster():
    units = [_u('A uniquely worded sentence with no relatives here.')]
    clusters = near_dup_module.find_clusters(units, threshold=0.85)
    assert clusters == []


def test_higher_threshold_is_stricter():
    units = [_u('Click OK to continue with the process.'),
             _u('Click OK to proceed with the task.')]
    loose = near_dup_module.find_clusters(units, threshold=0.5)
    strict = near_dup_module.find_clusters(units, threshold=0.98)
    assert len(loose) == 1
    assert strict == []


def test_side_tgt_clusters_on_target_text():
    units = [
        _u('An orange cat sleeps on the windowsill.', '点击确定以继续。'),
        _u('The stock market fell sharply this afternoon.', '点击确定以继续！'),
    ]
    by_src = near_dup_module.find_clusters(units, threshold=0.8, side='src')
    by_tgt = near_dup_module.find_clusters(units, threshold=0.8, side='tgt')
    assert by_src == []
    assert len(by_tgt) == 1


def test_case_and_whitespace_insensitive_matching():
    units = [_u('Click  OK   to continue.'), _u('click ok to continue.')]
    clusters = near_dup_module.find_clusters(units, threshold=0.99)
    assert len(clusters) == 1
    assert clusters[0]['size'] == 2


def test_empty_text_excluded_from_clustering():
    units = [_u(''), _u(''), _u('Click OK to continue.')]
    clusters = near_dup_module.find_clusters(units, threshold=0.85)
    assert clusters == []


def test_min_cluster_size_filters_small_groups():
    units = [
        _u('Click OK to continue.'),
        _u('Click OK to continue!'),
        _u('Totally unrelated sentence about the weather patterns today outside.'),
    ]
    clusters = near_dup_module.find_clusters(units, threshold=0.85, min_cluster_size=3)
    assert clusters == []


def test_transitive_closure_groups_a_chain_into_one_cluster():
    # A~B and B~C both clear threshold, A~C may not directly -- all three
    # should still land in the same cluster (connected components).
    units = [
        _u('The quick brown fox jumps over the lazy dog today.'),
        _u('The quick brown fox jumps over the lazy cat today.'),
        _u('The quick brown fox leaps over the lazy cat today.'),
    ]
    clusters = near_dup_module.find_clusters(units, threshold=0.9)
    assert len(clusters) == 1
    assert clusters[0]['size'] == 3


def test_invalid_threshold_raises():
    import pytest
    with pytest.raises(ValueError):
        near_dup_module.find_clusters([], threshold=0.0)
    with pytest.raises(ValueError):
        near_dup_module.find_clusters([], threshold=1.5)


def test_find_clusters_empty_input_does_not_raise():
    assert near_dup_module.find_clusters([]) == []


def test_summarize_counts_clusters_and_units():
    units = [
        _u('Click OK to continue.'),
        _u('Click OK to continue!'),
        _u('Totally unrelated sentence about the weather patterns today outside now.'),
    ]
    clusters = near_dup_module.find_clusters(units, threshold=0.85)
    s = near_dup_module.summarize(clusters)
    assert s == {'cluster_count': 1, 'total_units': 2}


def test_write_clusters_csv_groups_rows_by_cluster_id(tmp_path):
    units = [
        _u('Click OK to continue.', '点击确定以继续。', source_file='a.docx'),
        _u('Click OK to continue!', '点击确定以继续！', source_file='b.docx'),
    ]
    clusters = near_dup_module.find_clusters(units, threshold=0.85)
    out = tmp_path / 'clusters.csv'
    near_dup_module.write_clusters_csv(str(out), clusters)
    content = out.read_text(encoding='utf-8-sig')
    lines = content.strip().splitlines()
    assert lines[0].split(',') == ['cluster_id', 'cluster_size', 'src_text', 'tgt_text',
                                    'source_file']
    assert lines[1].startswith('1,2,')
    assert lines[2].startswith('1,2,')
    assert 'a.docx' in content
    assert 'b.docx' in content


def test_write_clusters_csv_empty_clusters_writes_header_only(tmp_path):
    out = tmp_path / 'clusters.csv'
    near_dup_module.write_clusters_csv(str(out), [])
    content = out.read_text(encoding='utf-8-sig')
    assert content.strip().splitlines() == [
        'cluster_id,cluster_size,src_text,tgt_text,source_file']


def test_length_bound_pruning_matches_brute_force_on_random_corpus():
    # Regression test for the length-bound pruning's exactness claim --
    # compares against a brute-force scan using the SAME shorter-first
    # argument order find_clusters() itself uses (SequenceMatcher's
    # ratio() is not perfectly order-symmetric in rare tie cases, a
    # property of the metric itself, not of this pruning).
    words = ['click', 'ok', 'cancel', 'continue', 'install', 'wizard', 'the', 'a', 'to',
             'update', 'error', 'warning', 'save', 'file', 'open', 'close', 'delete',
             'confirm', 'proceed', 'system', 'network', 'restart', 'device']
    random.seed(1234)
    units = [_u(' '.join(random.choice(words) for _ in range(random.randint(2, 9))))
             for _ in range(80)]
    threshold = 0.7

    texts = [near_dup_module._normalize(u.src_text) for u in units]
    n = len(units)
    brute_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            ti, tj = texts[i], texts[j]
            if not ti or not tj:
                continue
            a, b = (ti, tj) if len(ti) <= len(tj) else (tj, ti)
            if SequenceMatcher(None, a, b).ratio() >= threshold:
                brute_pairs.append((i, j))

    clusters = near_dup_module.find_clusters(units, threshold=threshold, min_cluster_size=2)
    id_to_index = {id(u): i for i, u in enumerate(units)}
    cluster_of = {}
    for cid, c in enumerate(clusters):
        for u in c['units']:
            cluster_of[id_to_index[id(u)]] = cid

    for i, j in brute_pairs:
        assert cluster_of.get(i) is not None
        assert cluster_of.get(i) == cluster_of.get(j)
