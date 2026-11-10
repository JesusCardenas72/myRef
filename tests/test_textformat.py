from unittest.mock import MagicMock, patch

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef import commands, textformat
from myRef.items import BeePixmapItem, BeeTextItem
from myRef.widgets.textformat import (
    EditorTarget,
    NoteFormatToolbar,
    TextFormatToolbar,
)


def select_all(item):
    cursor = QtGui.QTextCursor(item.document())
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    return cursor


def first_format(item):
    cursor = QtGui.QTextCursor(item.document())
    cursor.setPosition(1)
    return cursor.charFormat()


def edit(view, item):
    view.scene.addItem(item)
    item.setSelected(True)
    item.enter_edit_mode()
    cursor = item.textCursor()
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    item.setTextCursor(cursor)


# Formatting operations

def test_bold_toggles(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.bold(textformat.reference_format(cursor))(cursor)
    assert textformat.is_bold(first_format(item))
    cursor = select_all(item)
    textformat.bold(textformat.reference_format(cursor))(cursor)
    assert not textformat.is_bold(first_format(item))


def test_italic_underline_strikeout(qapp):
    item = BeeTextItem('foo')
    for op in (textformat.italic, textformat.underline,
               textformat.strikeout):
        cursor = select_all(item)
        op(textformat.reference_format(cursor))(cursor)
    fmt = first_format(item)
    assert fmt.fontItalic()
    assert fmt.fontUnderline()
    assert fmt.fontStrikeOut()


def test_colors_font_and_size(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.foreground(QtGui.QColor('red'))(cursor)
    textformat.highlight(QtGui.QColor('yellow'))(cursor)
    textformat.font_family('Arial')(cursor)
    textformat.font_size(30)(cursor)
    fmt = first_format(item)
    assert fmt.foreground().color() == QtGui.QColor('red')
    assert fmt.background().color() == QtGui.QColor('yellow')
    assert fmt.fontFamilies() == ['Arial']
    assert fmt.fontPointSize() == 30


def test_highlight_transparent_removes_highlight(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.highlight(QtGui.QColor('yellow'))(cursor)
    cursor = select_all(item)
    textformat.highlight(QtGui.QColor(0, 0, 0, 0))(cursor)
    assert first_format(item).background().style() == Qt.BrushStyle.NoBrush


def test_align(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.align(Qt.AlignmentFlag.AlignRight)(cursor)
    assert (item.document().begin().blockFormat().alignment()
            == Qt.AlignmentFlag.AlignRight)


def test_bullet_list_toggles(qapp):
    item = BeeTextItem('foo\nbar')
    cursor = select_all(item)
    textformat.bullet_list()(cursor)
    blocks = [item.document().begin(), item.document().lastBlock()]
    assert all(b.textList() for b in blocks)
    assert (blocks[0].textList().format().style()
            == textformat.ListStyle.ListDisc)
    cursor = select_all(item)
    textformat.bullet_list()(cursor)
    assert not item.document().begin().textList()
    assert not item.document().lastBlock().textList()


def test_numbered_list(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.numbered_list()(cursor)
    assert (item.document().begin().textList().format().style()
            == textformat.ListStyle.ListDecimal)


def test_bullet_list_to_numbered_list(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.bullet_list()(cursor)
    cursor = select_all(item)
    textformat.numbered_list()(cursor)
    assert (item.document().begin().textList().format().style()
            == textformat.ListStyle.ListDecimal)


def test_checklist_and_toggle_checkbox(qapp):
    item = BeeTextItem('foo\nbar')
    cursor = select_all(item)
    textformat.checklist()(cursor)
    block = item.document().begin()
    assert textformat.is_checklist_block(block)
    assert block.blockFormat().marker() == textformat.MarkerType.Unchecked
    textformat.toggle_checkbox(block)
    block = item.document().begin()
    assert block.blockFormat().marker() == textformat.MarkerType.Checked
    textformat.toggle_checkbox(block)
    assert (item.document().begin().blockFormat().marker()
            == textformat.MarkerType.Unchecked)


def test_checklist_toggles_off(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.checklist()(cursor)
    cursor = select_all(item)
    textformat.checklist()(cursor)
    block = item.document().begin()
    assert not block.textList()
    assert block.blockFormat().marker() == textformat.MarkerType.NoMarker


def test_bullet_list_from_checklist_removes_markers(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.checklist()(cursor)
    cursor = select_all(item)
    textformat.bullet_list()(cursor)
    block = item.document().begin()
    assert block.textList()
    assert block.blockFormat().marker() == textformat.MarkerType.NoMarker


def test_checkbox_at(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.checklist()(cursor)
    block = item.document().begin()
    layout = block.layout()
    rect = item.document().documentLayout().blockBoundingRect(block)
    text_left = layout.position().x() + layout.lineAt(0).x()
    pos = QtCore.QPointF(text_left - 5, rect.center().y())
    assert textformat.checkbox_at(item.document(), pos) == block
    pos = QtCore.QPointF(text_left + 5, rect.center().y())
    assert textformat.checkbox_at(item.document(), pos) is None


def test_indent_list_and_dedent(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.bullet_list()(cursor)
    cursor = select_all(item)
    textformat.indent(1)(cursor)
    assert item.document().begin().textList().format().indent() == 2
    cursor = select_all(item)
    textformat.indent(-1)(cursor)
    assert item.document().begin().textList().format().indent() == 1
    cursor = select_all(item)
    textformat.indent(-1)(cursor)
    assert not item.document().begin().textList()


def test_indent_paragraph(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.indent(1)(cursor)
    assert item.document().begin().blockFormat().indent() == 1
    cursor = select_all(item)
    textformat.indent(-1)(cursor)
    textformat.indent(-1)(cursor)
    assert item.document().begin().blockFormat().indent() == 0


def test_clear_format(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.bold(textformat.reference_format(cursor))(cursor)
    textformat.foreground(QtGui.QColor('red'))(cursor)
    cursor = select_all(item)
    textformat.clear_format()(cursor)
    fmt = first_format(item)
    assert not textformat.is_bold(fmt)
    assert fmt.foreground().style() == Qt.BrushStyle.NoBrush


def test_copy_and_paste_format(qapp):
    source = BeeTextItem('foo')
    cursor = select_all(source)
    textformat.italic(textformat.reference_format(cursor))(cursor)
    textformat.align(Qt.AlignmentFlag.AlignHCenter)(cursor)
    textformat.copy_format(select_all(source))
    target = BeeTextItem('bar')
    textformat.paste_format()(select_all(target))
    assert first_format(target).fontItalic()
    assert (target.document().begin().blockFormat().alignment()
            == Qt.AlignmentFlag.AlignHCenter)


def test_paste_format_without_copied_format_does_nothing(qapp):
    item = BeeTextItem('foo')
    old = item.html()
    textformat.paste_format(None)
    with patch('myRef.textformat.copied_format', None):
        textformat.paste_format()(select_all(item))
    assert item.html() == old


def test_link_on_selection(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.link('example.com')(cursor)
    fmt = first_format(item)
    assert fmt.isAnchor()
    assert fmt.anchorHref() == 'http://example.com'


def test_link_without_selection_inserts_url(qapp):
    item = BeeTextItem('foo ')
    cursor = QtGui.QTextCursor(item.document())
    cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
    textformat.link('https://example.com')(cursor)
    assert item.toPlainText() == 'foo https://example.com'
    assert not cursor.charFormat().isAnchor()


def test_empty_link_does_nothing(qapp):
    item = BeeTextItem('foo')
    old = item.html()
    textformat.link('  ')(select_all(item))
    assert item.html() == old


def test_anchor_at(qapp):
    item = BeeTextItem('foo')
    textformat.link('https://example.com')(select_all(item))
    rect = item.document().documentLayout().blockBoundingRect(
        item.document().begin())
    pos = QtCore.QPointF(rect.left() + 3, rect.center().y())
    assert item.anchor_at(pos) == 'https://example.com'
    assert item.anchor_at(QtCore.QPointF(-100, -100)) is None


# Text item

def test_text_item_loads_html(qapp):
    item = BeeTextItem(html='<b>foo</b>')
    assert item.toPlainText() == 'foo'
    assert textformat.is_bold(first_format(item))


def test_text_item_loads_plain_text_from_old_files(qapp):
    item = BeeTextItem.create_from_data(data={'text': '<b>foo</b>'})
    assert item.toPlainText() == '<b>foo</b>'


def test_text_item_save_data_roundtrip(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.bold(textformat.reference_format(cursor))(cursor)
    item.set_text_width(150)
    item.set_background('#ff112233')
    data = item.get_extra_save_data()
    assert data['text_width'] == 150
    assert data['background'] == '#ff112233'
    loaded = BeeTextItem.create_from_data(data=data)
    assert loaded.toPlainText() == 'foo'
    assert textformat.is_bold(first_format(loaded))
    assert loaded.textWidth() == 150
    assert loaded.background_color() == QtGui.QColor('#ff112233')


def test_text_item_set_text_width(qapp):
    item = BeeTextItem('foo bar baz')
    assert item.has_fixed_width() is False
    item.set_text_width(30)
    assert item.has_fixed_width() is True
    assert item.boundingRect().width() >= 30
    item.set_text_width(None)
    assert item.has_fixed_width() is False


def test_text_item_default_background(qapp):
    item = BeeTextItem('foo')
    assert item.background_color() == item.default_background_color()
    item.set_background('nonsense')
    assert item.background_color() == item.default_background_color()


def test_create_copy_keeps_format(qapp):
    item = BeeTextItem('foo')
    cursor = select_all(item)
    textformat.italic(textformat.reference_format(cursor))(cursor)
    item.set_text_width(80)
    item.set_background('#ff00ff00')
    copy = item.create_copy()
    assert first_format(copy).fontItalic()
    assert copy.textWidth() == 80
    assert copy.background == '#ff00ff00'


def test_change_text_with_width(qapp):
    item = BeeTextItem('foo')
    command = commands.ChangeText(item, '<i>bar</i>', item.html(), 50, -1)
    command.redo()
    assert item.toPlainText() == 'bar'
    assert item.textWidth() == 50
    command.undo()
    assert item.toPlainText() == 'foo'
    assert item.has_fixed_width() is False


def test_change_note_background(qapp):
    item1 = BeeTextItem('foo')
    item2 = BeeTextItem('bar', background='#ff0000ff')
    command = commands.ChangeNoteBackground([item1, item2], '#ffff0000')
    command.redo()
    assert item1.background == '#ffff0000'
    assert item2.background == '#ffff0000'
    command.undo()
    assert item1.background is None
    assert item2.background == '#ff0000ff'


def test_edit_mode_commits_format_and_width_in_one_undo_step(view):
    item = BeeTextItem('foo')
    edit(view, item)
    view.on_action_text_bold()
    item.set_text_width(120)
    item.exit_edit_mode()
    assert textformat.is_bold(first_format(item))
    assert item.textWidth() == 120
    view.undo_stack.undo()
    assert not textformat.is_bold(first_format(item))
    assert item.has_fixed_width() is False


def test_cancel_edit_mode_restores_format_and_width(view):
    item = BeeTextItem('foo')
    edit(view, item)
    view.on_action_text_italic()
    item.set_text_width(120)
    item.exit_edit_mode(commit=False)
    assert not first_format(item).fontItalic()
    assert item.has_fixed_width() is False


def test_shift_enter_creates_new_list_item(view):
    item = BeeTextItem('foo')
    edit(view, item)
    view.on_action_text_bullet_list()
    cursor = item.textCursor()
    cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
    item.setTextCursor(cursor)
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_Return,
                            Qt.KeyboardModifier.ShiftModifier)
    item.keyPressEvent(event)
    doc = item.document()
    assert doc.blockCount() == 2
    assert doc.lastBlock().textList() is doc.begin().textList()


def test_tab_indents_list_item(view):
    item = BeeTextItem('foo')
    edit(view, item)
    view.on_action_text_bullet_list()
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_Tab,
                            Qt.KeyboardModifier.NoModifier)
    item.keyPressEvent(event)
    assert item.document().begin().textList().format().indent() == 2
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_Backtab,
                            Qt.KeyboardModifier.ShiftModifier)
    item.keyPressEvent(event)
    assert item.document().begin().textList().format().indent() == 1


def test_mouse_press_on_checkbox_in_edit_mode_toggles_it(view):
    item = BeeTextItem('foo')
    edit(view, item)
    view.on_action_text_checklist()
    block = item.document().begin()
    layout = block.layout()
    rect = item.document().documentLayout().blockBoundingRect(block)
    pos = QtCore.QPointF(layout.position().x() + layout.lineAt(0).x() - 5,
                         rect.center().y())
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    event.pos.return_value = pos
    item.mousePressEvent(event)
    assert (item.document().begin().blockFormat().marker()
            == textformat.MarkerType.Checked)
    event.accept.assert_called_once_with()


def test_width_handle_drag_in_edit_mode(view):
    item = BeeTextItem('foo bar baz')
    edit(view, item)
    rect = QtWidgets.QGraphicsTextItem.boundingRect(item)
    assert item.is_on_width_handle(
        QtCore.QPointF(rect.right() - 1, rect.center().y()))
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    event.pos.return_value = QtCore.QPointF(rect.right() - 1,
                                            rect.center().y())
    item.mousePressEvent(event)
    assert item.width_drag_start is not None
    event.pos.return_value = QtCore.QPointF(40, rect.center().y())
    item.mouseMoveEvent(event)
    assert item.textWidth() == 40
    item.mouseReleaseEvent(event)
    assert item.width_drag_start is None


def test_no_width_handle_outside_edit_mode(view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    rect = QtWidgets.QGraphicsTextItem.boundingRect(item)
    assert not item.is_on_width_handle(
        QtCore.QPointF(rect.right() - 1, rect.center().y()))


# View actions

def test_format_multiple_selected_notes_with_undo(view):
    item1 = BeeTextItem('foo')
    item2 = BeeTextItem('bar')
    image = BeePixmapItem(
        QtGui.QImage(10, 10, QtGui.QImage.Format.Format_RGB32))
    for item in (item1, item2, image):
        view.scene.addItem(item)
        item.setSelected(True)
    view.on_action_text_bold()
    assert textformat.is_bold(first_format(item1))
    assert textformat.is_bold(first_format(item2))
    view.undo_stack.undo()
    assert not textformat.is_bold(first_format(item1))
    assert not textformat.is_bold(first_format(item2))


def test_format_notes_inside_selected_group(view):
    item1 = BeeTextItem('foo')
    item2 = BeeTextItem('bar')
    for item in (item1, item2):
        view.scene.addItem(item)
        item.setSelected(True)
    view.scene.group_selection()
    assert view.selected_text_items() == [item1, item2] or (
        set(view.selected_text_items()) == {item1, item2})
    view.on_action_text_italic()
    assert first_format(item1).fontItalic()
    assert first_format(item2).fontItalic()


def test_text_actions_enabled_with_note_selection(view):
    from myRef.actions.actions import actions
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    view.on_selection_changed()
    assert actions['text_bold'].qaction.isEnabled() is False
    item.setSelected(True)
    assert actions['text_bold'].qaction.isEnabled() is True


def test_text_alignment_and_lists_actions(view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_text_align_center()
    assert (item.document().begin().blockFormat().alignment()
            == Qt.AlignmentFlag.AlignHCenter)
    view.on_action_text_align_right()
    view.on_action_text_align_left()
    assert (item.document().begin().blockFormat().alignment()
            == Qt.AlignmentFlag.AlignLeft)
    view.on_action_text_numbered_list()
    assert item.document().begin().textList()
    view.on_action_text_indent()
    assert item.document().begin().textList().format().indent() == 2
    view.on_action_text_dedent()
    assert item.document().begin().textList().format().indent() == 1


def test_text_color_actions(view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    item.setSelected(True)
    with patch('PyQt6.QtWidgets.QColorDialog.getColor',
               return_value=QtGui.QColor('red')):
        view.on_action_text_color()
        view.on_action_text_highlight()
        view.on_action_note_background()
    fmt = first_format(item)
    assert fmt.foreground().color() == QtGui.QColor('red')
    assert fmt.background().color() == QtGui.QColor('red')
    assert item.background_color() == QtGui.QColor('red')
    view.undo_stack.undo()
    assert item.background is None


def test_text_color_action_cancelled(view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    item.setSelected(True)
    old = item.html()
    with patch('PyQt6.QtWidgets.QColorDialog.getColor',
               return_value=QtGui.QColor()):
        view.on_action_text_color()
        view.on_action_note_background()
    assert item.html() == old
    assert item.background is None


def test_text_link_action(view):
    item = BeeTextItem('foo')
    edit(view, item)
    with patch('PyQt6.QtWidgets.QInputDialog.getText',
               return_value=('https://example.com', True)):
        view.on_action_text_link()
    assert first_format(item).anchorHref() == 'https://example.com'


def test_text_paste_plain(view):
    QtWidgets.QApplication.clipboard().setText('pasted')
    item = BeeTextItem('foo')
    edit(view, item)
    view.on_action_text_paste_plain()
    assert item.toPlainText() == 'pasted'


def test_text_paste_plain_when_not_editing_does_nothing(view):
    QtWidgets.QApplication.clipboard().setText('pasted')
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_text_paste_plain()
    assert item.toPlainText() == 'foo'


def test_copy_and_paste_format_actions(view):
    source = BeeTextItem('foo')
    target = BeeTextItem('bar')
    view.scene.addItem(source)
    view.scene.addItem(target)
    source.setSelected(True)
    view.on_action_text_underline()
    view.on_action_text_copy_format()
    view.scene.select_items([target])
    view.on_action_text_paste_format()
    assert first_format(target).fontUnderline()
    view.on_action_text_clear_format()
    assert not first_format(target).fontUnderline()


def test_fixed_width_action_on_selected_notes(view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_text_fixed_width()
    assert item.has_fixed_width() is True
    view.on_action_text_fixed_width()
    assert item.has_fixed_width() is False
    view.undo_stack.undo()
    assert item.has_fixed_width() is True


def test_fixed_width_action_in_edit_mode(view):
    item = BeeTextItem('foo bar')
    edit(view, item)
    view.on_action_text_fixed_width()
    assert item.has_fixed_width() is True


def test_insert_text_with_selected_image_parents_note(view):
    image = BeePixmapItem(
        QtGui.QImage(10, 10, QtGui.QImage.Format.Format_RGB32))
    view.scene.addItem(image)
    image.setSelected(True)
    view.on_action_insert_text()
    notes = list(view.scene.items_by_type('text'))
    assert len(notes) == 1
    assert notes[0].parentItem() is image
    view.undo_stack.undo()
    assert list(view.scene.items_by_type('text')) == []


def test_insert_text_without_selection_is_top_level(view):
    view.on_action_insert_text()
    notes = list(view.scene.items_by_type('text'))
    assert len(notes) == 1
    assert notes[0].parentItem() is None


@patch('PyQt6.QtGui.QDesktopServices.openUrl')
def test_open_link_external(open_mock, view):
    view.open_link('https://example.com')
    open_mock.assert_called_once_with(QtCore.QUrl('https://example.com'))


@patch('myRef.view.BeeGraphicsView.on_action_open_recent_file')
@patch('PyQt6.QtGui.QDesktopServices.openUrl')
def test_open_link_bee_file(open_mock, recent_mock, view, tmpdir):
    filename = str(tmpdir / 'foo.bee')
    view.open_link(QtCore.QUrl.fromLocalFile(filename).toString())
    recent_mock.assert_called_once()
    assert recent_mock.call_args[0][0].endswith('foo.bee')
    open_mock.assert_not_called()


def test_scene_link_at_and_ctrl_click(view):
    item = BeeTextItem('foo')
    textformat.link('https://example.com')(select_all(item))
    view.scene.addItem(item)
    rect = item.document().documentLayout().blockBoundingRect(
        item.document().begin())
    pos = item.mapToScene(QtCore.QPointF(rect.left() + 3,
                                         rect.center().y()))
    assert view.scene.link_at(pos) == 'https://example.com'
    assert view.scene.link_at(QtCore.QPointF(-500, -500)) is None
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.ControlModifier
    event.scenePos.return_value = pos
    with patch.object(view, 'open_link') as open_mock:
        view.scene.mousePressEvent(event)
    open_mock.assert_called_once_with('https://example.com')
    assert not item.isSelected()


# Toolbars

def test_toolbar_shown_while_editing(view):
    item = BeeTextItem('foo')
    edit(view, item)
    assert isinstance(view.text_toolbar, NoteFormatToolbar)
    assert view.text_toolbar.isVisibleTo(view)
    item.exit_edit_mode()
    assert not view.text_toolbar.isVisibleTo(view)


def test_toolbar_buttons_format_edited_note(view):
    item = BeeTextItem('foo')
    edit(view, item)
    toolbar = view.text_toolbar
    toolbar.buttons['bold'].click()
    assert textformat.is_bold(first_format(item))
    assert toolbar.buttons['bold'].isChecked()
    toolbar.buttons['checklist'].click()
    assert toolbar.buttons['checklist'].isChecked()
    toolbar.buttons['fixed_width'].click()
    assert item.has_fixed_width()
    assert toolbar.buttons['fixed_width'].isChecked()
    toolbar.size_box.setValue(33)
    assert first_format(item).fontPointSize() == 33


def test_toolbar_follows_item(view):
    item = BeeTextItem('foo')
    edit(view, item)
    toolbar = view.text_toolbar
    toolbar.follow_item()
    view.scene.edit_item = None
    toolbar.follow_item()
    assert not toolbar.isVisibleTo(view)


def test_editor_toolbar_formats_text_edit(qapp):
    editor = QtWidgets.QTextEdit()
    editor.setPlainText('foo')
    editor.selectAll()
    toolbar = TextFormatToolbar(EditorTarget(editor), for_notes=False)
    assert 'background' not in toolbar.buttons
    assert 'fixed_width' not in toolbar.buttons
    toolbar.buttons['italic'].click()
    toolbar.buttons['bullet_list'].click()
    cursor = QtGui.QTextCursor(editor.document())
    cursor.setPosition(1)
    assert cursor.charFormat().fontItalic()
    assert editor.document().begin().textList()


def test_comment_dialog_has_toolbar(view):
    from myRef.widgets.hierarchy import CommentDialog
    dialog = CommentDialog(view, '<b>hi</b>')
    assert isinstance(dialog.toolbar, TextFormatToolbar)
    assert 'hi' in dialog.comment()


def test_toolbar_retranslate_on_language_change(view):
    item = BeeTextItem('foo')
    edit(view, item)
    with patch.object(view.text_toolbar, 'retranslate') as retranslate:
        view.on_language_changed()
    retranslate.assert_called_once_with()
