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

"""Draw mode: drawing shapes into drawing items, and its toolbar."""

import logging
import math

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef import commands
from myRef import drawing
from myRef.i18n import _


logger = logging.getLogger(__name__)


# Tool settings are kept between draw sessions
tool_settings = {
    'tool': 'pen',
    'color': drawing.DEFAULT_COLOR,
    'width': drawing.DEFAULT_WIDTH,
    'style': 'solid',
}

#: Eraser radius in screen pixels
ERASER_RADIUS = 8
#: Pen strokes are simplified by this many screen pixels
SIMPLIFY_EPSILON = 0.75


class DrawSession:
    """One stay in draw mode.

    Shapes are drawn into ``item``. Without an item, the first stroke
    creates a new drawing item. Each finished stroke or erase gesture
    is one undo step.
    """

    def __init__(self, view, item=None):
        self.view = view
        self.item = item
        self.shape = None
        self.old_shapes = None
        self.new_item = False
        self.erasing = False

    @property
    def scene(self):
        return self.view.scene

    @property
    def tool(self):
        return tool_settings['tool']

    def set_tool(self, tool):
        if tool in drawing.TOOLS:
            tool_settings['tool'] = tool

    @property
    def active(self):
        return self.shape is not None or self.erasing

    def item_valid(self):
        return self.item is not None and self.item.scene() is self.scene

    def to_local(self, scene_pos):
        return self.item.mapFromScene(scene_pos)

    def screen_scale(self):
        return self.item.screen_scale()

    def press(self, scene_pos, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.tool == 'eraser':
            self.erasing = True
            if self.item_valid():
                self.old_shapes = list(self.item.shapes)
            else:
                self.old_shapes = None
            self.erase_at(scene_pos)
            return

        if not self.item_valid():
            from myRef.items import BeeDrawingItem
            self.item = BeeDrawingItem()
            self.item.setScale(1 / self.view.get_scale())
            self.item.setPos(scene_pos)
            self.scene.addItem(self.item)
            self.item.bring_to_front()
            self.new_item = True
        else:
            self.new_item = False
        self.old_shapes = list(self.item.shapes)
        local = self.to_local(scene_pos)
        points = [local] if self.tool == 'pen' else [local, local]
        self.shape = drawing.make_shape(
            self.tool,
            [(p.x(), p.y()) for p in points],
            color=tool_settings['color'],
            width=tool_settings['width'] / self.screen_scale(),
            style=tool_settings['style'])
        self.start = local
        self.item.add_shape(self.shape)

    def move(self, scene_pos, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.erasing:
            self.erase_at(scene_pos)
            return
        if self.shape is None or not self.item_valid():
            return
        local = self.to_local(scene_pos)
        if self.shape['type'] == 'pen':
            last = self.shape['points'][-1]
            min_dist = 0.5 / self.screen_scale()
            if math.hypot(local.x() - last[0], local.y() - last[1]) < min_dist:
                return
            self.shape['points'].append([local.x(), local.y()])
        else:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                local = drawing.constrain(self.shape['type'], self.start,
                                          local)
            self.shape['points'][-1] = [local.x(), local.y()]
        self.item.update_last_shape(self.shape)

    def release(self, scene_pos, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.erasing:
            self.erase_at(scene_pos)
            self.erasing = False
            if (self.item_valid() and self.old_shapes is not None
                    and self.item.shapes != self.old_shapes):
                self.view.undo_stack.push(commands.ChangeDrawing(
                    self.item, list(self.item.shapes), self.old_shapes,
                    text='Erase', ignore_first_redo=True))
            self.old_shapes = None
            return
        if self.shape is None:
            return
        self.move(scene_pos, modifiers)
        shape = self.shape
        self.shape = None
        if not self.item_valid():
            return
        scale = self.screen_scale()
        if shape['type'] == 'pen':
            shape['points'] = drawing.simplify(
                shape['points'], SIMPLIFY_EPSILON / scale)
            keep = True
        else:
            (x1, y1), (x2, y2) = shape['points'][0], shape['points'][-1]
            keep = math.hypot(x2 - x1, y2 - y1) * scale >= 2
        if keep:
            self.item.update_last_shape(shape)
        else:
            self.item.set_shapes(self.old_shapes)

        if self.new_item:
            if keep:
                self.view.undo_stack.push(commands.InsertItems(
                    self.scene, [self.item], ignore_first_redo=True))
            else:
                self.scene.removeItem(self.item)
                self.item = None
        elif keep:
            self.view.undo_stack.push(commands.ChangeDrawing(
                self.item, list(self.item.shapes), self.old_shapes,
                text='Draw', ignore_first_redo=True))
        self.new_item = False

    def erase_at(self, scene_pos):
        """Remove the shapes under the eraser. Without a current item,
        the first drawing under the cursor becomes the current item."""

        if not self.item_valid():
            from myRef.items import BeeDrawingItem
            candidates = [i for i in self.scene.items(scene_pos)
                          if isinstance(i, BeeDrawingItem)
                          and i.is_interactive()]
            for candidate in candidates:
                local = candidate.mapFromScene(scene_pos)
                radius = ERASER_RADIUS / candidate.screen_scale()
                if candidate.shapes_at(local, radius):
                    self.item = candidate
                    self.old_shapes = list(candidate.shapes)
                    break
            else:
                return
        local = self.to_local(scene_pos)
        radius = ERASER_RADIUS / self.screen_scale()
        hits = set(self.item.shapes_at(local, radius))
        if hits:
            self.item.set_shapes([s for i, s in enumerate(self.item.shapes)
                                  if i not in hits])

    def finish(self):
        """Leave draw mode: Finish the current stroke, remove the item
        if it ended up empty."""

        if self.active:
            self.shape = None
            self.erasing = False
        if self.item_valid() and not self.item.shapes:
            self.view.undo_stack.push(
                commands.DeleteItems(self.scene, [self.item]))
            self.item = None
        return self.item if self.item_valid() else None


class ColorButton(QtWidgets.QToolButton):

    def set_color(self, color):
        pixmap = QtGui.QPixmap(16, 16)
        pixmap.fill(QtGui.QColor(color))
        self.setIcon(QtGui.QIcon(pixmap))


class DrawToolbar(QtWidgets.QFrame):
    """Floating toolbar shown in draw mode."""

    TOOL_SYMBOLS = {
        'pen': '✎',
        'line': '╱',
        'arrow': '↗',
        'rect': '▭',
        'ellipse': '◯',
        'eraser': '⌫',
    }

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setObjectName('DrawToolbar')
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(1)
        self.tool_buttons = {}
        group = QtWidgets.QButtonGroup(self)
        group.setExclusive(True)
        for tool in drawing.TOOLS:
            button = QtWidgets.QToolButton()
            button.setText(self.TOOL_SYMBOLS[tool])
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setMinimumWidth(26)
            button.clicked.connect(
                lambda checked=False, t=tool: self.view.set_draw_tool(t))
            group.addButton(button)
            layout.addWidget(button)
            self.tool_buttons[tool] = button

        self.color_button = ColorButton()
        self.color_button.setAutoRaise(True)
        self.color_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.color_button.clicked.connect(self.on_color)
        layout.addWidget(self.color_button)

        self.width_box = QtWidgets.QDoubleSpinBox()
        self.width_box.setRange(0.5, 200)
        self.width_box.setDecimals(1)
        self.width_box.setMinimumWidth(72)
        self.width_box.valueChanged.connect(self.on_width)
        layout.addWidget(self.width_box)

        self.style_box = QtWidgets.QComboBox()
        for style in drawing.STYLES:
            self.style_box.addItem('', style)
        self.style_box.currentIndexChanged.connect(self.on_style)
        layout.addWidget(self.style_box)

        self.done_button = QtWidgets.QToolButton()
        self.done_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.done_button.clicked.connect(self.view.exit_draw_mode)
        layout.addWidget(self.done_button)
        self.retranslate()
        self.update_state()
        self.hide()

    def retranslate(self):
        tooltips = {
            'pen': _('Pen'),
            'line': _('Line'),
            'arrow': _('Arrow'),
            'rect': _('Rectangle'),
            'ellipse': _('Ellipse'),
            'eraser': _('Eraser'),
        }
        for tool, button in self.tool_buttons.items():
            button.setToolTip(tooltips[tool])
        self.color_button.setToolTip(_('Color'))
        self.width_box.setToolTip(_('Line width'))
        names = {'solid': _('Solid'), 'dashed': _('Dashed'),
                 'dotted': _('Dotted')}
        for i in range(self.style_box.count()):
            self.style_box.setItemText(i, names[self.style_box.itemData(i)])
        self.style_box.setToolTip(_('Line style'))
        self.done_button.setText(_('Done'))

    def update_state(self):
        self.tool_buttons[tool_settings['tool']].setChecked(True)
        self.color_button.set_color(tool_settings['color'])
        self.width_box.blockSignals(True)
        self.width_box.setValue(tool_settings['width'])
        self.width_box.blockSignals(False)
        self.style_box.blockSignals(True)
        self.style_box.setCurrentIndex(
            self.style_box.findData(tool_settings['style']))
        self.style_box.blockSignals(False)

    def on_color(self):
        color = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(tool_settings['color']), self.view, _('Color'),
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            tool_settings['color'] = color.name(
                QtGui.QColor.NameFormat.HexArgb)
            self.update_state()
        self.view.setFocus()

    def on_width(self, value):
        tool_settings['width'] = value
        self.view.setFocus()

    def on_style(self, index):
        style = self.style_box.itemData(index)
        if style:
            tool_settings['style'] = style
        self.view.setFocus()

    def show_toolbar(self):
        self.update_state()
        self.adjustSize()
        self.update_position()
        self.show()
        self.raise_()

    def update_position(self):
        size = self.sizeHint()
        self.move(max(0, (self.view.width() - size.width()) // 2), 8)
