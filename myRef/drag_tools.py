# This file is part of myRef.
#
# myRef is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# myRef is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with myRef.  If not, see <https://www.gnu.org/licenses/>.

"""Dragging on items with modifier keys or held keys (as in PureRef):

* Ctrl: rotate, Ctrl+Shift: rotate in steps, Ctrl+Alt: scale,
  Ctrl+Alt+Shift: opacity, Alt+Shift: flip (configurable mouse
  controls)
* C: crop the selected images to a rectangle
* V: pan the image inside its crop frame, Shift+V: zoom inside it
* Z: zoom the view
* S: show the color under the cursor
* D: show the image coordinates under the cursor
"""

import logging
import math

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef import commands
from myRef.config import BeeSettings, KeyboardSettings
from myRef import hierarchy
from myRef.i18n import _
from myRef import utils
from myRef.utils import qcolor_to_hex


logger = logging.getLogger(__name__)

#: Keys that turn a left drag into a tool while held
HOLD_KEYS = {
    Qt.Key.Key_C: 'crop',
    Qt.Key.Key_V: 'pan_crop',
    Qt.Key.Key_Z: 'zoom',
    Qt.Key.Key_S: 'color',
    Qt.Key.Key_D: 'coordinates',
}

#: Pixels on screen for doubling the scale while dragging
SCALE_DRAG_PIXELS = 200
#: Pixels on screen for going from transparent to opaque
OPACITY_DRAG_PIXELS = 300
MIN_OPACITY = 0.05
#: Pixels on screen before a flip drag decides its direction
FLIP_DRAG_PIXELS = 10


def drag_factor(dx):
    """Scale factor for a horizontal drag distance in pixels."""
    return 2 ** (dx / SCALE_DRAG_PIXELS)


def clamp_rect(rect, bounds):
    """Move ``rect`` so that it lies within ``bounds`` (it must not be
    larger than ``bounds``)."""

    rect = QtCore.QRectF(rect)
    if rect.left() < bounds.left():
        rect.moveLeft(bounds.left())
    if rect.right() > bounds.right():
        rect.moveRight(bounds.right())
    if rect.top() < bounds.top():
        rect.moveTop(bounds.top())
    if rect.bottom() > bounds.bottom():
        rect.moveBottom(bounds.bottom())
    return rect


def panned_crop(crop, delta, bounds):
    """The crop rect moved by ``delta`` (in image coordinates), kept
    inside the image."""

    return clamp_rect(crop.translated(delta), bounds)


def zoomed_crop(crop, factor, bounds):
    """The crop rect zoomed by ``factor`` (> 1 zooms in) around its
    center, keeping its aspect ratio and staying inside the image."""

    width = crop.width() / factor
    height = crop.height() / factor
    shrink = min(1, bounds.width() / width, bounds.height() / height)
    width = max(1, width * shrink)
    height = max(1, height * shrink)
    rect = QtCore.QRectF(0, 0, width, height)
    rect.moveCenter(crop.center())
    return clamp_rect(rect, bounds)


class CursorInfoWidget(QtWidgets.QLabel):
    """A small label following the mouse cursor."""

    OFFSET = 16

    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet(
            'QLabel { background-color: rgba(30, 30, 30, 220);'
            ' color: #f0f0f0; border: 1px solid #555555;'
            ' padding: 4px 6px; }')
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def show_at(self, pos, text):
        self.setText(text)
        self.adjustSize()
        x = int(pos.x()) + self.OFFSET
        y = int(pos.y()) + self.OFFSET
        parent = self.parentWidget()
        if parent is not None:
            # Stay inside the view
            x = min(x, parent.width() - self.width())
            y = min(y, parent.height() - self.height())
        self.move(max(0, x), max(0, y))
        self.show()
        self.raise_()


