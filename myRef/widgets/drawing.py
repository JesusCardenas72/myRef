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

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QPointF, QRectF, QSize

from myRef import commands
from myRef import drawing
from myRef.i18n import _
from myRef.widgets.color_field import (
    TransparencySpinBox,
    alpha_to_transparency,
    swatch_pixmap,
    transparency_to_alpha,
)
from myRef.widgets.dragspin import DragDoubleSpinBox


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
        #: Polyline being drawn click by click (not yet committed)
        self.polyline = None

    @property
    def scene(self):
        return self.view.scene

    @property
    def tool(self):
        return tool_settings['tool']

    def set_tool(self, tool):
        if tool in drawing.TOOLS:
            if tool != tool_settings['tool']:
                # A polyline is finished when switching tools
                self.finish_polyline()
            tool_settings['tool'] = tool

    @property
    def active(self):
        return (self.shape is not None or self.erasing
                or self.polyline is not None)

    def item_valid(self):
        return self.item is not None and self.item.scene() is self.scene

    def to_local(self, scene_pos):
        return self.item.mapFromScene(scene_pos)

    def screen_scale(self):
        return self.item.screen_scale()

    def _ensure_item(self, scene_pos):
        """Create a drawing item at ``scene_pos`` if there is none.
        Returns whether a new item was created."""

        if self.item_valid():
            return False
        from myRef.items import BeeDrawingItem
        self.item = BeeDrawingItem()
        self.item.setScale(1 / self.view.get_scale())
        self.item.setPos(scene_pos)
        self.scene.addItem(self.item)
        self.item.bring_to_front()
        return True

    def press(self, scene_pos, modifiers=Qt.KeyboardModifier.NoModifier):
        if self.polyline is not None and self.tool != 'polyline':
            self.finish_polyline()

        if self.tool == 'eraser':
            self.erasing = True
            if self.item_valid():
                self.old_shapes = list(self.item.shapes)
            else:
                self.old_shapes = None
            self.erase_at(scene_pos)
            return

        if self.tool == 'polyline':
            self.press_polyline(scene_pos)
            return

        self.new_item = self._ensure_item(scene_pos)
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
        if self.polyline is not None and self.shape is None:
            # Rubber band from the last vertex to the cursor
            if not self.item_valid():
                return
            local = self.to_local(scene_pos)
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                local = drawing.constrain('line', self.start, local)
            self.polyline['points'][-1] = [local.x(), local.y()]
            self.item.update_last_shape(self.polyline)
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

    def press_polyline(self, scene_pos):
        """Each click fixes the current vertex and starts the next
        segment from it. The first click starts the polyline."""

        if self.polyline is not None and not self.item_valid():
            self.polyline = None
        if self.polyline is not None:
            local = self.to_local(scene_pos)
            point = [local.x(), local.y()]
            # The rubber band's end becomes a fixed vertex; a new
            # rubber band starts from it
            self.polyline['points'][-1] = point
            self.polyline['points'].append(list(point))
            self.start = local
            self.item.update_last_shape(self.polyline)
            return

        self.new_item = self._ensure_item(scene_pos)
        self.old_shapes = list(self.item.shapes)
        local = self.to_local(scene_pos)
        point = [local.x(), local.y()]
        self.polyline = drawing.make_shape(
            'polyline', [point, point],
            color=tool_settings['color'],
            width=tool_settings['width'] / self.screen_scale(),
            style=tool_settings['style'])
        self.start = local
        self.item.add_shape(self.polyline)

    def finish_polyline(self):
        """Commit the polyline being drawn as one undo step. The last
        point is the rubber band to the cursor, so it is dropped."""

        shape = self.polyline
        if shape is None:
            return
        self.polyline = None
        if not self.item_valid():
            return
        points = []
        for point in shape['points'][:-1]:
            if not points or point != points[-1]:
                points.append(point)
        keep = len(points) >= 2
        if keep:
            shape['points'] = points
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
        self.old_shapes = None

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

        self.finish_polyline()
        if self.active:
            self.shape = None
            self.erasing = False
        if self.item_valid() and not self.item.shapes:
            self.view.undo_stack.push(
                commands.DeleteItems(self.scene, [self.item]))
            self.item = None
        return self.item if self.item_valid() else None


#: Size of the tool icons in logical pixels
TOOL_ICON_SIZE = 26


def _draw_pencil(p):
    p.save()
    p.translate(12, 12)
    p.rotate(45)
    p.drawRoundedRect(QRectF(-3.5, -9, 7, 14), 1.5, 1.5)
    p.drawLine(QPointF(-3.5, -5), QPointF(3.5, -5))
    p.drawLine(QPointF(-3.5, 5), QPointF(3.5, 5))
    p.drawLine(QPointF(-3.5, 5), QPointF(0, 10))
    p.drawLine(QPointF(3.5, 5), QPointF(0, 10))
    p.restore()


def _draw_line(p):
    p.drawLine(QPointF(5, 19), QPointF(19, 5))
    p.setBrush(p.pen().color())
    p.drawEllipse(QPointF(5, 19), 2.2, 2.2)
    p.drawEllipse(QPointF(19, 5), 2.2, 2.2)
    p.setBrush(Qt.BrushStyle.NoBrush)


def _draw_polyline(p):
    points = [QPointF(3.5, 18), QPointF(9.5, 6), QPointF(14.5, 16),
              QPointF(20.5, 6)]
    for a, b in zip(points, points[1:]):
        p.drawLine(a, b)
    p.setBrush(p.pen().color())
    for point in points:
        p.drawEllipse(point, 2, 2)
    p.setBrush(Qt.BrushStyle.NoBrush)


