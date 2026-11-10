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

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef import commands
from myRef import group_style
from myRef.i18n import _


logger = logging.getLogger(__name__)


class ColorButton(QtWidgets.QToolButton):
    """Shows a color; a click opens a color dialog."""

    def __init__(self, color, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.color = QtGui.QColor(color)
        self.callback = None
        self.setMinimumWidth(60)
        self.update_icon()
        self.clicked.connect(self.choose_color)

    def update_icon(self):
        pixmap = QtGui.QPixmap(40, 16)
        pixmap.fill(Qt.GlobalColor.white)
        painter = QtGui.QPainter(pixmap)
        # Checkerboard so that transparency is visible
        for x in range(0, 40, 8):
            for y in range(0, 16, 8):
                if (x + y) // 8 % 2:
                    painter.fillRect(x, y, 8, 8, Qt.GlobalColor.lightGray)
        painter.fillRect(pixmap.rect(), self.color)
        painter.end()
        self.setIcon(QtGui.QIcon(pixmap))
        self.setIconSize(pixmap.size())

    def set_color(self, color):
        self.color = QtGui.QColor(color)
        self.update_icon()
        if self.callback:
            self.callback(self.color.name(QtGui.QColor.NameFormat.HexArgb))

    def choose_color(self):
        color = QtWidgets.QColorDialog.getColor(
            self.color, self, self.title,
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self.set_color(color)


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

        self.background_input = ColorButton(
            groups[0].background_color(), _('Background Color'), self)
        self.background_input.callback = partial(self.set_value, 'color')
        layout.addRow(_('Background color:'), self.background_input)

        self.border_color_input = ColorButton(
            style['border_color'], _('Border Color'), self)
        self.border_color_input.callback = partial(
            self.set_value, 'border_color')
        layout.addRow(_('Border color:'), self.border_color_input)

        self.border_width_input = QtWidgets.QDoubleSpinBox()
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

        self.amplitude_input = QtWidgets.QDoubleSpinBox()
        self.amplitude_input.setRange(0, group_style.MAX_AMPLITUDE)
        self.amplitude_input.setDecimals(1)
        self.amplitude_input.setValue(style['border_amplitude'])
        self.amplitude_input.valueChanged.connect(
            partial(self.set_value, 'border_amplitude'))
        layout.addRow(_('Wave height:'), self.amplitude_input)

        self.wavelength_input = QtWidgets.QDoubleSpinBox()
        self.wavelength_input.setRange(
            group_style.MIN_WAVELENGTH, group_style.MAX_WAVELENGTH)
        self.wavelength_input.setDecimals(1)
        self.wavelength_input.setValue(style['border_wavelength'])
        self.wavelength_input.valueChanged.connect(
            partial(self.set_value, 'border_wavelength'))
        layout.addRow(_('Wave length:'), self.wavelength_input)
        self.update_wave_inputs()

        self.title_color_input = ColorButton(
            style['title_color'], _('Title Color'), self)
        self.title_color_input.callback = partial(
            self.set_value, 'title_color')
        layout.addRow(_('Title color:'), self.title_color_input)

        self.title_size_input = QtWidgets.QDoubleSpinBox()
        self.title_size_input.setRange(0, group_style.MAX_TITLE_SIZE)
        self.title_size_input.setDecimals(0)
        self.title_size_input.setSpecialValueText(_('No title'))
        self.title_size_input.setValue(style['title_size'])
        self.title_size_input.valueChanged.connect(
            partial(self.set_value, 'title_size'))
        layout.addRow(_('Title size:'), self.title_size_input)

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

    def accept(self):
        if self.command.values:
            logger.debug(f'Setting group style: {self.command.values}')
            self.command.ignore_first_redo = True
            self.undo_stack.push(self.command)
        return super().accept()

    def reject(self):
        if self.command.values:
            self.command.undo()
        return super().reject()
