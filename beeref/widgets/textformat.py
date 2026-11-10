# This file is part of BeeRef.
#
# BeeRef is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BeeRef is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BeeRef.  If not, see <https://www.gnu.org/licenses/>.

"""Formatting toolbar for text notes and comments."""

import logging

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref import textformat
from beeref.i18n import _


logger = logging.getLogger(__name__)


class EditorTarget:
    """Applies formatting to a QTextEdit."""

    def __init__(self, editor):
        self.editor = editor

    def cursor(self):
        return self.editor.textCursor()

    def apply(self, operation):
        cursor = self.editor.textCursor()
        operation(cursor)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def ask_color(self, title, initial):
        return QtWidgets.QColorDialog.getColor(
            initial, self.editor, title,
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)

    def ask_link(self):
        url, ok = QtWidgets.QInputDialog.getText(
            self.editor, _('Insert Link'), _('URL:'))
        return url if ok else None


class TextFormatToolbar(QtWidgets.QFrame):
    """Buttons for formatting text.

    :param target: Object with the methods ``cursor()`` (the cursor the
        formatting state is read from) and ``apply(operation)``.
    :param for_notes: Whether to show the buttons that only make sense
        for text notes (background color, fixed width).
    """

    def __init__(self, target, parent=None, for_notes=True):
        super().__init__(parent)
        self.target = target
        self.for_notes = for_notes
        self.updating = False
        self.setObjectName('TextFormatToolbar')
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(1)
        self.buttons = {}

        self.font_box = QtWidgets.QFontComboBox()
        self.font_box.setMaximumWidth(150)
        self.font_box.textActivated.connect(self.on_font_family)
        layout.addWidget(self.font_box)
        self.size_box = QtWidgets.QSpinBox()
        self.size_box.setRange(4, 400)
        self.size_box.setKeyboardTracking(False)
        self.size_box.setMinimumWidth(52)
        self.size_box.valueChanged.connect(self.on_font_size)
        layout.addWidget(self.size_box)

        self.add_button(layout, 'bold', 'B', self.on_bold, checkable=True,
                        font={'bold': True})
        self.add_button(layout, 'italic', 'I', self.on_italic,
                        checkable=True, font={'italic': True})
        self.add_button(layout, 'underline', 'U', self.on_underline,
                        checkable=True, font={'underline': True})
        self.add_button(layout, 'strikeout', 'S', self.on_strikeout,
                        checkable=True, font={'strikeout': True})
        self.add_separator(layout)
        self.add_button(layout, 'color', 'A', self.on_color)
        self.add_button(layout, 'highlight', '▒', self.on_highlight)
        if for_notes:
            self.add_button(layout, 'background', '▧',
                            self.on_background)
        self.add_separator(layout)
        self.add_button(layout, 'align_left', '⭰', self.on_align_left,
                        checkable=True)
        self.add_button(layout, 'align_center', '≡',
                        self.on_align_center, checkable=True)
        self.add_button(layout, 'align_right', '⭲',
                        self.on_align_right, checkable=True)
        self.add_separator(layout)
        self.add_button(layout, 'bullet_list', '•', self.on_bullet_list,
                        checkable=True)
        self.add_button(layout, 'numbered_list', '1.',
                        self.on_numbered_list, checkable=True)
        self.add_button(layout, 'checklist', '☑', self.on_checklist,
                        checkable=True)
        self.add_button(layout, 'dedent', '⇤', self.on_dedent)
        self.add_button(layout, 'indent', '⇥', self.on_indent)
        self.add_separator(layout)
        self.add_button(layout, 'link', '\U0001F517', self.on_link)
        self.add_button(layout, 'clear_format', '∅',
                        self.on_clear_format)
        if for_notes:
            self.add_button(layout, 'fixed_width', '↩',
                            self.on_fixed_width, checkable=True)
        self.retranslate()
        self.update_state()

    def add_button(self, layout, name, text, callback, checkable=False,
                   font=None):
        button = QtWidgets.QToolButton()
        button.setText(text)
        button.setCheckable(checkable)
        button.setAutoRaise(True)
        # Keep the focus in the text that is being edited:
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setMinimumWidth(24)
        if font:
            qfont = button.font()
            qfont.setBold(font.get('bold', False))
            qfont.setItalic(font.get('italic', False))
            qfont.setUnderline(font.get('underline', False))
            qfont.setStrikeOut(font.get('strikeout', False))
            button.setFont(qfont)
        button.clicked.connect(lambda checked=False: callback())
        layout.addWidget(button)
        self.buttons[name] = button
        return button

    def add_separator(self, layout):
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(line)

    def retranslate(self):
        tooltips = {
            'bold': _('Bold'),
            'italic': _('Italic'),
            'underline': _('Underline'),
            'strikeout': _('Strikethrough'),
            'color': _('Text color'),
            'highlight': _('Highlight color'),
            'background': _('Note background'),
            'align_left': _('Align left'),
            'align_center': _('Align center'),
            'align_right': _('Align right'),
            'bullet_list': _('Bullet list'),
            'numbered_list': _('Numbered list'),
            'checklist': _('Checklist'),
            'dedent': _('Decrease indent'),
            'indent': _('Increase indent'),
            'link': _('Link'),
            'clear_format': _('Clear formatting'),
            'fixed_width': _('Fixed width with word wrap'),
        }
        for name, button in self.buttons.items():
            button.setToolTip(tooltips[name])
        self.font_box.setToolTip(_('Font'))
        self.size_box.setToolTip(_('Font size'))

    # State

    def reference_format(self):
        return textformat.reference_format(self.target.cursor())

    def update_state(self):
        """Show the format at the cursor in the buttons."""

        cursor = self.target.cursor()
        if cursor is None:
            return
        self.updating = True
        fmt = textformat.reference_format(cursor)
        self.buttons['bold'].setChecked(textformat.is_bold(fmt))
        self.buttons['italic'].setChecked(fmt.fontItalic())
        self.buttons['underline'].setChecked(fmt.fontUnderline())
        self.buttons['strikeout'].setChecked(fmt.fontStrikeOut())
        alignment = textformat.reference_block_format(cursor).alignment()
        horizontal = alignment & Qt.AlignmentFlag.AlignHorizontal_Mask
        self.buttons['align_center'].setChecked(
            horizontal == Qt.AlignmentFlag.AlignHCenter)
        self.buttons['align_right'].setChecked(
            horizontal == Qt.AlignmentFlag.AlignRight)
        self.buttons['align_left'].setChecked(
            horizontal not in (Qt.AlignmentFlag.AlignHCenter,
                               Qt.AlignmentFlag.AlignRight))
        text_list = cursor.currentList()
        block = cursor.document().findBlock(cursor.selectionStart())
        style = text_list.format().style() if text_list else None
        is_check = textformat.is_checklist_block(block)
        self.buttons['bullet_list'].setChecked(
            style == textformat.ListStyle.ListDisc and not is_check)
        self.buttons['numbered_list'].setChecked(
            style == textformat.ListStyle.ListDecimal)
        self.buttons['checklist'].setChecked(is_check)
        if not self.font_box.hasFocus():
            families = fmt.fontFamilies()
            family = (families[0] if families
                      else cursor.document().defaultFont().family())
            self.font_box.setCurrentFont(QtGui.QFont(family))
        if not self.size_box.hasFocus():
            size = fmt.fontPointSize()
            if not size:
                size = cursor.document().defaultFont().pointSizeF()
            self.size_box.setValue(max(1, round(size)))
        if 'fixed_width' in self.buttons:
            self.buttons['fixed_width'].setChecked(
                bool(getattr(self.target, 'has_fixed_width', lambda: False)()))
        self.updating = False

    def apply(self, operation):
        self.target.apply(operation)
        self.update_state()

    # Callbacks

    def on_bold(self):
        self.apply(textformat.bold(self.reference_format()))

    def on_italic(self):
        self.apply(textformat.italic(self.reference_format()))

    def on_underline(self):
        self.apply(textformat.underline(self.reference_format()))

    def on_strikeout(self):
        self.apply(textformat.strikeout(self.reference_format()))

    def on_font_family(self, family):
        if not self.updating:
            self.apply(textformat.font_family(family))

    def on_font_size(self, size):
        if not self.updating:
            self.apply(textformat.font_size(size))

    def on_color(self):
        fmt = self.reference_format()
        color = self.target.ask_color(_('Text Color'),
                                      fmt.foreground().color())
        if color and color.isValid():
            self.apply(textformat.foreground(color))

    def on_highlight(self):
        fmt = self.reference_format()
        color = self.target.ask_color(_('Highlight Color'),
                                      fmt.background().color())
        if color and color.isValid():
            self.apply(textformat.highlight(color))

    def on_background(self):
        self.target.change_background()

    def on_align_left(self):
        self.apply(textformat.align(Qt.AlignmentFlag.AlignLeft))

    def on_align_center(self):
        self.apply(textformat.align(Qt.AlignmentFlag.AlignHCenter))

    def on_align_right(self):
        self.apply(textformat.align(Qt.AlignmentFlag.AlignRight))

    def on_bullet_list(self):
        self.apply(textformat.bullet_list())

    def on_numbered_list(self):
        self.apply(textformat.numbered_list())

    def on_checklist(self):
        self.apply(textformat.checklist())

    def on_indent(self):
        self.apply(textformat.indent(1))

    def on_dedent(self):
        self.apply(textformat.indent(-1))

    def on_link(self):
        url = self.target.ask_link()
        if url:
            self.apply(textformat.link(url))

    def on_clear_format(self):
        self.apply(textformat.clear_format())

    def on_fixed_width(self):
        self.target.toggle_fixed_width()
        self.update_state()


