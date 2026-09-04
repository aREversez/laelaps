# -*- coding: utf-8 -*-
"""
Convert a bilingual DOCX (source block then target block, both numbered [1]..[N])
into an SDL Trados Studio .sdltm translation memory with sentence-level alignment.

Layout expected in the document:
    [1] English paragraph 1
    [2] English paragraph 2
    ...
    [1] 中文段落 1
    [2] 中文段落 2
    ...

Usage:
    python docx_to_sdltm.py input.docx [-o output_basename]
                                       [--src en-US] [--tgt zh-CN]

Outputs <basename>.sdltm (Trados TM), <basename>.tmx (interchange),
        <basename>.csv (alignment review).

Optionally repairs PDF/OCR artefacts (lost spaces and hyphens, e.g.
"artificialintelligence" -> "artificial intelligence") using the rules in
repairs.json; enable with --repair.
"""
import sys, os, re, csv, json, math, html, uuid, zipfile, sqlite3, datetime, argparse

# --------------------------------------------------------------- text repair
REPAIR = {'en': {}, 'zh': {}, 'regex': []}


def load_repairs(path):
    """Load {"en":{...}, "zh":{...}, "regex":[[pattern, repl], ...]}."""
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    REPAIR['en'] = d.get('en', {})
    REPAIR['zh'] = d.get('zh', {})
    REPAIR['regex'] = d.get('regex', [])
    return len(REPAIR['en']) + len(REPAIR['zh']) + len(REPAIR['regex'])


def repair(text, lang):
    """Apply the loaded repair rules to a raw paragraph."""
    rules = REPAIR.get(lang, {})
    if rules:
        if lang == 'en':
            for wrong, right in rules.items():
                text = re.sub(r'\b%s\b' % re.escape(wrong), lambda m, r=right: r, text)
        else:
            for wrong, right in rules.items():
                text = text.replace(wrong, right)
    for pat, repl in REPAIR['regex']:
        text = re.sub(pat, repl, text)
    return text


# ----------------------------------------------------------------- docx text
def docx_paragraphs(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read('word/document.xml').decode('utf-8')
    out = []
    for p in re.findall(r'<w:p[ >].*?</w:p>|<w:p/>', xml, re.S):
        t = ''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', p, re.S))
        out.append(html.unescape(re.sub(r'<[^>]+>', '', t)).replace('\u00a0', ' ').strip())
    return out


def find_blocks(paras):
    """Split numbered paragraphs into the first (source) and second (target) block."""
    hits = []
    for i, t in enumerate(paras):
        m = re.match(r'^\[(\d+)\]\s*(.*)$', t, re.S)
        if m and m.group(2).strip():
            hits.append((i, int(m.group(1)), m.group(2).strip()))
    # the target block starts where numbering restarts at 1
    start = None
    for k in range(1, len(hits)):
        if hits[k][1] == 1:
            start = k
            break
    if start is None:
        raise SystemExit('Could not locate the two language blocks; expected [1] to appear twice.')
    src = {n: b for _, n, b in hits[:start]}
    tgt = {n: b for _, n, b in hits[start:]}
    keys = sorted(set(src) & set(tgt))
    missing_src = sorted(set(tgt) - set(src))
    missing_tgt = sorted(set(src) - set(tgt))
    if missing_src:
        print('warning: numbers present only in target block, dropped: %s' % missing_src)
    if missing_tgt:
        print('warning: numbers present only in source block, dropped: %s' % missing_tgt)
    return src, tgt, keys


# ------------------------------------------------------------ sentence split
ABBREV = {'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr', 'vs', 'etc', 'e.g', 'i.e',
          'inc', 'ltd', 'co', 'corp', 'no', 'fig', 'st', 'approx', 'cf', 'al',
          'u.s', 'u.k', 'a.m', 'p.m', 'ph.d', 'jan', 'feb', 'mar', 'apr', 'jun',
          'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec'}
TOKEN = re.compile(r"[A-Za-z0-9\u00C0-\u024F.\'\-&$%]+")


def split_en(text):
    text = repair(text, 'en')
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
                    if last in ABBREV and seg.rstrip().endswith('.') \
                            and not re.search(r'\b[A-Za-z]\.$', seg):
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


CJK = r'\u4e00-\u9fff\u3000-\u303f\uff00-\uffef'


def split_zh(text):
    """Split on 。！？； (matching Trados Studio's Chinese segmentation rules).
    Whitespace between two CJK characters is dropped; spaces inside Latin runs
    ("App Store", "John Ternus") are preserved."""
    text = html.unescape(text)
    text = repair(text, 'zh')
    text = re.sub(r'[\r\n\t\u00a0]+', ' ', text)
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'(?<=[%s])\s+(?=[%s])' % (CJK, CJK), '', text)
    text = text.strip()
    parts = re.findall(r'[^。！？；]*[。！？；]|[^。！？；]+', text)
    return [p.strip() for p in parts if p.strip()]