class DragToolsMixin:

    def init_drag_tools(self):
        self.held_keys = set()
        self.item_drag = None
        self.cursor_info = None

    # Held keys

    def drag_tools_key_press(self, event):
        key = event.key()
        if (key in HOLD_KEYS and not event.isAutoRepeat()
                and not self.scene.edit_item
                and not self.draw_session):
            self.held_keys.add(key)

    def drag_tools_key_release(self, event):
        if event.isAutoRepeat():
            return
        self.held_keys.discard(event.key())

    def held_tool(self, event):
        """The tool for a left mouse press while a key is held down."""

        if event.button() != Qt.MouseButton.LeftButton:
            return None
        modifiers = event.modifiers()
        tools = [HOLD_KEYS[key] for key in self.held_keys]
        if len(tools) != 1:
            return None
        tool = tools[0]
        if (tool == 'pan_crop'
                and modifiers == Qt.KeyboardModifier.ShiftModifier):
            return 'zoom_crop'
        if modifiers != Qt.KeyboardModifier.NoModifier:
            return None
        return tool

    # Starting a drag

    def image_under_cursor(self, scene_pos, selected_only=False):
        """The image at the position that drag tools act on."""

        item = self.scene.interactive_item_at(scene_pos)
        if not getattr(item, 'is_image', False):
            return None
        if selected_only and not item.isSelected():
            return None
        return item

    def drag_tools_press(self, event, action=None, inverted=False):
        """Start a drag tool if the press calls for one.

        :param action: Mouse action from the mouse controls settings
        :returns: ``True`` if a drag tool has been started
        """

        if (self.draw_session or self.scene.crop_item
                or self.scene.edit_item or self.scene.items_locked):
            return False
        tool = self.held_tool(event)
        if tool is None and action not in KeyboardSettings.ITEM_MOUSE_ACTIONS:
            return False
        pos = event.position()
        scene_pos = self.mapToScene(pos.toPoint())
        if tool is not None:
            return self.start_held_tool(tool, pos, scene_pos)
        return self.start_item_drag(action, inverted, pos, scene_pos)

    def start_item_drag(self, action, inverted, pos, scene_pos):
        if action in ('rotate', 'rotate_snap') and self.scene.link_at(
                scene_pos):
            # Ctrl+Click on a link in a note opens it
            return False
        item = self.scene.interactive_item_at(scene_pos)
        if item is None:
            return False
        if not item.isSelected():
            self.scene.clearSelection()
            item.setSelected(True)
        items = self.scene.selected_top_items()
        if not items:
            return False
        logger.debug(f'Start item drag: {action} on {len(items)} items')
        self.reset_previous_transform()
        rect = self.scene.itemsBoundingRect(items=items)
        drag = {
            'tool': action,
            'items': items,
            'start': pos,
            'scene_start': scene_pos,
            'anchor': rect.center(),
            'inverted': inverted,
            'orig': {item: (item.pos(), item.rotation(), item.scale(),
                            item.opacity())
                     for item in items},
        }
        if action in ('rotate', 'rotate_snap'):
            drag['start_angle'] = self.angle_to_anchor(
                scene_pos, drag['anchor'])
        self.item_drag = drag
        self.viewport().setCursor(self.drag_cursor(action))
        return True

    def start_held_tool(self, tool, pos, scene_pos):
        drag = {'tool': tool, 'start': pos, 'scene_start': scene_pos}
        if tool in ('pan_crop', 'zoom_crop'):
            item = self.image_under_cursor(scene_pos)
            if item is None:
                images = self.selected_images()
                if len(images) != 1:
                    return False
                item = images[0]
            drag['item'] = item
            drag['crop'] = QtCore.QRectF(item.crop)
            drag['scale'] = item.scale()
            drag['pos'] = item.pos()
            drag['frame_topleft'] = item.mapToScene(item.crop.topLeft())
            drag['frame_center'] = item.mapToScene(item.crop.center())
        elif tool == 'crop':
            images = self.selected_images()
            if not images:
                item = self.image_under_cursor(scene_pos)
                if item is None:
                    return False
                self.scene.clearSelection()
                item.setSelected(True)
                images = [item]
            drag['items'] = images
            self.scene.addItem(self.scene.rubberband_item)
            self.scene.rubberband_item.bring_to_front()
            self.scene.rubberband_item.fit(scene_pos, scene_pos)
        elif tool == 'zoom':
            drag['anchor'] = pos
        logger.debug(f'Start held key tool: {tool}')
        self.item_drag = drag
        self.viewport().setCursor(self.drag_cursor(tool))
        self.update_held_tool(drag, pos, scene_pos)
        return True

    @staticmethod
    def drag_cursor(tool):
        shapes = {
            'rotate': Qt.CursorShape.SizeAllCursor,
            'rotate_snap': Qt.CursorShape.SizeAllCursor,
            'scale': Qt.CursorShape.SizeHorCursor,
            'opacity': Qt.CursorShape.SizeHorCursor,
            'flip': Qt.CursorShape.SizeAllCursor,
            'crop': Qt.CursorShape.CrossCursor,
            'pan_crop': Qt.CursorShape.ClosedHandCursor,
            'zoom_crop': Qt.CursorShape.SizeHorCursor,
            'zoom': Qt.CursorShape.SizeVerCursor,
            'color': Qt.CursorShape.CrossCursor,
            'coordinates': Qt.CursorShape.CrossCursor,
        }
        return QtGui.QCursor(shapes.get(tool, Qt.CursorShape.ArrowCursor))

    @staticmethod
    def angle_to_anchor(pos, anchor):
        diff = pos - anchor
        return math.degrees(math.atan2(diff.y(), diff.x()))

    # Moving

    def drag_tools_move(self, event):
        if self.item_drag is None:
            return False
        pos = event.position()
        scene_pos = self.mapToScene(pos.toPoint())
        drag = self.item_drag
        if drag['tool'] in KeyboardSettings.ITEM_MOUSE_ACTIONS:
            self.update_item_drag(drag, pos, scene_pos)
        else:
            self.update_held_tool(drag, pos, scene_pos)
        event.accept()
        return True

    def restore_drag_items(self, drag):
        for item, (pos, rotation, scale, opacity) in drag['orig'].items():
            item.setRotation(rotation)
            item.setScale(scale)
            item.setPos(pos)
            item.setOpacity(opacity)

    def drag_dx(self, drag, pos):
        dx = pos.x() - drag['start'].x()
        return -dx if drag.get('inverted') else dx

    def update_item_drag(self, drag, pos, scene_pos):
        tool = drag['tool']
        anchor = drag['anchor']
        if tool in ('rotate', 'rotate_snap'):
            delta = (self.angle_to_anchor(scene_pos, anchor)
                     - drag['start_angle'])
            first = drag['items'][0]
            orig_rotation = drag['orig'][first][1]
            if tool == 'rotate_snap':
                step = BeeSettings().valueOrDefault('Items/rotation_snap')
                delta = utils.round_to(orig_rotation + delta, step)
                delta -= orig_rotation
            self.restore_drag_items(drag)
            for item in drag['items']:
                item.setRotation(item.rotation() + delta * item.flip(),
                                 item.mapFromScene(anchor))
            drag['value'] = delta
            self.show_cursor_info(
                pos, _('Rotation: {angle}°').format(
                    angle=round(first.rotation(), 1)))
        elif tool == 'scale':
            factor = drag_factor(self.drag_dx(drag, pos))
            self.restore_drag_items(drag)
            for item in drag['items']:
                item.setScale(item.scale() * factor,
                              item.mapFromScene(anchor))
            drag['value'] = factor
            self.show_cursor_info(
                pos, _('Scale: {percent}%').format(
                    percent=round(drag['items'][0].scale() * 100)))
        elif tool == 'opacity':
            first = drag['items'][0]
            opacity = drag['orig'][first][3] + (
                self.drag_dx(drag, pos) / OPACITY_DRAG_PIXELS)
            opacity = min(1, max(MIN_OPACITY, opacity))
            for item in drag['items']:
                item.setOpacity(opacity)
            drag['value'] = opacity
            self.show_cursor_info(
                pos, _('Opacity: {percent}%').format(
                    percent=round(opacity * 100)))
        elif tool == 'flip' and 'value' not in drag:
            diff = pos - drag['start']
            if max(abs(diff.x()), abs(diff.y())) < FLIP_DRAG_PIXELS:
                return
            vertical = abs(diff.y()) > abs(diff.x())
            drag['value'] = vertical
            self.undo_stack.push(
                commands.FlipItems(drag['items'], anchor, vertical=vertical))

    def update_held_tool(self, drag, pos, scene_pos):
        tool = drag['tool']
        if tool == 'crop':
            self.scene.rubberband_item.fit(drag['scene_start'], scene_pos)
        elif tool == 'pan_crop':
            self.update_pan_crop(drag, scene_pos)
        elif tool == 'zoom_crop':
            self.update_zoom_crop(drag, pos)
        elif tool == 'zoom':
            delta = (drag['start'] - pos).y()
            drag['start'] = pos
            if delta:
                self.zoom(delta * 20, drag['anchor'])
        elif tool == 'color':
            self.show_color_info(pos, scene_pos)
        elif tool == 'coordinates':
            self.show_coordinates_info(pos, scene_pos)

    def place_crop_frame(self, item, crop, scene_point, item_point):
        """Set the crop and move the item so that ``item_point`` (in item
        coordinates) ends up at ``scene_point``."""

        item.crop = crop
        delta = scene_point - item.mapToScene(item_point)
        item.setPos(item.pos() + hierarchy.scene_delta_to_parent(item, delta))

    def update_pan_crop(self, drag, scene_pos):
        item = drag['item']
        item.setPos(drag['pos'])
        item.setScale(drag['scale'])
        start = item.mapFromScene(drag['scene_start'])
        current = item.mapFromScene(scene_pos)
        bounds = QtCore.QRectF(item.pixmap().rect())
        # Dragging the image to the right shows more of its left part
        crop = panned_crop(drag['crop'], start - current, bounds)
        self.place_crop_frame(item, crop, drag['frame_topleft'],
                              crop.topLeft())
        drag['value'] = crop

    def update_zoom_crop(self, drag, pos):
        item = drag['item']
        factor = drag_factor(pos.x() - drag['start'].x())
        bounds = QtCore.QRectF(item.pixmap().rect())
        crop = zoomed_crop(drag['crop'], factor, bounds)
        item.setPos(drag['pos'])
        item.setScale(drag['scale'] * drag['crop'].width() / crop.width())
        self.place_crop_frame(item, crop, drag['frame_center'],
                              crop.center())
        drag['value'] = crop

    # Info at the cursor

    def show_cursor_info(self, pos, text):
        if self.cursor_info is None:
            self.cursor_info = CursorInfoWidget(self.viewport())
        self.cursor_info.show_at(pos, text)

    def hide_cursor_info(self):
        if self.cursor_info is not None:
            self.cursor_info.hide()

    def show_color_info(self, pos, scene_pos):
        color = self.scene.sample_color_at(scene_pos)
        if color is None:
            self.show_cursor_info(pos, _('No color'))
            return
        name = qcolor_to_hex(color)
        swatch = (f'<span style="background-color:{name};">'
                  '&nbsp;&nbsp;&nbsp;&nbsp;</span>')
        self.show_cursor_info(
            pos,
            f'{swatch} {name}<br/>'
            f'RGB {color.red()}, {color.green()}, {color.blue()}<br/>'
            f'HSV {max(color.hue(), 0)}, {color.saturation()}, '
            f'{color.value()}')

    def show_coordinates_info(self, pos, scene_pos):
        item = self.image_under_cursor(scene_pos)
        if item is None:
            self.show_cursor_info(
                pos, _('Canvas: {x}, {y}').format(
                    x=round(scene_pos.x()), y=round(scene_pos.y())))
            return
        point = item.mapFromScene(scene_pos)
        size = item.pixmap().size()
        self.show_cursor_info(
            pos,
            f'{item.display_name()}<br/>'
            + _('Pixel: {x}, {y}').format(
                x=math.floor(point.x()), y=math.floor(point.y()))
            + '<br/>'
            + _('Size: {width} × {height}').format(
                width=size.width(), height=size.height()))

    # Ending a drag

    def drag_tools_release(self, event):
        if self.item_drag is None:
            return False
        drag = self.item_drag
        self.item_drag = None
        self.viewport().unsetCursor()
        self.hide_cursor_info()
        tool = drag['tool']
        if tool in KeyboardSettings.ITEM_MOUSE_ACTIONS:
            self.finish_item_drag(drag)
        else:
            self.finish_held_tool(drag)
        self.scene.on_selection_change()
        event.accept()
        return True

    def finish_item_drag(self, drag):
        tool = drag['tool']
        value = drag.get('value')
        if value is None:
            return
        anchor = drag['anchor']
        if tool in ('rotate', 'rotate_snap') and value != 0:
            self.undo_stack.push(commands.RotateItemsBy(
                drag['items'], value, anchor, ignore_first_redo=True))
        elif tool == 'scale' and value != 1:
            self.undo_stack.push(commands.ScaleItemsBy(
                drag['items'], value, anchor, ignore_first_redo=True))
        elif tool == 'opacity':
            self.restore_drag_items(drag)
            self.undo_stack.push(
                commands.ChangeOpacity(drag['items'], value))

    def finish_held_tool(self, drag):
        tool = drag['tool']
        if tool == 'crop':
            rect = self.scene.rubberband_item.rect()
            self.scene.removeItem(self.scene.rubberband_item)
            self.crop_items_to_rect(drag['items'], rect)
        elif tool in ('pan_crop', 'zoom_crop') and 'value' in drag:
            item = drag['item']
            new = (QtCore.QRectF(item.crop), item.scale(), item.pos())
            command = commands.SetCropView(
                item, *new, ignore_first_redo=True)
            command.set_old(drag['crop'], drag['scale'], drag['pos'])
            self.undo_stack.push(command)

    def crop_items_to_rect(self, items, rect):
        """Crop the images to the given scene rect."""

        if rect.width() < 1 or rect.height() < 1:
            return
        changes = []
        for item in items:
            local = item.mapFromScene(rect).boundingRect()
            crop = item.crop.intersected(local)
            if crop.width() >= 1 and crop.height() >= 1:
                changes.append((item, crop))
        if not changes:
            return
        self.undo_stack.beginMacro('Crop items')
        for item, crop in changes:
            self.undo_stack.push(commands.CropItem(item, crop))
        self.undo_stack.endMacro()

    def cancel_drag_tools(self):
        if self.item_drag is None:
            return
        drag = self.item_drag
        self.item_drag = None
        if 'orig' in drag:
            self.restore_drag_items(drag)
        if drag['tool'] == 'crop' and self.scene.rubberband_item.scene():
            self.scene.removeItem(self.scene.rubberband_item)
        if drag['tool'] in ('pan_crop', 'zoom_crop'):
            item = drag['item']
            item.crop = drag['crop']
            item.setScale(drag['scale'])
            item.setPos(drag['pos'])
        self.viewport().unsetCursor()
        self.hide_cursor_info()
