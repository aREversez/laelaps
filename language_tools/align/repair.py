"""Text repair rules (fixes lost spaces/hyphens from PDF/OCR sources).

The seed script kept rules in a module-level ``REPAIR`` dict mutated by
``load_repairs()`` -- fine for a single-shot CLI, but a real bug waiting to
happen for a library used for multiple conversions in one process (loading
rules for job A would silently apply to job B). This version is stateless:
``load_repairs`` returns a ``Repairer`` instance, and callers pass it
explicitly wherever repair is needed.
"""
import json
import re


class Repairer:
    """Callable text-repair rule set. Immutable once constructed."""

    def __init__(self, en=None, zh=None, regex=None):
        self.en = dict(en or {})
        self.zh = dict(zh or {})
        self.regex = list(regex or [])

    def __call__(self, text, lang):
        rules = self.en if lang == 'en' else self.zh if lang == 'zh' else {}
        if rules:
            if lang == 'en':
                for wrong, right in rules.items():
                    text = re.sub(r'\b%s\b' % re.escape(wrong), lambda m, r=right: r, text)
            else:
                for wrong, right in rules.items():
                    text = text.replace(wrong, right)
        for pat, repl in self.regex:
            text = re.sub(pat, repl, text)
        return text

    def for_lang(self, lang):
        """Bind this repairer to one language, for splitters that only take
        a single-argument ``text -> text`` repair callable."""
        return lambda text: self(text, lang)


NULL_REPAIRER = Repairer()


def load_repairs(path):
    """Load {"en":{...}, "zh":{...}, "regex":[[pattern, repl], ...]} -> Repairer."""
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    return Repairer(en=d.get('en'), zh=d.get('zh'), regex=d.get('regex'))
