"""Write a TMX 1.4 interchange file."""
import datetime

from language_tools.writers.sdltm_writer import esc


def _seg_body(unit_text, unit_markup):
    """Build the inside of a <seg>...</seg> element.

    When ``unit_markup`` is None (the common case -- text-only TUs from
    docx/xlsx/csv inputs and from corpus readers whose <seg> had no
    inline tags), this is just the escaped plain text -- unchanged from
    pre-markup behavior. When markup is present (TMX input whose <seg>
    contained <bpt>/<ept>/<ph>/...), each tag fragment is written out
    verbatim and each text node is escaped -- so a TMX round-tripped
    through this writer preserves its inline structure losslessly instead
    of collapsing it back to plain text. The visible-text round-trip
    (escaping only, no markup) is still covered by the existing
    ``test_tmx_reader_round_trips_text_and_lang`` test.
    """
    if not unit_markup:
        return esc(unit_text)
    parts = []
    for node in unit_markup:
        if node.kind == 'text':
            parts.append(esc(node.content))
        else:  # 'tag' -- already an XML fragment from the source TMX, escape
            # nothing: it's already valid XML, just echo it back.
            parts.append(node.content)
    return ''.join(parts)


def write(path, units, src_lang, tgt_lang):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tmx version="1.4">\n')
        f.write('  <header creationtool="laelaps" creationtoolversion="1.0" o-tmf="SDLTM" '
                'adminlang="en-US" srclang="%s" datatype="unknown" segtype="sentence" '
                'creationdate="%s" creationid="laelaps"/>\n  <body>\n' % (src_lang, stamp))
        for u in units:
            src_text, tgt_text = u.src_text.strip(), u.tgt_text.strip()
            if not src_text or not tgt_text:
                continue
            f.write('    <tu creationdate="%s" creationid="laelaps">\n' % stamp)
            f.write('      <tuv xml:lang="%s"><seg>%s</seg></tuv>\n'
                    % (src_lang, _seg_body(src_text, getattr(u, 'src_markup', None))))
            f.write('      <tuv xml:lang="%s"><seg>%s</seg></tuv>\n'
                    % (tgt_lang, _seg_body(tgt_text, getattr(u, 'tgt_markup', None))))
            f.write('    </tu>\n')
        f.write('  </body>\n</tmx>\n')