def nolen(s):
    return len(re.sub(r'\s+', '', s))


# ------------------------------------------------------- language dispatch
CJK_RE = re.compile('[%s]' % CJK)


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
    if is_cjk_lang(lang_code):
        return split_zh
    if looks_cjk(sample_text):
        print('warning: --%s=%s but the %s block looks like Chinese/CJK text; '
              'segmenting it with the CJK splitter instead of the Latin one.'
              % (role, lang_code, role))
        return split_zh
    return split_en


# -------------------------------------------------------------- alignment DP
MATCHES = [(1, 1), (2, 1), (1, 2), (2, 2), (3, 2), (2, 3), (1, 3), (3, 1), (3, 3)]
INF = float('inf')


def align_pairs(src, tgt, keys, src_lang, tgt_lang, S2=0.8, MP=2.5, MP0=2.0, GAP=60.0):
    sample_src = next((src[k] for k in keys if src[k]), '')
    sample_tgt = next((tgt[k] for k in keys if tgt[k]), '')
    split_src = pick_splitter(src_lang, sample_src, 'src')
    split_tgt = pick_splitter(tgt_lang, sample_tgt, 'tgt')
    # CJK segments are rejoined without spaces, Latin-script ones with spaces.
    join_src = '' if split_src is split_zh else ' '
    join_tgt = '' if split_tgt is split_zh else ' '
    split = {k: (split_src(src[k]), split_tgt(tgt[k])) for k in keys}
    en_len = sum(nolen(s) for k in keys for s in split[k][0])
    zh_len = sum(nolen(s) for k in keys for s in split[k][1])
    R = en_len / max(zh_len, 1)

    def cost(en_g, zh_g):
        if not en_g or not zh_g:
            return GAP
        le = sum(nolen(s) for s in en_g)
        lc = sum(nolen(s) for s in zh_g)
        if le == 0 or lc == 0:
            return GAP
        exp = le / R
        z = (lc - exp) / math.sqrt(max(exp * S2, 1.0))
        pen = 0.5 * z * z
        pen += MP * ((len(en_g) - 1) + (len(zh_g) - 1))
        if (len(en_g), len(zh_g)) != (1, 1):
            pen += MP0
        return pen

    def align(e, z):
        n, m = len(e), len(z)
        dp = [[INF] * (m + 1) for _ in range(n + 1)]
        bt = [[None] * (m + 1) for _ in range(n + 1)]
        dp[0][0] = 0.0
        for i in range(n + 1):
            for j in range(m + 1):
                if dp[i][j] == INF:
                    continue
                for di, dj in MATCHES:
                    ni, nj = i + di, j + dj
                    if ni > n or nj > m:
                        continue
                    c = cost(e[i:ni], z[j:nj])
                    if c != INF and dp[i][j] + c < dp[ni][nj]:
                        dp[ni][nj] = dp[i][j] + c
                        bt[ni][nj] = (i, j)
        if dp[n][m] == INF:
            return []
        res, i, j = [], n, m
        while (i, j) != (0, 0):
            pi, pj = bt[i][j]
            res.append((join_src.join(e[pi:i]), join_tgt.join(z[pj:j])))
            i, j = pi, pj
        res.reverse()
        return res

    out = []
    for k in keys:
        e, z = split[k]
        out.extend(align(e, z))
    return out, R


