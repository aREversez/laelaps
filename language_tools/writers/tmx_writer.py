"""Write a TMX 1.4 interchange file."""
import datetime

from language_tools.writers.sdltm_writer import esc


def write(path, units, src_lang, tgt_lang):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tmx version="1.4">\n')
        f.write('  <header creationtool="WorkBuddy" creationtoolversion="1.0" o-tmf="SDLTM" '
                'adminlang="en-US" srclang="%s" datatype="unknown" segtype="sentence" '
                'creationdate="%s" creationid="WorkBuddy"/>\n  <body>\n' % (src_lang, stamp))
        for u in units:
            src_text, tgt_text = u.src_text.strip(), u.tgt_text.strip()
            if not src_text or not tgt_text:
                continue
            f.write('    <tu creationdate="%s" creationid="WorkBuddy">\n' % stamp)
            f.write('      <tuv xml:lang="%s"><seg>%s</seg></tuv>\n' % (src_lang, esc(src_text)))
            f.write('      <tuv xml:lang="%s"><seg>%s</seg></tuv>\n' % (tgt_lang, esc(tgt_text)))
            f.write('    </tu>\n')
        f.write('  </body>\n</tmx>\n')
