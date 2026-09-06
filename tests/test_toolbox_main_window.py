from toolbox.main_window import MainWindow


def test_main_window_lists_corpus_convert_tool(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    labels = [w.sidebar.item(i).text() for i in range(w.sidebar.count())]
    assert '语料转换' in labels


def test_sidebar_items_have_icons(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    for i in range(w.sidebar.count()):
        assert not w.sidebar.item(i).icon().isNull()


def test_sidebar_has_object_name_for_qss_targeting(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.sidebar.objectName() == 'sidebar'


def test_selecting_sidebar_item_switches_stack_page(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.stack.currentIndex() == 0
    if w.sidebar.count() > 1:
        w.sidebar.setCurrentRow(1)
        assert w.stack.currentIndex() == 1