# ------------------------------------------------------------- sdltm writing
DDL = [
    """CREATE TABLE translation_memories(
	id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, guid BLOB NOT NULL,
	name TEXT NOT NULL UNIQUE, source_language TEXT NOT NULL,
	target_language TEXT NOT NULL, copyright TEXT, description TEXT,
	settings INT NOT NULL, creation_user TEXT NOT NULL,
	creation_date DATETIME NOT NULL, expiration_date DATETIME,
	fuzzy_indexes INT NOT NULL, last_recompute_date DATETIME,
	last_recompute_size INT, flags INT NOT NULL DEFAULT 0,
	tucount INT NOT NULL DEFAULT 0)""",
    """CREATE TABLE translation_units(
	id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, guid BLOB NOT NULL,
	translation_memory_id INT NOT NULL CONSTRAINT FK_tu_tm REFERENCES translation_memories(id) ON DELETE CASCADE,
	source_hash INTEGER NOT NULL, source_segment TEXT, target_hash INTEGER NOT NULL,
	target_segment TEXT, creation_date DATETIME NOT NULL, creation_user TEXT NOT NULL,
	change_date DATETIME NOT NULL, change_user TEXT NOT NULL,
	last_used_date DATETIME NOT NULL, last_used_user TEXT NOT NULL,
	usage_counter INT NOT NULL, flags INT)""",
    """CREATE TABLE attributes(id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	guid BLOB NOT NULL, name TEXT NOT NULL, type INT NOT NULL, tm_id INT NOT NULL,
CONSTRAINT CK_a UNIQUE (name, tm_id))""",
    """CREATE TABLE picklist_values(id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	guid BLOB NOT NULL, attribute_id INT NOT NULL CONSTRAINT FK_pv_a REFERENCES attributes(id) ON DELETE CASCADE,
	value TEXT NOT NULL)""",
    """CREATE TABLE picklist_attributes(translation_unit_id INT NOT NULL CONSTRAINT FK_pa_tu REFERENCES translation_units(id) ON DELETE CASCADE,
	picklist_value_id INT NOT NULL CONSTRAINT FK_pa_pv REFERENCES picklist_values(id) ON DELETE CASCADE)""",
    """CREATE TABLE string_attributes(translation_unit_id INT NOT NULL CONSTRAINT FK_sa_tu REFERENCES translation_units(id) ON DELETE CASCADE,
	attribute_id INT NOT NULL CONSTRAINT FK_sa_a REFERENCES attributes(id) ON DELETE CASCADE, value TEXT NOT NULL)""",
    """CREATE TABLE numeric_attributes(translation_unit_id INT NOT NULL CONSTRAINT FK_na_tu REFERENCES translation_units(id) ON DELETE CASCADE,
	attribute_id INT NOT NULL CONSTRAINT FK_na_a REFERENCES attributes(id) ON DELETE CASCADE, value INT NOT NULL)""",
    """CREATE TABLE date_attributes(translation_unit_id INT NOT NULL CONSTRAINT FK_da_tu REFERENCES translation_units(id) ON DELETE CASCADE,
	attribute_id INT NOT NULL CONSTRAINT FK_da_a REFERENCES attributes(id) ON DELETE CASCADE, value DATETIME NOT NULL)""",
    """CREATE TABLE translation_unit_contexts(translation_unit_id INT NOT NULL CONSTRAINT FK_tuc_tu REFERENCES translation_units(id) ON DELETE CASCADE,
	left_source_context INTEGER NOT NULL, left_target_context INTEGER NOT NULL,
CONSTRAINT PK_tuc PRIMARY KEY (translation_unit_id, left_source_context, left_target_context))""",
    """CREATE TABLE resources(id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
	guid BLOB NOT NULL, type INT NOT NULL, language TEXT, data BLOB NOT NULL)""",
    """CREATE TABLE tm_resources(tm_id INT NOT NULL CONSTRAINT FK_tr_t REFERENCES translation_memories(id) ON DELETE CASCADE,
	resource_id INT NOT NULL CONSTRAINT FK_tr_r REFERENCES resources(id) ON DELETE CASCADE,
CONSTRAINT PK_tr PRIMARY KEY (tm_id, resource_id))""",
    """CREATE TABLE fuzzy_data(translation_memory_id INT NOT NULL CONSTRAINT FK_fi1_tm REFERENCES translation_memories(id) ON DELETE CASCADE,
	translation_unit_id INT NOT NULL, fi1 TEXT, fi2 TEXT, fi4 TEXT, fi8 TEXT,
CONSTRAINT PK_fi1 PRIMARY KEY (translation_memory_id, translation_unit_id))""",
    """CREATE TABLE parameters(translation_memory_id INT NULL CONSTRAINT FK_p_tm REFERENCES translation_memories ON DELETE CASCADE,
	name TEXT NOT NULL, value TEXT NOT NULL)""",
    "CREATE INDEX idx_Resources1 ON resources (type, language)",
    "CREATE INDEX idx_Resources2 ON resources (id)",
    "CREATE INDEX idx_attributes1 ON attributes (tm_id)",
    "CREATE INDEX idx_attributes2 ON attributes (name, type)",
    "CREATE INDEX idx_date_attributes ON date_attributes (translation_unit_id, attribute_id)",
    "CREATE INDEX idx_numeric_attributes ON numeric_attributes (translation_unit_id, attribute_id)",
    "CREATE INDEX idx_picklist_attributes ON picklist_attributes (translation_unit_id)",
    "CREATE INDEX idx_string_attributes ON string_attributes (translation_unit_id, attribute_id)",
    "CREATE INDEX idx_tus_hashes ON translation_units(translation_memory_id, source_hash, target_hash)",
    "CREATE INDEX p_main ON parameters(translation_memory_id, name)",
]


def s64(x):
    return x - (1 << 64) if x >= (1 << 63) else x


def fnv1a64(text):
    """Deterministic stand-in for Trados' private (stemming-based) segment hash."""
    h = 0xcbf29ce484222325
    for b in text.encode('utf-8'):
        h ^= b
        h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return s64(h)


