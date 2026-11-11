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

"""The dialog for the look of groups."""

from functools import partial
import logging
import math

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef import commands
from myRef import group_style
from myRef.i18n import _
from myRef.widgets.color_field import ColorField
from myRef.widgets.dragspin import DragDoubleSpinBox


logger = logging.getLogger(__name__)


class GroupTitleEditor(QtWidgets.QLineEdit):
    """A text field over a group's title, to edit it in place.

    Enter or clicking elsewhere applies the new title, Escape discards
    it. Clicking into the title panel keeps the field open.
    """

    def __init__(self, view, group, click=None):
        super().__init__(view.viewport())
        self.view = view
        self.group = group
        self.cancelled = False
        self.finished = False
        self.setText(group.display_name())
        self.setFrame(False)
        self.update_color()
        alignment = {
            'left': Qt.AlignmentFlag.AlignLeft,
            'center': Qt.AlignmentFlag.AlignHCenter,
            'right': Qt.AlignmentFlag.AlignRight,
        }[group_style.title_alignment(group.style['title_position'])]
        self.setAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
        group.editing_title = True
        group.editing_text = self.text()
        group.update()
        self.update_geometry()
        self.textChanged.connect(self.on_text_changed)
        self.returnPressed.connect(self.finish)
        for bar in (view.horizontalScrollBar(), view.verticalScrollBar()):
            bar.valueChanged.connect(self.update_geometry)
        self.show()
        self.setFocus()
        if click is None:
            self.selectAll()
        else:
            self.setCursorPosition(
                self.cursorPositionAt(self.mapFrom(view.viewport(), click)))

    def update_color(self):
        color = QtGui.QColor(self.group.style['title_color'])
        color.setAlpha(255)
        self.setStyleSheet(
            f'QLineEdit {{ background: rgba(30, 30, 30, 215);'
            f' color: {color.name()}; border: 1px solid #5a9fe2;'
            f' padding: 0px 2px; }}')

    def style_changed(self):
        """The title's look has changed (e.g. in the text options):
        Show the text the same way."""

        self.update_color()
        self.update_geometry()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self.view.edit_group_title_style(self.group)

    def on_text_changed(self, text):
        self.group.editing_text = text
        self.group.update()
        self.update_geometry()

    def update_geometry(self, *args):
        """Place the field over the title, following the zoom and the
        text."""

        if self.finished:
            return
        transform = self.group.deviceTransform(
            self.view.viewportTransform())
        scale = max(math.hypot(transform.m11(), transform.m12()), 0.0001)
        font = QtGui.QFont(group_style.title_font(self.group.style))
        font.setPixelSize(max(1, round(self.group.style['title_size']
                                       * scale)))
        self.setFont(font)
        rect = transform.mapRect(self.group.title_text_rect())
        if group_style.title_side(
                self.group.style['title_position']) in ('left', 'right'):
            # The field is always horizontal
            center = rect.center()
            rect = QtCore.QRectF(0, 0, rect.height(), rect.width())
            rect.moveCenter(center)
        rect.setWidth(max(rect.width(), 24))
        self.setGeometry(rect.toAlignedRect().adjusted(-3, -2, 3, 2))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled = True
            self.finish()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if event.reason() not in (Qt.FocusReason.ActiveWindowFocusReason,
                                  Qt.FocusReason.PopupFocusReason):
            self.finish()

    def finish(self):
        if self.finished:
            return
        self.finished = True
        group = self.group
        group.editing_title = False
        group.editing_text = None
        group.update()
        if not self.cancelled:
            name = self.text().strip()
            if name == group.default_name():
                name = ''
            if name != group.name:
                self.view.undo_stack.push(commands.RenameItem(group, name))
        if self.view.title_editor is self:
            self.view.title_editor = None
        self.hide()
        self.deleteLater()
        self.view.viewport().setFocus()


