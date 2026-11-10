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

"""Grid, snapping and canvas area of the view."""

import logging

from PyQt6 import QtCore, QtGui

from beeref import commands
from beeref import constants
from beeref import snapping


logger = logging.getLogger(__name__)


class CanvasMixin:
    """Grid, snapping and canvas area for :class:`BeeGraphicsView`."""

    def init_canvas_state(self):
        """Has to be called before the actions get built, since the
        callbacks of checkable actions run while building them."""

        self.show_grid = False
        self.snap_to_grid = False
        self.snap_to_items = False

    def grid_size(self):
        """The grid size in scene coordinates at the current zoom."""

        return snapping.effective_grid_size(
            self.settings.valueOrDefault('Canvas/grid_size'),
            self.get_scale())

    def canvas_rect(self):
        """The area of the canvas: The bounding rect of all items plus
        the canvas margin, or ``None`` with an empty scene."""

        if not any(True for _ in self.scene.items_for_save()):
            return None
        margin = self.settings.valueOrDefault('Canvas/margin')
        return self.scene.itemsBoundingRect().adjusted(
            -margin, -margin, margin, margin)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        if self.settings.valueOrDefault('Canvas/highlight_canvas'):
            canvas = self.canvas_rect()
            if canvas:
                painter.fillRect(canvas, QtGui.QColor(
                    *constants.COLORS['Scene:CanvasArea']))
        if self.show_grid:
            self.draw_grid(painter, rect)

    def draw_grid(self, painter, rect):
        size = self.grid_size()
        xs = snapping.grid_lines(rect.left(), rect.right(), size)
        ys = snapping.grid_lines(rect.top(), rect.bottom(), size)
        minor = QtGui.QPen(QtGui.QColor(*constants.COLORS['Scene:Grid']))
        minor.setCosmetic(True)
        major = QtGui.QPen(
            QtGui.QColor(*constants.COLORS['Scene:GridMajor']))
        major.setCosmetic(True)
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)

        if self.settings.valueOrDefault('Canvas/grid_style') == 'dots':
            minor.setColor(QtGui.QColor(*constants.COLORS['Scene:GridDot']))
            minor.setWidth(3)
            major.setColor(
                QtGui.QColor(*constants.COLORS['Scene:GridDotMajor']))
            major.setWidth(4)
            for pen, is_major in ((minor, False), (major, True)):
                points = [QtCore.QPointF(x, y) for x in xs for y in ys
                          if (snapping.is_major_line(x, size)
                              and snapping.is_major_line(y, size))
                          == is_major]
                painter.setPen(pen)
                painter.drawPoints(points)
        else:
            for pen, is_major in ((minor, False), (major, True)):
                lines = [
                    QtCore.QLineF(x, rect.top(), x, rect.bottom())
                    for x in xs
                    if snapping.is_major_line(x, size) == is_major]
                lines += [
                    QtCore.QLineF(rect.left(), y, rect.right(), y)
                    for y in ys
                    if snapping.is_major_line(y, size) == is_major]
                painter.setPen(pen)
                painter.drawLines(lines)
        painter.restore()

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        guides = getattr(self.scene, 'snap_guides', None)
        if guides:
            pen = QtGui.QPen(
                QtGui.QColor(*constants.COLORS['Scene:SnapGuide']))
            pen.setCosmetic(True)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            painter.save()
            painter.setPen(pen)
            painter.drawLines(guides)
            painter.restore()

    def snap_threshold(self):
        """The maximum distance for snapping to other items, in scene
        coordinates."""

        return (self.settings.valueOrDefault('Canvas/snap_distance')
                / self.get_scale())

    def on_action_show_grid(self, checked):
        self.show_grid = checked
        self.viewport().update()

    def on_action_snap_to_grid(self, checked):
        self.snap_to_grid = checked

    def on_action_snap_to_items(self, checked):
        self.snap_to_items = checked

    def on_canvas_settings_changed(self):
        self.viewport().update()

    def on_action_focus_canvas(self):
        canvas = self.canvas_rect()
        if canvas:
            self.fit_rect(canvas)

    def on_action_optimize_canvas(self):
        """Move all items so that they are centered on the origin.

        Far away items make the scene huge, which can make zooming and
        panning imprecise. The view keeps showing the same items.
        """

        items = self.scene.user_items()
        if not items:
            return
        center = self.scene.itemsBoundingRect().center()
        delta = QtCore.QPointF(-round(center.x()), -round(center.y()))
        if delta.isNull():
            return
        view_center = self.mapToScene(self.get_view_center())
        logger.debug(f'Optimize canvas: Moving items by {delta}')
        self.undo_stack.push(commands.MoveItemsBy(items, delta))
        self.previous_transform = None
        self.recalc_scene_rect()
        self.centerOn(view_center + delta)
