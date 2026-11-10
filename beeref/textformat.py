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

"""Rich text formatting for text notes and comments.

Most functions here return an operation: A callable that takes a
QTextCursor and applies the formatting to the cursor's selection (or,
without a selection, to the text typed next). The same operation can
be applied to the cursor of the note being edited, or to the whole
document of several notes at once.
"""

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt


MarkerType = QtGui.QTextBlockFormat.MarkerType
ListStyle = QtGui.QTextListFormat.Style

WEIGHT_NORMAL = QtGui.QFont.Weight.Normal.value
WEIGHT_BOLD = QtGui.QFont.Weight.Bold.value

LINK_COLOR = QtGui.QColor(80, 160, 255)

# Format copied with "Copy Format", see copy_format/paste_format
copied_format = None


def reference_format(cursor):
    """The character format the formatting state is read from: The
    first selected character, or the format at the cursor."""

    if cursor.hasSelection():
        ref = QtGui.QTextCursor(cursor)
        ref.setPosition(cursor.selectionStart() + 1)
        return ref.charFormat()
    return cursor.charFormat()


def reference_block_format(cursor):
    ref = QtGui.QTextCursor(cursor)
    ref.setPosition(cursor.selectionStart())
    return ref.blockFormat()


def is_bold(fmt):
    return fmt.fontWeight() > WEIGHT_NORMAL


def merge(fmt):
    """Operation that merges the given character format."""

    def operation(cursor):
        cursor.mergeCharFormat(fmt)
    return operation


def bold(ref):
    """Toggle bold, depending on the reference format."""

    fmt = QtGui.QTextCharFormat()
    fmt.setFontWeight(WEIGHT_NORMAL if is_bold(ref) else WEIGHT_BOLD)
    return merge(fmt)


def italic(ref):
    fmt = QtGui.QTextCharFormat()
    fmt.setFontItalic(not ref.fontItalic())
    return merge(fmt)


def underline(ref):
    fmt = QtGui.QTextCharFormat()
    fmt.setFontUnderline(not ref.fontUnderline())
    return merge(fmt)


def strikeout(ref):
    fmt = QtGui.QTextCharFormat()
    fmt.setFontStrikeOut(not ref.fontStrikeOut())
    return merge(fmt)


def foreground(color):
    fmt = QtGui.QTextCharFormat()
    fmt.setForeground(QtGui.QBrush(QtGui.QColor(color)))
    return merge(fmt)


def highlight(color):
    """Background color of the text; an invalid or transparent color
    removes the highlight."""

    color = QtGui.QColor(color)
    fmt = QtGui.QTextCharFormat()
    if color.isValid() and color.alpha():
        fmt.setBackground(QtGui.QBrush(color))
    else:
        fmt.setBackground(QtGui.QBrush(Qt.BrushStyle.NoBrush))
    return merge(fmt)


def font_family(family):
    fmt = QtGui.QTextCharFormat()
    fmt.setFontFamilies([family])
    return merge(fmt)


def font_size(size):
    fmt = QtGui.QTextCharFormat()
    fmt.setFontPointSize(float(size))
    return merge(fmt)


def align(alignment):
    def operation(cursor):
        fmt = QtGui.QTextBlockFormat()
        fmt.setAlignment(alignment)
        cursor.mergeBlockFormat(fmt)
    return operation


def blocks(cursor):
    """All text blocks touched by the cursor's selection."""

    doc = cursor.document()
    block = doc.findBlock(cursor.selectionStart())
    end = doc.findBlock(cursor.selectionEnd())
    while block.isValid():
        yield block
        if block == end:
            break
        block = block.next()


def set_marker(block, marker):
    cursor = QtGui.QTextCursor(block)
    fmt = block.blockFormat()
    fmt.setMarker(marker)
    cursor.setBlockFormat(fmt)


def is_checklist_block(block):
    return (block.textList() is not None
            and block.blockFormat().marker() != MarkerType.NoMarker)


def remove_from_list(cursor):
    cursor.beginEditBlock()
    for block in list(blocks(cursor)):
        text_list = block.textList()
        if text_list:
            text_list.remove(block)
        block_cursor = QtGui.QTextCursor(block)
        fmt = block.blockFormat()
        fmt.setIndent(0)
        fmt.setMarker(MarkerType.NoMarker)
        block_cursor.setBlockFormat(fmt)
    cursor.endEditBlock()


