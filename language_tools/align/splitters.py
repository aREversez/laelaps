"""Language-aware sentence splitters and the reader/target language dispatch.

Ported from the seed script (docx_to_sdltm.py) with two fixes applied during
the Phase 1 port, both confirmed empirically before landing here:

1. Language-direction dispatch (``pick_splitter`` / ``is_cjk_lang`` /
   ``looks_cjk``): the seed script always ran ``split_en`` on the source
   block and ``split_zh`` on the target block regardless of the declared
   ``--src``/``--tgt`` languages. Reversing direction (Chinese source,
   English target) silently produced unsplit, unaligned segments. Already
   fixed once in the seed script; ported here unchanged.

2. Abbreviation false-negative in ``split_en``: the seed script's
   abbreviation guard was

       if last in ABBREV and seg.rstrip().endswith('.') \\
               and not re.search(r'\\b[A-Za-z]\\.$', seg):

   The trailing ``not re.search(r'\\b[A-Za-z]\\.$', seg)`` clause was meant to
   avoid misclassifying a bare single-letter initial (e.g. "J.") as an
   abbreviation, but ``last in ABBREV`` already guarantees ``last`` is one of
   the specific multi-character strings in ``ABBREV`` -- a bare initial can
   never be a member of that set, so the clause is redundant. Worse, it's
   actively wrong: every two-part abbreviation in ABBREV that itself
   contains an internal period (a.m, p.m, i.e, e.g, u.s, u.k, ph.d) ends in
   "single letter + period", so the regex matches and the guard is defeated
   for exactly the abbreviations it's supposed to protect. Confirmed with:

       split_en("Dr. Smith arrived at 9 a.m.")
       # before fix: ['Dr. Smith arrived at 9 a.m.', 'and started ...']
       # after fix:  ['Dr. Smith arrived at 9 a.m.']  (no bogus split)

   Fixed by dropping the clause; ``last in ABBREV`` alone is sufficient.
"""
import html
import re

ABBREV = {'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr', 'vs', 'etc', 'e.g', 'i.e',
          'inc', 'ltd', 'co', 'corp', 'no', 'fig', 'st', 'approx', 'cf', 'al',
          'u.s', 'u.k', 'a.m', 'p.m', 'ph.d', 'jan', 'feb', 'mar', 'apr', 'jun',
          'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec'}
TOKEN = re.compile(r"[A-Za-z0-9\u00C0-\u024F.\'\-&$%]+")
CJK = r'\u4e00-\u9fff\u3000-\u303f\uff00-\uffef'
CJK_RE = re.compile('[%s]' % CJK)


def split_en(text, repair_fn=None):
    """Split English (Latin-script) text into sentences.

    ``repair_fn`` is an optional ``text -> text`` callable applied before
    splitting (see ``align.repair``); passing ``None`` skips repair.
    """
    if repair_fn is not None:
        text = repair_fn(text)
    text = html.unescape(text).replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    text = re.sub(r'\s+', ' ', text).strip()
    out, start, i, n = [], 0, 0, len(text)
    while i < n:
        if text[i] in '.!?':
            j = i + 1
            while j < n and text[j] in '"\')]}':
                j += 1
            if j >= n or text[j] == ' ':
                if text[i] == '.':
                    seg = text[start:i + 1]
                    toks = TOKEN.findall(seg.lower())
                    last = (toks[-1] if toks else '').rstrip('.')
                    if last in ABBREV and seg.rstrip().endswith('.'):
                        i += 1
                        continue
                    if re.search(r'(^|\s)[A-Z]\.$', seg):
                        i += 1
                        continue
                piece = text[start:j].strip()
                if piece:
                    out.append(piece)
                start = j
                while start < n and text[start] == ' ':
                    start += 1
                i = start
                continue
        i += 1
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def split_zh(text, repair_fn=None):
    """Split CJK text on 。！？； (matches Trados Studio's Chinese segmentation).

    Whitespace between two CJK characters is dropped; spaces inside Latin
    runs ("App Store", "John Ternus") are preserved.
    """
    text = html.unescape(text)
    if repair_fn is not None:
        text = repair_fn(text)
    text = re.sub(r'[\r\n\t\u00a0]+', ' ', text)
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'(?<=[%s])\s+(?=[%s])' % (CJK, CJK), '', text)
    text = text.strip()
    parts = re.findall(r'[^。！？；]*[。！？；]|[^。！？；]+', text)
    return [p.strip() for p in parts if p.strip()]


def nolen(s):
    """Length ignoring whitespace, used for length-ratio cost calculations."""
    return len(re.sub(r'\s+', '', s))


def is_cjk_lang(code):
    return (code or '').split('-')[0].lower() in ('zh', 'ja', 'ko')


def looks_cjk(text):
    """Fallback content sniff, used when the declared language code doesn't
    clearly say zh/ja/ko but the paragraph is mostly CJK anyway."""
    letters = re.sub(r'\s+', '', text)
    if not letters:
        return False
    return len(CJK_RE.findall(letters)) / len(letters) > 0.3


def pick_splitter(lang_code, sample_text, role):
    """Return (splitter_fn, join_str, lang_tag) for a declared language + sample text.

    join_str is '' for CJK (chars glue back together without spaces) and
    ' ' for Latin-script languages -- callers must join re-merged sentence
    fragments with the same string the splitter conceptually removed.
    lang_tag is 'zh' or 'en', for binding language-specific repair rules.
    """
    if is_cjk_lang(lang_code):
        return split_zh, '', 'zh'
    if looks_cjk(sample_text):
        print('warning: --%s=%s but the %s block looks like Chinese/CJK text; '
              'segmenting it with the CJK splitter instead of the Latin one.'
              % (role, lang_code, role))
        return split_zh, '', 'zh'
    return split_en, ' ', 'en'