class NoteTarget:
    """Applies formatting to the text note being edited, via the view."""

    def __init__(self, view):
        self.view = view

    def cursor(self):
        return self.view.text_format_cursor()

    def apply(self, operation):
        self.view.apply_text_format(operation)

    def ask_color(self, title, initial):
        return self.view.ask_color(title, initial)

    def ask_link(self):
        return self.view.ask_link()

    def change_background(self):
        self.view.on_action_note_background()

    def toggle_fixed_width(self):
        self.view.on_action_text_fixed_width()

    def has_fixed_width(self):
        item = self.view.scene.edit_item
        return item is not None and item.has_fixed_width()


class NoteFormatToolbar(TextFormatToolbar):
    """Toolbar floating above the text note that is being edited."""

    def __init__(self, view):
        super().__init__(NoteTarget(view), parent=view, for_notes=True)
        self.view = view
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.follow_item)
        self.hide()

    def show_for_item(self):
        self.adjustSize()
        self.follow_item()
        self.show()
        self.raise_()
        self.timer.start()

    def hide_toolbar(self):
        self.timer.stop()
        self.hide()

    def follow_item(self):
        """Keep the toolbar next to the edited item and up to date."""

        item = self.view.scene.edit_item
        if item is None:
            self.hide_toolbar()
            return
        rect = self.view.mapFromScene(
            item.sceneBoundingRect()).boundingRect()
        size = self.sizeHint()
        x = rect.left()
        y = rect.top() - size.height() - 6
        if y < 0:
            y = rect.bottom() + 6
        x = max(0, min(x, self.view.width() - size.width()))
        y = max(0, min(y, self.view.height() - size.height()))
        if self.pos() != QtCore.QPoint(x, y):
            self.move(x, y)
        self.update_state()
