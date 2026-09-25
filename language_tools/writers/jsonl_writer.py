"""Write a JSONL (one JSON object per line) export for LLM/MT training
pipelines.

Lives alongside ``csv_writer``/``tmx_writer``/``sdltm_writer`` as a fourth
"consume the aligned TranslationUnit list" writer -- no network calls, no
external service, purely a local format conversion (DESIGN.md 15.2: "纯
本地格式转换，不违反'不上传文件'定位").

Unlike ``csv_writer`` (whose whole point is a human-reviewable sheet that
deliberately keeps empty-src/tgt rows so a reviewer can see gaps), this
mirrors ``tmx_writer``/``sdltm_writer`` and silently drops any unit whose
stripped src or tgt text is empty -- a training example with a blank side
isn't useful training data and would need filtering out downstream
anyway; there's no "human reviewer scanning line-by-line" audience here
the way there is for the CSV.

Each line carries its own ``src_lang``/``tgt_lang`` rather than relying on
a shared header the way tmx/sdltm do. JSONL exports are meant to be
concatenable across multiple conversion runs (different files, potentially
different language pairs) into one training corpus; once concatenated, a
per-file header has nowhere to live, so the language pair has to travel
with every line instead.

Field names (``src_lang``/``tgt_lang``/``src``/``tgt``) deliberately don't
follow any one training framework's chat-message schema (OpenAI/Alpaca/
ShareGPT-style ``messages``/``instruction`` wrappers) -- DESIGN.md 15.2
only asked for "a training format", not a particular framework's, and
guessing wrong locks in a shape someone then has to convert *again*. A
flat src/tgt record is the common denominator any downstream training
script can reshape into whatever wrapper it needs.

Written with ``ensure_ascii=False`` (readable CJK in the file itself,
consistent with every other writer in this package storing UTF-8 text
directly rather than ``\\uXXXX``-escaping it) and plain ``utf-8`` with no
BOM -- unlike ``csv_writer``'s ``utf-8-sig``, this file's audience is a
JSON parser/training script, not Excel, so there's no BOM-for-Excel
reason to add one (a leading BOM byte would break a naive line-by-line
JSON parser reading the first line).
"""
import json


def write(path, units, src_lang, tgt_lang):
    n = 0
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for u in units:
            src_text, tgt_text = u.src_text.strip(), u.tgt_text.strip()
            if not src_text or not tgt_text:
                continue
            f.write(json.dumps(
                {'src_lang': src_lang, 'tgt_lang': tgt_lang, 'src': src_text, 'tgt': tgt_text},
                ensure_ascii=False))
            f.write('\n')
            n += 1
    return n