def _draw_arrow(p):
    p.drawLine(QPointF(5, 19), QPointF(19, 5))
    p.drawLine(QPointF(9, 5), QPointF(19, 5))
    p.drawLine(QPointF(19, 5), QPointF(19, 15))


def _draw_rect(p):
    p.drawRoundedRect(QRectF(4, 6, 16, 12), 1.5, 1.5)


def _draw_ellipse(p):
    p.drawEllipse(QRectF(3.5, 6, 17, 12))


def _draw_eraser(p):
    p.save()
    p.translate(12, 12)
    p.rotate(-35)
    p.drawRoundedRect(QRectF(-6, -8, 12, 16), 2.5, 2.5)
    p.drawLine(QPointF(-6, 1), QPointF(6, 1))
    p.restore()


TOOL_ICON_PAINTERS = {
    'pen': _draw_pencil,
    'line': _draw_line,
    'polyline': _draw_polyline,
    'arrow': _draw_arrow,
    'rect': _draw_rect,
    'ellipse': _draw_ellipse,
    'eraser': _draw_eraser,
}


def tool_icon(tool, color, size=TOOL_ICON_SIZE):
    """A crisp vector icon of a draw tool, painted in ``color``."""

    scale = 2  # Rendered for high DPI screens
    pixmap = QtGui.QPixmap(int(size * scale), int(size * scale))
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    # Icons are designed on a 24 x 24 grid
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24, size / 24)
    pen = QtGui.QPen(color, 2.2, Qt.PenStyle.SolidLine,
                     Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    TOOL_ICON_PAINTERS[tool](painter)
    painter.end()
    return QtGui.QIcon(pixmap)


class ColorButton(QtWidgets.QToolButton):

    def set_color(self, color):
        self.setIcon(QtGui.QIcon(swatch_pixmap(color, 22, 22)))


class DrawToolbar(QtWidgets.QFrame):
    """Floating toolbar shown in draw mode."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setObjectName('DrawToolbar')
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.tool_buttons = {}
        group = QtWidgets.QButtonGroup(self)
        group.setExclusive(True)
        for tool in drawing.TOOLS:
            button = QtWidgets.QToolButton()
            button.setIconSize(QSize(TOOL_ICON_SIZE, TOOL_ICON_SIZE))
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setMinimumSize(40, 38)
            button.clicked.connect(
                lambda checked=False, t=tool: self.view.set_draw_tool(t))
            group.addButton(button)
            layout.addWidget(button)
            self.tool_buttons[tool] = button

        self.color_button = ColorButton()
        self.color_button.setIconSize(QSize(22, 22))
        self.color_button.setMinimumSize(34, 38)
        self.color_button.setAutoRaise(True)
        self.color_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.color_button.clicked.connect(self.on_color)
        layout.addWidget(self.color_button)

        self.transparency_box = TransparencySpinBox()
        self.transparency_box.setMinimumHeight(34)
        self.transparency_box.valueChanged.connect(self.on_transparency)
        layout.addWidget(self.transparency_box)

        self.width_box = DragDoubleSpinBox()
        self.width_box.setRange(0.5, 200)
        self.width_box.setDecimals(1)
        self.width_box.setMinimumSize(76, 34)
        self.width_box.valueChanged.connect(self.on_width)
        layout.addWidget(self.width_box)

        self.style_box = QtWidgets.QComboBox()
        for style in drawing.STYLES:
            self.style_box.addItem('', style)
        self.style_box.setMinimumHeight(34)
        self.style_box.currentIndexChanged.connect(self.on_style)
        layout.addWidget(self.style_box)

        self.done_button = QtWidgets.QToolButton()
        self.done_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.done_button.clicked.connect(self.view.exit_draw_mode)
        layout.addWidget(self.done_button)
        self.refresh_icons()
        self.retranslate()
        self.update_state()
        self.hide()

    def retranslate(self):
        tooltips = {
            'pen': _('Pen'),
            'line': _('Line'),
            'polyline': _('Polyline'),
            'arrow': _('Arrow'),
            'rect': _('Rectangle'),
            'ellipse': _('Ellipse'),
            'eraser': _('Eraser'),
        }
        for tool, button in self.tool_buttons.items():
            button.setToolTip(tooltips[tool])
        self.color_button.setToolTip(_('Color'))
        self.transparency_box.setToolTip(_('Transparency'))
        self.width_box.setToolTip(_('Line width'))
        names = {'solid': _('Solid'), 'dashed': _('Dashed'),
                 'dotted': _('Dotted')}
        for i in range(self.style_box.count()):
            self.style_box.setItemText(i, names[self.style_box.itemData(i)])
        self.style_box.setToolTip(_('Line style'))
        self.done_button.setText(_('Done'))

    def refresh_icons(self):
        """Paint the tool icons in the current text color."""

        color = self.palette().color(QtGui.QPalette.ColorRole.ButtonText)
        for tool, button in self.tool_buttons.items():
            button.setIcon(tool_icon(tool, color))

    def changeEvent(self, event):
        if (event.type() in (QtCore.QEvent.Type.PaletteChange,
                             QtCore.QEvent.Type.StyleChange)
                and self.tool_buttons):
            self.refresh_icons()
        super().changeEvent(event)

    def update_state(self):
        self.tool_buttons[tool_settings['tool']].setChecked(True)
        self.color_button.set_color(tool_settings['color'])
        self.transparency_box.blockSignals(True)
        self.transparency_box.setValue(alpha_to_transparency(
            QtGui.QColor(tool_settings['color']).alpha()))
        self.transparency_box.blockSignals(False)
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

    def on_transparency(self, value):
        color = QtGui.QColor(tool_settings['color'])
        color.setAlpha(transparency_to_alpha(value))
        tool_settings['color'] = color.name(QtGui.QColor.NameFormat.HexArgb)
        self.color_button.set_color(tool_settings['color'])
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