class GroupTitlePanel(QtWidgets.QDialog):
    """Floating panel with the text options of a group's title.

    Changes show up right away. They are put on the undo stack as one
    step when the panel closes (which happens when the title is
    deselected).
    """

    def __init__(self, view, group, undo_stack):
        super().__init__(view.window())
        self.view = view
        self.group = group
        self.undo_stack = undo_stack
        self.command = commands.ChangeGroupStyle(
            [group], text='Change title text')
        self.committed = False
        self.setWindowTitle(_('Title Text'))
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        style = group.get_style()
        layout = QtWidgets.QFormLayout(self)

        self.font_input = QtWidgets.QFontComboBox()
        self.font_input.currentFontChanged.connect(self.on_font_changed)
        layout.addRow(_('Font:'), self.font_input)

        self.size_input = DragDoubleSpinBox()
        self.size_input.setRange(1, group_style.MAX_TITLE_SIZE)
        self.size_input.setDecimals(1)
        self.size_input.valueChanged.connect(
            partial(self.set_value, 'title_size'))
        layout.addRow(_('Title size:'), self.size_input)

        self.bold_input = QtWidgets.QCheckBox(_('Bold'))
        self.bold_input.toggled.connect(partial(self.set_value, 'title_bold'))
        self.italic_input = QtWidgets.QCheckBox(_('Italic'))
        self.italic_input.toggled.connect(
            partial(self.set_value, 'title_italic'))
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.bold_input)
        row.addWidget(self.italic_input)
        layout.addRow(row)

        self.color_input = ColorField(
            style['title_color'], _('Title Color'), self)
        self.color_input.callback = partial(self.set_value, 'title_color')
        layout.addRow(_('Title color:'), self.color_input)

        self.refresh()
        self.place()
        self.show()

    def refresh(self):
        """Show the group's current values."""

        style = self.group.style
        widgets_ = (self.font_input, self.size_input,
                    self.bold_input, self.italic_input)
        for widget in widgets_:
            widget.blockSignals(True)
        font = QtGui.QFont(style['title_family'] or self.font().family())
        self.font_input.setCurrentFont(font)
        self.size_input.setValue(style['title_size'])
        self.bold_input.setChecked(style['title_bold'])
        self.italic_input.setChecked(style['title_italic'])
        for widget in widgets_:
            widget.blockSignals(False)

    def place(self):
        """Next to the group, not covering the title."""

        view = self.view
        transform = self.group.deviceTransform(view.viewportTransform())
        rect = transform.mapRect(self.group.bounding_rect_unselected())
        size = self.sizeHint()
        right = view.viewport().mapToGlobal(
            QtCore.QPoint(int(rect.right()) + 12, int(rect.top())))
        left = view.viewport().mapToGlobal(
            QtCore.QPoint(int(rect.left()) - 12 - size.width(),
                          int(rect.top())))
        screen = self.screen().availableGeometry()
        pos = right if right.x() + size.width() <= screen.right() else left
        self.move(max(screen.left(), pos.x()), max(screen.top(), pos.y()))

    def set_value(self, key, value):
        self.command.values[key] = value
        self.command.redo()
        if self.view.title_editor is not None:
            self.view.title_editor.style_changed()

    def on_font_changed(self, font):
        self.set_value('title_family', font.family())

    def flush(self):
        """Put the changes so far on the undo stack."""

        if self.command.values:
            self.command.ignore_first_redo = True
            self.undo_stack.push(self.command)
            self.command = commands.ChangeGroupStyle(
                [self.group], text='Change title text')

    def closeEvent(self, event):
        if not self.committed:
            self.committed = True
            self.flush()
        if self.view.title_panel is self:
            self.view.title_panel = None
        super().closeEvent(event)