def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def seg_xml(text, culture):
    return ('<Segment xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema"><Elements><Text><Value>%s</Value>'
            '</Text></Elements><CultureName>%s</CultureName></Segment>' % (esc(text), culture))


def write_sdltm(path, pairs, src_lang, tgt_lang, name):
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    con.execute('pragma page_size=8192')
    con.execute('pragma encoding="UTF-8"')
    for d in DDL:
        con.execute(d)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    con.execute('INSERT INTO translation_memories(guid,name,source_language,target_language,'
                'copyright,description,settings,creation_user,creation_date,expiration_date,'
                'fuzzy_indexes,last_recompute_date,last_recompute_size,flags,tucount) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (uuid.uuid4().bytes, name, src_lang, tgt_lang, None, None, 127,
                 'WorkBuddy', now, '9999-12-31 23:59:59', 9, None, None, 0, 0))
    for k, v in (('VERSION', '8.06'), ('FREQUENCYTOP', '1000'), ('LAST_ANALYZE', '0')):
        con.execute('INSERT INTO parameters VALUES(?,?,?)', (1, k, v))
    con.execute('INSERT INTO attributes(guid,name,type,tm_id) VALUES(?,?,?,?)',
                (uuid.uuid4().bytes, 'StructureContext', 2, 1))
    n = 0
    for en, zh in pairs:
        en, zh = en.strip(), zh.strip()
        if not en or not zh:
            continue
        con.execute('INSERT INTO translation_units(guid,translation_memory_id,source_hash,'
                    'source_segment,target_hash,target_segment,creation_date,creation_user,'
                    'change_date,change_user,last_used_date,last_used_user,usage_counter,flags) '
                    'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (uuid.uuid4().bytes, 1, fnv1a64(en), seg_xml(en, src_lang),
                     fnv1a64(zh), seg_xml(zh, tgt_lang), now, 'WorkBuddy', now, 'WorkBuddy',
                     now, 'WorkBuddy', 0, 131073))
        n += 1
    con.execute('UPDATE translation_memories SET tucount=? WHERE id=1', (n,))
    con.commit()
    con.execute('VACUUM')
    con.close()
    return n


def write_tmx(path, pairs, src_lang, tgt_lang):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tmx version="1.4">\n')
        f.write('  <header creationtool="WorkBuddy" creationtoolversion="1.0" o-tmf="SDLTM" '
                'adminlang="en-US" srclang="%s" datatype="unknown" segtype="sentence" '
                'creationdate="%s" creationid="WorkBuddy"/>\n  <body>\n' % (src_lang, stamp))
        for en, zh in pairs:
            en, zh = en.strip(), zh.strip()
            if not en or not zh:
                continue
            f.write('    <tu creationdate="%s" creationid="WorkBuddy">\n' % stamp)
            f.write('      <tuv xml:lang="%s"><seg>%s</seg></tuv>\n' % (src_lang, esc(en)))
            f.write('      <tuv xml:lang="%s"><seg>%s</seg></tuv>\n' % (tgt_lang, esc(zh)))
            f.write('    </tu>\n')
        f.write('  </body>\n</tmx>\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('docx')
    ap.add_argument('-o', '--out', default=None)
    ap.add_argument('--src', default='en-US')
    ap.add_argument('--tgt', default='zh-CN')
    ap.add_argument('--repair', nargs='?', const='__default__', default=None,
                    help='apply text-repair rules from repairs.json (or a given file)')
    a = ap.parse_args()

    if a.repair:
        path = a.repair
        if path == '__default__':
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'repairs.json')
        if not os.path.exists(path):
            raise SystemExit('repair file not found: %s' % path)
        n = load_repairs(path)
        print('repair rules loaded from %s: %d' % (os.path.basename(path), n))

    paras = docx_paragraphs(a.docx)
    src, tgt, keys = find_blocks(paras)
    print('paired paragraphs: %d' % len(keys))
    pairs, R = align_pairs(src, tgt, keys, a.src, a.tgt)
    print('length ratio EN/ZH = %.3f' % R)
    print('aligned translation units: %d' % len(pairs))

    base = a.out or os.path.splitext(os.path.abspath(a.docx))[0]
    name = os.path.splitext(os.path.basename(a.docx))[0]
    n = write_sdltm(base + '.sdltm', pairs, a.src, a.tgt, name[:80])
    write_tmx(base + '.tmx', pairs, a.src, a.tgt)
    with open(base + '.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['No', 'EN', 'ZH'])
        for i, (en, zh) in enumerate(pairs, 1):
            w.writerow([i, en.strip(), zh.strip()])
    print('wrote %s.sdltm (%d TUs), %s.tmx, %s.csv' % (base, n, base, base))


if __name__ == '__main__':
    main()
