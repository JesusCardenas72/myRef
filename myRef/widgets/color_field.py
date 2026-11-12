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

"""Color fields: a swatch that opens a color dialog plus a field for
the transparency of the color."""

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef.i18n import _
from myRef.widgets.dragspin import DragSpinBox


def alpha_to_transparency(alpha):
    """Alpha 0-255 -> transparency in percent (0 = opaque)."""
    return round((255 - alpha) * 100 / 255)


def transparency_to_alpha(transparency):
    """Transparency in percent (0 = opaque) -> alpha 0-255."""
    return round((100 - transparency) * 255 / 100)


def swatch_pixmap(color, width=40, height=16):
    """The color over a checkerboard, so that transparency is visible."""

    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.white)
    painter = QtGui.QPainter(pixmap)
    for x in range(0, width, 8):
        for y in range(0, height, 8):
            if (x + y) // 8 % 2:
                painter.fillRect(x, y, 8, 8, Qt.GlobalColor.lightGray)
    painter.fillRect(pixmap.rect(), QtGui.QColor(color))
    painter.end()
    return pixmap


class TransparencySpinBox(DragSpinBox):
    """Transparency of a color in percent: 0 is opaque, 100 invisible."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setSuffix(' %')
        self.setKeyboardTracking(False)
        self.setMinimumWidth(64)
        self.setToolTip(_('Transparency'))


class ColorField(QtWidgets.QWidget):
    """A color swatch (a click opens a color dialog) and the
    transparency of the color next to it.

    ``callback`` is called with the new color as ``#AARRGGBB``.
    """

    def __init__(self, color, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.color = QtGui.QColor(color)
        self.callback = None
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.button = QtWidgets.QToolButton()
        self.button.setMinimumWidth(60)
        self.button.clicked.connect(self.choose_color)
        layout.addWidget(self.button)
        self.transparency_input = TransparencySpinBox()
        self.transparency_input.valueChanged.connect(
            self.on_transparency_changed)
        layout.addWidget(self.transparency_input)
        layout.addStretch()
        self.show_color()

    def show_color(self):
        self.button.setIcon(QtGui.QIcon(swatch_pixmap(self.color)))
        self.button.setIconSize(QtGui.QPixmap(40, 16).size())
        self.transparency_input.blockSignals(True)
        self.transparency_input.setValue(
            alpha_to_transparency(self.color.alpha()))
        self.transparency_input.blockSignals(False)

    def set_color(self, color):
        self.color = QtGui.QColor(color)
        self.show_color()
        if self.callback:
            self.callback(self.color.name(QtGui.QColor.NameFormat.HexArgb))

    def set_transparency(self, transparency):
        self.transparency_input.setValue(transparency)

    def on_transparency_changed(self, transparency):
        color = QtGui.QColor(self.color)
        color.setAlpha(transparency_to_alpha(transparency))
        if color != self.color:
            self.set_color(color)

    def choose_color(self):
        color = QtWidgets.QColorDialog.getColor(
            self.color, self, self.title,
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self.set_color(color)