class GroupStyleDialog(QtWidgets.QDialog):
    """Change the look of groups, with a live preview.

    All changes end up in one undo step; only the values changed in the
    dialog are applied, so groups keep their other differences.
    """

    def __init__(self, parent, groups, undo_stack, show=True):
        super().__init__(parent)
        self.undo_stack = undo_stack
        self.groups = groups
        self.command = commands.ChangeGroupStyle(groups)
        style = groups[0].get_style()

        self.setWindowTitle(_('Group Style'))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        layout = QtWidgets.QFormLayout(self)

        self.name_input = None
        self.old_name = None
        if len(groups) == 1:
            self.old_name = groups[0].name
            self.name_input = QtWidgets.QLineEdit(groups[0].display_name())
            self.name_input.textChanged.connect(self.on_name_changed)
            layout.addRow(_('Title:'), self.name_input)

        self.background_input = ColorField(
            groups[0].background_color(), _('Background Color'), self)
        self.background_input.callback = partial(self.set_value, 'color')
        layout.addRow(_('Background color:'), self.background_input)

        self.border_color_input = ColorField(
            style['border_color'], _('Border Color'), self)
        self.border_color_input.callback = partial(
            self.set_value, 'border_color')
        layout.addRow(_('Border color:'), self.border_color_input)

        self.border_width_input = DragDoubleSpinBox()
        self.border_width_input.setRange(0, group_style.MAX_BORDER_WIDTH)
        self.border_width_input.setDecimals(1)
        self.border_width_input.setValue(style['border_width'])
        self.border_width_input.valueChanged.connect(
            partial(self.set_value, 'border_width'))
        layout.addRow(_('Border width:'), self.border_width_input)

        self.border_style_input = QtWidgets.QComboBox()
        names = {
            'solid': _('Solid'),
            'dash': _('Dashes'),
            'dot': _('Dots'),
            'dash_dot': _('Dash and dot'),
            'dash_dot_dot': _('Dash and two dots'),
        }
        for key in group_style.BORDER_STYLES:
            self.border_style_input.addItem(names[key], key)
        self.border_style_input.setCurrentIndex(
            self.border_style_input.findData(style['border_style']))
        self.border_style_input.currentIndexChanged.connect(
            self.on_border_style_changed)
        layout.addRow(_('Border style:'), self.border_style_input)

        self.border_shape_input = QtWidgets.QComboBox()
        shapes = {
            'straight': _('Straight'),
            'zigzag': _('Zigzag'),
            'wave': _('Wave'),
            'scallop': _('Scallops'),
            'battlement': _('Battlements'),
        }
        for key in group_style.BORDER_SHAPES:
            self.border_shape_input.addItem(shapes[key], key)
        self.border_shape_input.setCurrentIndex(
            self.border_shape_input.findData(style['border_shape']))
        self.border_shape_input.currentIndexChanged.connect(
            self.on_border_shape_changed)
        layout.addRow(_('Border shape:'), self.border_shape_input)

        self.amplitude_input = DragDoubleSpinBox()
        self.amplitude_input.setRange(0, group_style.MAX_AMPLITUDE)
        self.amplitude_input.setDecimals(1)
        self.amplitude_input.setValue(style['border_amplitude'])
        self.amplitude_input.valueChanged.connect(
            partial(self.set_value, 'border_amplitude'))
        layout.addRow(_('Wave height:'), self.amplitude_input)

        self.wavelength_input = DragDoubleSpinBox()
        self.wavelength_input.setRange(
            group_style.MIN_WAVELENGTH, group_style.MAX_WAVELENGTH)
        self.wavelength_input.setDecimals(1)
        self.wavelength_input.setValue(style['border_wavelength'])
        self.wavelength_input.valueChanged.connect(
            partial(self.set_value, 'border_wavelength'))
        layout.addRow(_('Wave length:'), self.wavelength_input)
        self.update_wave_inputs()

        self.title_color_input = ColorField(
            style['title_color'], _('Title Color'), self)
        self.title_color_input.callback = partial(
            self.set_value, 'title_color')
        layout.addRow(_('Title color:'), self.title_color_input)

        self.title_size_input = DragDoubleSpinBox()
        self.title_size_input.setRange(0, group_style.MAX_TITLE_SIZE)
        self.title_size_input.setDecimals(0)
        self.title_size_input.setSpecialValueText(_('No title'))
        self.title_size_input.setValue(style['title_size'])
        self.title_size_input.valueChanged.connect(
            partial(self.set_value, 'title_size'))
        layout.addRow(_('Title size:'), self.title_size_input)

        self.title_position_input = QtWidgets.QComboBox()
        positions = {
            'top_left': _('Top left'),
            'top_center': _('Top center'),
            'top_right': _('Top right'),
            'middle_left': _('Left side'),
            'middle_right': _('Right side'),
            'bottom_left': _('Bottom left'),
            'bottom_center': _('Bottom center'),
            'bottom_right': _('Bottom right'),
        }
        for key in group_style.TITLE_POSITIONS:
            self.title_position_input.addItem(positions[key], key)
        self.title_position_input.setCurrentIndex(
            self.title_position_input.findData(style['title_position']))
        self.title_position_input.currentIndexChanged.connect(
            self.on_title_position_changed)
        layout.addRow(_('Title position:'), self.title_position_input)

        self.opacity_input = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.opacity_input.setRange(0, 100)
        self.opacity_input.setValue(round(style['opacity'] * 100))
        self.opacity_input.valueChanged.connect(self.on_opacity_changed)
        layout.addRow(_('Opacity:'), self.opacity_input)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if show:
            self.show()

    def set_value(self, key, value):
        """Preview a changed value."""

        self.command.values[key] = value
        self.command.redo()

    def new_name(self):
        name = self.name_input.text().strip()
        if name == self.groups[0].default_name():
            name = ''
        return name

    def on_name_changed(self, text):
        """Preview the new title."""

        self.groups[0].name = self.new_name()
        self.groups[0].update()

    def on_title_position_changed(self, index):
        self.set_value('title_position',
                       self.title_position_input.itemData(index))

    def on_border_style_changed(self, index):
        self.set_value('border_style', self.border_style_input.itemData(index))

    def on_border_shape_changed(self, index):
        self.set_value('border_shape', self.border_shape_input.itemData(index))
        self.update_wave_inputs()

    def update_wave_inputs(self):
        wavy = self.border_shape_input.currentData() != 'straight'
        self.amplitude_input.setEnabled(wavy)
        self.wavelength_input.setEnabled(wavy)

    def on_opacity_changed(self, value):
        self.set_value('opacity', value / 100)

    def renamed(self):
        return (self.name_input is not None
                and self.new_name() != self.old_name)

    def accept(self):
        renamed = self.renamed()
        if self.command.values or renamed:
            logger.debug(f'Setting group style: {self.command.values}')
            self.undo_stack.beginMacro('Change group')
            if self.command.values:
                self.command.ignore_first_redo = True
                self.undo_stack.push(self.command)
            if renamed:
                name = self.new_name()
                self.groups[0].name = self.old_name
                self.undo_stack.push(
                    commands.RenameItem(self.groups[0], name))
            self.undo_stack.endMacro()
        return super().accept()

    def reject(self):
        if self.command.values:
            self.command.undo()
        if self.name_input is not None:
            self.groups[0].name = self.old_name
            self.groups[0].update()
        return super().reject()
