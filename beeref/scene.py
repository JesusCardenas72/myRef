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

from functools import partial
import logging
import math
import random
from queue import Queue

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtCore import Qt

import rpack

from beeref import commands
from beeref import snapping
from beeref.config import BeeSettings
from beeref.i18n import _
from beeref.items import (
    item_registry,
    items_in_order,
    sort_by_addition,
    sort_by_filename,
    BeeErrorItem,
)
from beeref.selection import MultiSelectItem, RubberbandItem


logger = logging.getLogger(__name__)


class BeeGraphicsScene(QtWidgets.QGraphicsScene):
    cursor_changed = QtCore.pyqtSignal(QtGui.QCursor)
    cursor_cleared = QtCore.pyqtSignal()

    MOVE_MODE = 1
    RUBBERBAND_MODE = 2

    def __init__(self, undo_stack):
        super().__init__()
        self.active_mode = None
        self.undo_stack = undo_stack
        self.max_z = 0
        self.min_z = 0
        self.Z_STEP = 0.001
        self.selectionChanged.connect(self.on_selection_change)
        self.changed.connect(self.on_change)
        self.items_to_add = Queue()
        self.edit_item = None
        self.crop_item = None
        self.items_locked = False
        self.grayscale_canvas = False
        self.snap_guides = []
        self.move_start_rect = None
        self.snap_others = []
        self.settings = BeeSettings()
        self.clear()
        self._clear_ongoing = False

    def clear(self):
        self._clear_ongoing = True
        super().clear()
        self.internal_clipboard = []
        self.rubberband_item = RubberbandItem()
        self.multi_select_item = MultiSelectItem()
        self.pending_parents = {}
        self._clear_ongoing = False

    def addItem(self, item):
        logger.debug(f'Adding item {item}')
        super().addItem(item)
        if hasattr(item, 'set_locked'):
            item.set_locked(self.items_locked)

    def removeItem(self, item):
        logger.debug(f'Removing item {item}')
        super().removeItem(item)

    def set_items_locked(self, locked):
        """Locks or unlocks all items added by the user.

        Locked items can't be selected, moved or edited. Items that get
        added to the scene while it's locked are locked, too.
        """

        logger.debug(f'Setting items locked to {locked}')
        self.items_locked = locked
        if locked:
            self.cancel_active_modes()
            if self.edit_item:
                self.edit_item.exit_edit_mode()
            self.clearSelection()
        for item in self.items_for_save():
            item.set_locked(locked)

    def cancel_active_modes(self):
        """Cancels ongoing crop modes, rubberband modes etc, if there are
        any.
        """
        self.cancel_crop_mode()
        self.end_rubberband_mode()

    def end_rubberband_mode(self):
        if self.rubberband_item.scene():
            logger.debug('Ending rubberband selection')
            self.removeItem(self.rubberband_item)
        self.active_mode = None

    def cancel_crop_mode(self):
        """Cancels an ongoing crop mode, if there is any."""
        if self.crop_item:
            self.crop_item.exit_crop_mode(confirm=False)

    def copy_selection_to_internal_clipboard(self):
        self.internal_clipboard = []
        for item in self.selectedItems(user_only=True):
            self.internal_clipboard.append(item)

    def paste_from_internal_clipboard(self, position):
        copies = []
        for item in self.internal_clipboard:
            copy = item.create_copy()
            copies.append(copy)
        self.undo_stack.push(commands.InsertItems(self, copies, position))

    def raise_to_top(self):
        self.cancel_active_modes()
        items = self.selectedItems(user_only=True)
        z_values = map(lambda i: i.zValue(), items)
        delta = self.max_z + self.Z_STEP - min(z_values)
        logger.debug(f'Raise to top, delta: {delta}')
        for item in items:
            item.setZValue(item.zValue() + delta)

    def lower_to_bottom(self):
        self.cancel_active_modes()
        items = self.selectedItems(user_only=True)
        z_values = map(lambda i: i.zValue(), items)
        delta = self.min_z - self.Z_STEP - max(z_values)
        logger.debug(f'Lower to bottom, delta: {delta}')

        for item in items:
            item.setZValue(item.zValue() + delta)

    def user_items(self):
        """All top-level items added by the user."""

        return [item for item in self.items()
                if hasattr(item, 'save_id') and item.parentItem() is None]

    def items_for_action(self):
        """The items an organizing action should affect.

        These are the selected items, or all items if nothing is
        selected.
        """

        return self.selectedItems(user_only=True) or self.user_items()

    def items_center(self, items):
        rect = self.itemsBoundingRect(items=items)
        return (rect.topLeft() + rect.bottomRight()) / 2

    def _item_rects(self, items):
        return [self.itemsBoundingRect(items=[item]) for item in items]

    def _normalize(self, values, func):
        """Push a NormalizeItems command so that the given values become
        the same for all items.

        :param values: List of (item, value) tuples.
        :param func: Turns (target value, current value) into a scale
            factor.
        """

        if len(values) < 2:
            return
        source = self.settings.valueOrDefault('Items/normalize_source')
        if source == 'first':
            first = items_in_order([v[0] for v in values])[0]
            target = dict(values)[first]
        else:
            target = sum(v[1] for v in values) / len(values)
        logger.debug(f'Normalizing to {target} ({source})')
        items = [v[0] for v in values]
        factors = [func(target, v[1]) for v in values]
        self.undo_stack.push(commands.NormalizeItems(items, factors))

    def normalize_width_or_height(self, mode):
        """Scale the selected images to have the same width or height, as
        specified by ``mode``.

        :param mode: "width" or "height".
        """

        self.cancel_active_modes()
        items = self.items_for_action()
        values = [(item, getattr(rect, mode)())
                  for item, rect in zip(items, self._item_rects(items))]
        self._normalize(values, lambda target, value: target / value)

    def normalize_height(self):
        """Scale selected images to the same height."""
        return self.normalize_width_or_height('height')

    def normalize_width(self):
        """Scale selected images to the same width."""
        return self.normalize_width_or_height('width')

    def normalize_size(self):
        """Scale selected images to the same size.

        Size meaning the area = widh * height.
        """

        self.cancel_active_modes()
        items = self.items_for_action()
        values = [(item, rect.width() * rect.height())
                  for item, rect in zip(items, self._item_rects(items))]
        self._normalize(
            values, lambda target, value: math.sqrt(target / value))

    def normalize_longest_side(self):
        """Scale selected items so that their longest sides are equal."""

        self.cancel_active_modes()
        items = self.items_for_action()
        values = [(item, max(rect.width(), rect.height()))
                  for item, rect in zip(items, self._item_rects(items))]
        self._normalize(values, lambda target, value: target / value)

    def normalize_scale(self):
        """Give selected items the same scale factor.

        Useful for giving text notes the same text size.
        """

        self.cancel_active_modes()
        values = [(item, item.scale()) for item in self.items_for_action()]
        self._normalize(values, lambda target, value: target / value)

    def align(self, edge):
        """Align items to the outermost edge of all affected items.

        :param edge: "left", "right", "top" or "bottom"
        """

        self.cancel_active_modes()
        items = self.items_for_action()
        if len(items) < 2:
            return
        rects = self._item_rects(items)
        if edge == 'left':
            target = min(r.left() for r in rects)
            positions = [QtCore.QPointF(target, r.top()) for r in rects]
        elif edge == 'right':
            target = max(r.right() for r in rects)
            positions = [QtCore.QPointF(target - r.width(), r.top())
                         for r in rects]
        elif edge == 'top':
            target = min(r.top() for r in rects)
            positions = [QtCore.QPointF(r.left(), target) for r in rects]
        elif edge == 'bottom':
            target = max(r.bottom() for r in rects)
            positions = [QtCore.QPointF(r.left(), target - r.height())
                         for r in rects]
        else:
            raise ValueError(f'Unknown edge: {edge}')
        self.undo_stack.push(commands.ArrangeItems(self, items, positions))

    def distribute(self, vertical=False):
        """Distribute items with equal spacing between them.

        The outermost items keep their positions.
        """

        self.cancel_active_modes()
        items = self.items_for_action()
        if len(items) < 3:
            return
        pairs = list(zip(items, self._item_rects(items)))
        if vertical:
            pairs.sort(key=lambda p: p[1].top())
            start = pairs[0][1].top()
            end = max(r.bottom() for _, r in pairs)
            total = sum(r.height() for _, r in pairs)
        else:
            pairs.sort(key=lambda p: p[1].left())
            start = pairs[0][1].left()
            end = max(r.right() for _, r in pairs)
            total = sum(r.width() for _, r in pairs)
        spacing = (end - start - total) / (len(pairs) - 1)

        positions = []
        current = start
        for item, rect in pairs:
            if vertical:
                positions.append(QtCore.QPointF(rect.left(), current))
                current += rect.height() + spacing
            else:
                positions.append(QtCore.QPointF(current, rect.top()))
                current += rect.width() + spacing
        self.undo_stack.push(commands.ArrangeItems(
            self, [p[0] for p in pairs], positions))

    def stack(self):
        """Pile up items on top of each other, centered on their common
        center. The stacking order (z values) is kept.
        """

        self.cancel_active_modes()
        items = self.items_for_action()
        if len(items) < 2:
            return
        center = self.items_center(items)
        positions = [center - QtCore.QPointF(r.width() / 2, r.height() / 2)
                     for r in self._item_rects(items)]
        self.undo_stack.push(commands.ArrangeItems(self, items, positions))

    def arrange_default(self):
        default = self.settings.valueOrDefault('Items/arrange_default')
        MAPPING = {
            'optimal': self.arrange_optimal,
            'horizontal': self.arrange,
            'vertical': partial(self.arrange, vertical=True),
            'square': self.arrange_square,
        }

        MAPPING[default]()

    def arrange(self, vertical=False):
        """Arrange items in a line (horizontally or vertically)."""

        self.cancel_active_modes()

        items = sort_by_filename(self.items_for_action())
        if len(items) < 2:
            return

        gap = self.settings.valueOrDefault('Items/arrange_gap')
        center = self.items_center(items)
        positions = []
        rects = []
        for item in items:
            rects.append({
                'rect': self.itemsBoundingRect(items=[item]),
                'item': item})

        if vertical:
            rects.sort(key=lambda r: r['rect'].topLeft().y())
            sum_height = sum(map(lambda r: r['rect'].height(), rects))
            y = round(center.y() - sum_height/2)
            for rect in rects:
                positions.append(
                    QtCore.QPointF(
                        round(center.x() - rect['rect'].width()/2), y))
                y += rect['rect'].height() + gap

        else:
            rects.sort(key=lambda r: r['rect'].topLeft().x())
            sum_width = sum(map(lambda r: r['rect'].width(), rects))
            x = round(center.x() - sum_width/2)
            for rect in rects:
                positions.append(
                    QtCore.QPointF(
                        x, round(center.y() - rect['rect'].height()/2)))
                x += rect['rect'].width() + gap

        self.undo_stack.push(
            commands.ArrangeItems(self,
                                  [r['item'] for r in rects],
                                  positions))

    def arrange_optimal(self):
        self.cancel_active_modes()

        items = self.items_for_action()
        if len(items) < 2:
            return

        gap = self.settings.valueOrDefault('Items/arrange_gap')

        sizes = []
        for item in items:
            rect = self.itemsBoundingRect(items=[item])
            sizes.append((round(rect.width() + gap),
                          round(rect.height() + gap)))

        # The minimal area the items need if they could be packed optimally;
        # we use this as a starting shape for the packing algorithm
        min_area = sum(map(lambda s: s[0] * s[1], sizes))
        width = math.ceil(math.sqrt(min_area))

        positions = None
        while not positions:
            try:
                positions = rpack.pack(
                    sizes, max_width=width, max_height=width)
            except rpack.PackingImpossibleError:
                width = math.ceil(width * 1.2)

        # We want the items to center around the selection's center,
        # not (0, 0)
        center = self.items_center(items)
        bounds = rpack.bbox_size(sizes, positions)
        diff = center - QtCore.QPointF(bounds[0]/2, bounds[1]/2)
        positions = [QtCore.QPointF(*pos) + diff for pos in positions]

        self.undo_stack.push(commands.ArrangeItems(self, items, positions))

    @staticmethod
    def _shuffled(items):
        return random.sample(items, len(items))

    def arrange_square(self, order='filename'):
        """Arrange items in a square grid.

        :param order: "filename", "addition" (time added) or "random".
        """
        orders = {
            'filename': sort_by_filename,
            'addition': sort_by_addition,
            'random': self._shuffled,
        }
        self.cancel_active_modes()
        max_width = 0
        max_height = 0
        gap = self.settings.valueOrDefault('Items/arrange_gap')
        items = orders[order](self.items_for_action())

        if len(items) < 2:
            return

        for item in items:
            rect = self.itemsBoundingRect(items=[item])
            max_width = max(max_width, rect.width() + gap)
            max_height = max(max_height, rect.height() + gap)

        # We want the items to center around the selection's center,
        # not (0, 0)
        num_rows = math.ceil(math.sqrt(len(items)))
        center = self.items_center(items)
        diff = center - num_rows/2 * QtCore.QPointF(max_width, max_height)

        iter_items = iter(items)
        positions = []
        for j in range(num_rows):
            for i in range(num_rows):
                try:
                    item = next(iter_items)
                    rect = self.itemsBoundingRect(items=[item])
                    point = QtCore.QPointF(
                        i * max_width + (max_width - rect.width())/2,
                        j * max_height + (max_height - rect.height())/2)
                    positions.append(point + diff)
                except StopIteration:
                    break

        self.undo_stack.push(commands.ArrangeItems(self, items, positions))

    def duplicate_selection(self, offset):
        """Insert copies of the selected items, moved by ``offset``."""

        self.cancel_active_modes()
        items = self.selectedItems(user_only=True)
        if not items:
            return
        center = self.items_center(items)
        copies = [item.create_copy() for item in items]
        self.undo_stack.push(
            commands.InsertItems(self, copies, center + offset))

    def set_grayscale_canvas(self, value):
        """Show all images in grayscale (view only, not saved)."""
        self.grayscale_canvas = value
        self.update()

    def flip_items(self, vertical=False):
        """Flip selected items."""
        self.cancel_active_modes()
        self.undo_stack.push(
            commands.FlipItems(self.selectedItems(user_only=True),
                               self.get_selection_center(),
                               vertical=vertical))

    def crop_items(self):
        """Crop selected item."""

        if self.crop_item:
            return
        if self.has_single_image_selection():
            item = self.selectedItems(user_only=True)[0]
            if item.is_image:
                item.enter_crop_mode()

    def sample_color_at(self, position):
        item_at_pos = self.itemAt(position, self.views()[0].transform())
        if item_at_pos:
            return item_at_pos.sample_color_at(position)

    def select_all_items(self):
        self.cancel_active_modes()
        path = QtGui.QPainterPath()
        path.addRect(self.itemsBoundingRect())
        # This is faster than looping through all items and calling setSelected
        self.setSelectionArea(path)

    def deselect_all_items(self):
        self.cancel_active_modes()
        self.clearSelection()

    def has_selection(self):
        """Checks whether there are currently items selected."""

        return bool(self.selectedItems(user_only=True))

    def has_single_selection(self):
        """Checks whether there's currently exactly one item selected."""

        return len(self.selectedItems(user_only=True)) == 1

    def has_multi_selection(self):
        """Checks whether there are currently more than one items selected."""

        return len(self.selectedItems(user_only=True)) > 1

    def has_single_image_selection(self):
        """Checks whether the current selection is a single image."""

        if self.has_single_selection():
            return self.selectedItems(user_only=True)[0].is_image
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Right-click invokes the context menu on the
            # GraphicsView. We don't need it here.
            return

        if self.items_locked:
            # Neither items nor the rubberband react to the mouse, but
            # double clicking still fits the item into the view
            item_at_pos = self.itemAt(
                event.scenePos(), self.views()[0].transform())
            if item_at_pos:
                self.views()[0].reset_previous_transform(
                    toggle_item=item_at_pos)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.event_start = event.scenePos()
            self.last_move_delta = None
            item_at_pos = self.itemAt(
                event.scenePos(), self.views()[0].transform())

            if self.edit_item:
                if item_at_pos != self.edit_item:
                    self.edit_item.exit_edit_mode()
                else:
                    super().mousePressEvent(event)
                    return
            if self.crop_item:
                if item_at_pos != self.crop_item:
                    self.cancel_crop_mode()
                else:
                    super().mousePressEvent(event)
                    return
            if item_at_pos:
                self.active_mode = self.MOVE_MODE
            elif self.items():
                self.active_mode = self.RUBBERBAND_MODE

        super().mousePressEvent(event)
        if self.active_mode == self.MOVE_MODE:
            self.start_move_snapping()

    def start_move_snapping(self):
        """Remember the selection's bounding rect and the rects of the
        other items when starting to move items."""

        self.move_start_rect = None
        self.snap_others = []
        if not self.has_selection():
            return
        self.move_start_rect = self.itemsBoundingRect(selection_only=True)
        view = self.views()[0] if self.views() else None
        if getattr(view, 'snap_to_items', False):
            selected = set(self.selectedItems(user_only=True))
            self.snap_others = [
                self.itemsBoundingRect(items=[item])
                for item in self.items_for_save()
                if item not in selected and item.isVisible()]

    def snap_move_delta(self, delta, modifiers, axes=(True, True)):
        """Correct the move delta according to grid and item snapping.

        Holding Alt turns snapping off temporarily.
        """

        view = self.views()[0] if self.views() else None
        if (view is None or self.move_start_rect is None
                or modifiers & Qt.KeyboardModifier.AltModifier):
            return delta, []
        grid = (view.grid_size()
                if getattr(view, 'snap_to_grid', False) else None)
        others = (self.snap_others
                  if getattr(view, 'snap_to_items', False) else None)
        if not grid and not others:
            return delta, []
        return snapping.snap_delta(
            self.move_start_rect, delta, grid_size=grid, others=others,
            threshold=view.snap_threshold(), axes=axes)

    def set_snap_guides(self, guides):
        if guides or self.snap_guides:
            self.snap_guides = guides
            for view in self.views():
                view.viewport().update()

    def mouseDoubleClickEvent(self, event):
        self.cancel_active_modes()
        item = self.itemAt(event.scenePos(), self.views()[0].transform())
        if item:
            if not item.isSelected():
                item.setSelected(True)
            if item.is_editable and not self.items_locked:
                item.enter_edit_mode()
                self.mousePressEvent(event)
            else:
                self.views()[0].fit_rect(
                    self.itemsBoundingRect(items=[item]),
                    toggle_item=item)
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self.active_mode == self.RUBBERBAND_MODE:
            if not self.rubberband_item.scene():
                logger.debug('Activating rubberband selection')
                self.addItem(self.rubberband_item)
                self.rubberband_item.bring_to_front()
            self.rubberband_item.fit(self.event_start, event.scenePos())
            self.setSelectionArea(self.rubberband_item.shape())
            self.views()[0].reset_previous_transform()
        super().mouseMoveEvent(event)
        if self.is_moving_items():
            # Qt has moved the items by the raw mouse delta; correct
            # that if the move is constrained to an axis
            raw_delta = event.scenePos() - self.event_start
            delta = self.constrain_move_delta(raw_delta, event.modifiers())
            axes = (True, True)
            if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                # Don't leave the axis the move is constrained to
                axes = (delta.x() != 0, delta.y() != 0)
            delta, guides = self.snap_move_delta(
                delta, event.modifiers(), axes)
            self.set_snap_guides(guides)
            correction = raw_delta - delta
            if not correction.isNull():
                for item in self.selectedItems(user_only=True):
                    if item.flags() & item.GraphicsItemFlag.ItemIsMovable:
                        item.setPos(item.pos() - correction)
            self.last_move_delta = delta

    def is_moving_items(self):
        return (self.active_mode == self.MOVE_MODE
                and self.has_selection()
                and self.multi_select_item.active_mode is None
                and self.selectedItems()[0].active_mode is None)

    @staticmethod
    def constrain_move_delta(delta, modifiers):
        """With Shift held, restrict moving to the dominant axis."""

        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            if abs(delta.x()) >= abs(delta.y()):
                return QtCore.QPointF(delta.x(), 0)
            return QtCore.QPointF(0, delta.y())
        return QtCore.QPointF(delta)

    def mouseReleaseEvent(self, event):
        if self.active_mode == self.RUBBERBAND_MODE:
            self.end_rubberband_mode()
        if self.is_moving_items():
            delta = getattr(self, 'last_move_delta', None)
            if delta is None:
                delta = event.scenePos() - self.event_start
            if not delta.isNull():
                self.undo_stack.push(
                    commands.MoveItemsBy(self.selectedItems(),
                                         delta,
                                         ignore_first_redo=True))
        self.set_snap_guides([])
        self.move_start_rect = None
        self.snap_others = []
        self.active_mode = None
        super().mouseReleaseEvent(event)

    def selectedItems(self, user_only=False):
        """If ``user_only`` is set to ``True``, only return items added
        by the user (i.e. no multi select outlines and other UI items).

        User items are items that have a ``save_id`` attribute.
        """

        items = super().selectedItems()
        if user_only:
            return list(filter(lambda i: hasattr(i, 'save_id'), items))
        return items

    def items_by_type(self, itype):
        """Returns all items of the given type."""

        return filter(lambda i: getattr(i, 'TYPE', None) == itype,
                      self.items())

    def items_for_save(self):

        """Returns the items that are to be saved.

        Items to be saved are items that have a save_id attribute.
        """

        return filter(lambda i: hasattr(i, 'save_id'),
                      self.items(order=Qt.SortOrder.AscendingOrder))

    def clear_save_ids(self):
        for item in self.items_for_save():
            item.save_id = None

    def on_view_scale_change(self):
        for item in self.selectedItems():
            item.on_view_scale_change()

    def itemsBoundingRect(self, selection_only=False, items=None):
        """Returns the bounding rect of the scene's items; either all of them
        or only selected ones, or the items givin in ``items``.

        Re-implemented to not include the items's selection handles.
        """

        def filter_user_items(ilist):
            return list(filter(lambda i: hasattr(i, 'save_id'), ilist))

        if selection_only:
            base = filter_user_items(self.selectedItems())
        elif items:
            base = items
        else:
            base = filter_user_items(self.items())

        if not base:
            return QtCore.QRectF(0, 0, 0, 0)

        x = []
        y = []

        for item in base:
            for corner in item.corners_scene_coords:
                x.append(corner.x())
                y.append(corner.y())

        return QtCore.QRectF(
            QtCore.QPointF(min(x), min(y)),
            QtCore.QPointF(max(x), max(y)))

    def get_selection_center(self):
        rect = self.itemsBoundingRect(selection_only=True)
        return (rect.topLeft() + rect.bottomRight()) / 2

    def on_selection_change(self):
        if self._clear_ongoing:
            # Ignore events while clearing the scene since the
            # multiselect item will get cleared, too
            return
        if self.has_multi_selection():
            self.multi_select_item.fit_selection_area(
                self.itemsBoundingRect(selection_only=True))
        if self.has_multi_selection() and not self.multi_select_item.scene():
            self.addItem(self.multi_select_item)
            self.multi_select_item.bring_to_front()
        if not self.has_multi_selection() and self.multi_select_item.scene():
            self.removeItem(self.multi_select_item)

    def on_change(self, region):
        if self._clear_ongoing:
            # Ignore events while clearing the scene since the
            # multiselect item will get cleared, too
            return
        if (self.multi_select_item.scene()
                and self.multi_select_item.active_mode is None):
            self.multi_select_item.fit_selection_area(
                self.itemsBoundingRect(selection_only=True))

    def add_item_later(self, itemdata, selected=False):
        """Keep an item for adding later via ``add_queued_items``

        :param dict itemdata: Defines the item's data
        :param bool selected: Whether the item is initialised as selected
        """

        self.items_to_add.put((itemdata, selected))

    def add_queued_items(self):
        """Adds items added via ``add_item_later``"""

        while not self.items_to_add.empty():
            data, selected = self.items_to_add.get()
            typ = data.pop('type')
            cls = item_registry.get(typ)
            if not cls:
                # Just in case we add new item types in future versions
                logger.warning(f'Encountered item of unknown type: {typ}')
                cls = BeeErrorItem
                data['data'] = {
                    'text': _('Item of unknown type: {typ}').format(typ=typ)}
            item = cls.create_from_data(**data)
            # Set the values common to all item types:
            item.update_from_data(**data)
            self.addItem(item)
            # Force recalculation of min/max z values:
            item.setZValue(item.zValue())
            if selected:
                item.setSelected(True)
                item.bring_to_front()
            if getattr(item, 'pending_parent_id', None) is not None:
                self.pending_parents[item] = item.pending_parent_id
        self.resolve_parents()

    def resolve_parents(self):
        """Assign loaded items to their parents.

        Items loaded from a bee file reference their parent by its
        save_id. Since items are loaded in batches, a parent might not
        be in the scene yet; those children stay pending until a later
        call.
        """

        if not self.pending_parents:
            return

        by_save_id = {}
        for item in self.items():
            save_id = (getattr(item, 'save_id', None)
                       or getattr(item, 'original_save_id', None))
            if save_id is not None:
                by_save_id[save_id] = item

        for child, parent_id in list(self.pending_parents.items()):
            parent = by_save_id.get(parent_id)
            if parent is None or parent is child:
                continue
            # Positions are stored relative to the parent, so we don't
            # need to map them:
            child.setParentItem(parent)
            child.pending_parent_id = None
            del self.pending_parents[child]