def toggle_list(style, checklist=False):
    """Turn the selected paragraphs into a list of the given style, or
    back into normal paragraphs if they are such a list already.

    A checklist is a bullet list whose items have a check box marker.
    """

    def operation(cursor):
        current = cursor.currentList()
        block = cursor.document().findBlock(cursor.selectionStart())
        if (current and current.format().style() == style
                and is_checklist_block(block) == checklist):
            remove_from_list(cursor)
            return
        cursor.beginEditBlock()
        fmt = QtGui.QTextListFormat()
        fmt.setStyle(style)
        fmt.setIndent(current.format().indent() if current else 1)
        cursor.createList(fmt)
        for block in list(blocks(cursor)):
            marker = block.blockFormat().marker()
            if not checklist:
                marker = MarkerType.NoMarker
            elif marker == MarkerType.NoMarker:
                marker = MarkerType.Unchecked
            set_marker(block, marker)
        cursor.endEditBlock()
    return operation


def bullet_list():
    return toggle_list(ListStyle.ListDisc)


def numbered_list():
    return toggle_list(ListStyle.ListDecimal)


def checklist():
    return toggle_list(ListStyle.ListDisc, checklist=True)


def indent(delta):
    """Increase (delta > 0) or decrease (delta < 0) the indentation.

    List items get moved to a list one level deeper or higher; items on
    the first level that get dedented are removed from the list.
    """

    def operation(cursor):
        text_list = cursor.currentList()
        if text_list:
            fmt = QtGui.QTextListFormat(text_list.format())
            new_indent = fmt.indent() + delta
            if new_indent < 1:
                remove_from_list(cursor)
                return
            fmt.setIndent(new_indent)
            cursor.createList(fmt)
            return
        cursor.beginEditBlock()
        for block in list(blocks(cursor)):
            block_cursor = QtGui.QTextCursor(block)
            fmt = block.blockFormat()
            fmt.setIndent(max(0, fmt.indent() + delta))
            block_cursor.setBlockFormat(fmt)
        cursor.endEditBlock()
    return operation


def clear_format():
    """Remove all character formatting (including links)."""

    def operation(cursor):
        cursor.setCharFormat(QtGui.QTextCharFormat())
    return operation


def copy_format(cursor):
    """Remember the format at the cursor for paste_format."""

    global copied_format
    char_format = QtGui.QTextCharFormat(reference_format(cursor))
    char_format.setAnchor(False)
    char_format.clearProperty(QtGui.QTextFormat.Property.AnchorHref)
    copied_format = (char_format,
                     reference_block_format(cursor).alignment())
    return copied_format


def paste_format(fmt=None):
    """Apply a format copied with copy_format."""

    fmt = fmt or copied_format

    def operation(cursor):
        if fmt is None:
            return
        char_format, alignment = fmt
        cursor.beginEditBlock()
        cursor.setCharFormat(char_format)
        align(alignment)(cursor)
        cursor.endEditBlock()
    return operation


def normalize_url(url):
    url = url.strip()
    if not url:
        return url
    qurl = QtCore.QUrl.fromUserInput(url)
    return qurl.toString() if qurl.isValid() else url


def link(url):
    """Make the selected text a link, or insert the URL as a link if
    nothing is selected."""

    url = normalize_url(url)

    def operation(cursor):
        if not url:
            return
        fmt = QtGui.QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setForeground(QtGui.QBrush(LINK_COLOR))
        fmt.setFontUnderline(True)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
            return
        plain = QtGui.QTextCharFormat(cursor.charFormat())
        cursor.insertText(url, fmt)
        # Text typed after the link shouldn't be part of it:
        plain.setAnchor(False)
        plain.clearProperty(QtGui.QTextFormat.Property.AnchorHref)
        cursor.setCharFormat(plain)
    return operation


def anchor_at(document, pos):
    """The link target at the given position in document coordinates."""

    return document.documentLayout().anchorAt(pos) or None


def checkbox_at(document, pos):
    """The checklist block whose check box is at the given position in
    document coordinates, or None."""

    layout = document.documentLayout()
    block = document.begin()
    while block.isValid():
        if is_checklist_block(block):
            rect = layout.blockBoundingRect(block)
            text_layout = block.layout()
            text_left = text_layout.position().x()
            if text_layout.lineCount():
                text_left += text_layout.lineAt(0).x()
            if (rect.top() <= pos.y() <= rect.bottom()
                    and rect.left() - 4 <= pos.x() < text_left):
                return block
        block = block.next()
    return None


def toggle_checkbox(block):
    marker = block.blockFormat().marker()
    set_marker(block, MarkerType.Checked if marker == MarkerType.Unchecked
               else MarkerType.Unchecked)
