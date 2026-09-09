"""Small shared UI helpers used by more than one tool page.

``section()`` started as a private copy in ``corpus_convert/page.py``,
then got a second private copy in ``tm_maintenance/page.py`` (that
file's docstring said explicitly: two copies is a coincidence, not yet a
pattern -- wait for a clearer signal before sharing). ``qa_check`` is the
third tool wanting the identical helper, which is that clearer signal:
promoted here now, with both existing call sites switched over to import
it instead of keeping their own copies.
"""
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


def section(title, content_widget):
    """A section header (label + hairline rule) above a content widget --
    used instead of QGroupBox, whose native chrome can't be made to look
    clean via QSS alone. Every tool page should use this for section
    headers, for visual consistency across the toolbox.
    """
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    label = QLabel(title)
    label.setProperty('role', 'sectionTitle')
    layout.addWidget(label)

    rule = QFrame()
    rule.setProperty('role', 'hairline')
    layout.addWidget(rule)

    layout.addWidget(content_widget)
    return wrapper
