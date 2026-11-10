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

from myRef import commands
from myRef import hierarchy
from myRef import snapping
from myRef.config import BeeSettings
from myRef.i18n import _
from myRef.items import (
    item_registry,
    items_in_order,
    sibling_order,
    sort_by_addition,
    sort_by_filename,
    BeeErrorItem,
    BeeGroupItem,
)
from myRef.selection import MultiSelectItem, RubberbandItem


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
        self.selection_history = []
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
        self.selection_history = []
        self._clear_ongoing = False

    def addItem(self, item):
        logger.debug(f'Adding item {item}')
        super().addItem(item)
        if hasattr(item, 'set_locked'):
            # Children get added together with their parent
            for i in [item] + hierarchy.descendants(item):
                i.set_locked(self.items_locked)

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
        for item in self.selected_top_items():
            self.internal_clipboard.append(item)

    def paste_from_internal_clipboard(self, position):
        copies = []
        for item in self.internal_clipboard:
            copy = item.copy_with_children()
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

    def selected_top_items(self):
        """The selected items without those whose ancestors are
        selected, too (they get transformed along with their
        ancestors)."""

        return hierarchy.top_most(self.selectedItems(user_only=True))

    def groups(self):
        """All groups, innermost first."""

        groups = list(self.items_by_type(BeeGroupItem.TYPE))
        groups.sort(key=lambda g: len(hierarchy.ancestors(g)),
                    reverse=True)
        return groups

    def fit_groups(self):
        """Fit all groups to their children."""

        for group in self.groups():
            group.fit_to_children()

    def open_group(self, group):
        """Open a group (and the groups it is in) so that its children
        can be selected on their own."""

        for g in reversed([group] + hierarchy.ancestors(group)):
            if isinstance(g, BeeGroupItem):
                g.set_open(True)

    def close_unused_groups(self):
        """Close open groups that have no selected items inside."""

        selected = self.selectedItems(user_only=True)
        for group in self.groups():
            if group.is_open and not any(
                    group in hierarchy.ancestors(item) for item in selected):
                group.set_open(False)

    def effective_item(self, item):
        """The item that a click on the given item applies to: the
        outermost closed group containing it, or the item itself."""

        result = item
        for ancestor in hierarchy.ancestors(item):
            if isinstance(ancestor, BeeGroupItem) and not ancestor.is_open:
                result = ancestor
        return result

    def _interactive_item(self, item):
        """The item that reacts to a click on the given item, if any."""

        if not isinstance(item, QtWidgets.QGraphicsItem):
            return item
        if hierarchy.is_user_item(item):
            item = self.effective_item(item)
        if item.flags() & item.GraphicsItemFlag.ItemIsSelectable:
            return item
        return None

    def interactive_item_at(self, pos):
        """The topmost item at the given position that reacts to the
        mouse. Locked items are skipped; for items in closed groups,
        the group is returned."""

        if isinstance(pos, QtCore.QPoint):
            pos = QtCore.QPointF(pos)
        view = self.views()[0]
        first = self.itemAt(pos, view.transform())
        if first is None:
            return None
        result = self._interactive_item(first)
        if result is not None:
            return result
        for item in self.items(pos,
                               Qt.ItemSelectionMode.IntersectsItemShape,
                               Qt.SortOrder.DescendingOrder,
                               view.transform()):
            result = self._interactive_item(item)
            if result is not None:
                return result
        return None

    def group_selection(self):
        """Put the selected items into a new group.

        :returns: The number of selected items that have been left
            out because they have a different parent than the first one.
        """

        self.cancel_active_modes()
        items = self.selected_top_items()
        if not items:
            return 0
        # Items can only be grouped if they share the same parent
        parent = items[0].parentItem()
        grouped = [item for item in items if item.parentItem() is parent]
        self.undo_stack.push(
            commands.GroupItems(self, grouped, BeeGroupItem()))
        return len(items) - len(grouped)

    def target_groups(self):
        """The groups that group actions (style, title...) apply to.

        These are the selected groups or, if no group is selected, the
        group that contains all selected items.
        """

        items = self.selected_top_items()
        groups = [item for item in items if isinstance(item, BeeGroupItem)]
        if groups:
            return groups
        parents = {item.parentItem() for item in items}
        if len(parents) == 1:
            parent = parents.pop()
            if isinstance(parent, BeeGroupItem):
                return [parent]
        return []

    def selected_group(self):
        """The group if exactly one group is selected and nothing
        else, otherwise ``None``. Organizing actions then affect the
        group's contents, as if they were all selected."""

        items = self.selected_top_items()
        if len(items) == 1 and isinstance(items[0], BeeGroupItem):
            return items[0]
        return None

    def target_group(self):
        groups = self.target_groups()
        return groups[0] if groups else None

    def add_selection_to_group(self):
        """Put the selected items into the selected group.

        Exactly one group has to be selected along with the items.

        :returns: Whether the items have been added
        """

        self.cancel_active_modes()
        items = self.selected_top_items()
        groups = [item for item in items if isinstance(item, BeeGroupItem)]
        others = [item for item in items if item not in groups]
        if len(groups) != 1 or not others:
            return False
        self.move_in_hierarchy(others, groups[0], text='Add to group')
        return True

    def remove_selection_from_group(self):
        """Take the selected items out of their groups; they go to the
        groups' parents, right after the group they've been in."""

        self.cancel_active_modes()
        items = [item for item in self.selected_top_items()
                 if isinstance(item.parentItem(), BeeGroupItem)]
        if not items:
            return
        by_group = {}
        for item in items:
            by_group.setdefault(item.parentItem(), []).append(item)
        self.undo_stack.beginMacro('Remove from group')
        for group, children in by_group.items():
            parent = group.parentItem()
            siblings = self.ordered_children(parent)
            index = siblings.index(group) + 1
            self.move_in_hierarchy(children, parent, index,
                                   text='Remove from group')
        self.undo_stack.endMacro()

    def enter_group(self):
        """Select the children of the target group."""

        group = self.target_group()
        if group is None:
            return
        children = self.ordered_children(group)
        if children:
            self.select_items(children)

    def exit_group(self):
        """Select the group that contains the selected items."""

        self.cancel_active_modes()
        parents = {item.parentItem() for item in self.selected_top_items()}
        groups = [p for p in parents if isinstance(p, BeeGroupItem)]
        if len(groups) == 1:
            self.select_items(groups)

    def ungroup_selection(self):
        """Dissolve the selected groups."""

        self.cancel_active_modes()
        groups = [item for item in self.selected_top_items()
                  if isinstance(item, BeeGroupItem)]
        if groups:
            self.undo_stack.push(commands.UngroupItems(self, groups))

    def parent_selection(self):
        """Make the selected items children of the item that has been
        selected first."""

        self.cancel_active_modes()
        selected = self.selectedItems(user_only=True)
        if len(selected) < 2:
            return
        history = [i for i in self.selection_history if i in selected]
        parent = history[0] if history else items_in_order(selected)[0]
        forbidden = set([parent] + hierarchy.ancestors(parent))
        items = [item for item in hierarchy.top_most(selected)
                 if item not in forbidden]
        self.move_in_hierarchy(items, parent, text='Parent items')

    def unparent_selection(self):
        """Move the selected items to the top level of the hierarchy."""

        self.cancel_active_modes()
        items = [item for item in self.selected_top_items()
                 if item.parentItem() is not None]
        if items:
            self.move_in_hierarchy(items, None, text='Unparent items')

    def ordered_children(self, parent):
        """The children of the given item (or the top-level items for
        ``None``) in hierarchy order."""

        if parent is None:
            return sibling_order(self.user_items())
        return sibling_order(hierarchy.user_children(parent))

    def move_in_hierarchy(self, items, parent, index=None,
                          text='Change hierarchy'):
        """Make the items children of ``parent`` (or top-level items
        for ``None``) and put them at the given position among the
        parent's children (at the end for ``None``)."""

        items = hierarchy.top_most(items)
        if parent is not None:
            forbidden = set(items)
            if parent in forbidden or forbidden.intersection(
                    hierarchy.ancestors(parent)):
                logger.debug('Not moving items into their own descendants')
                return
        siblings = self.ordered_children(parent)
        if index is None:
            index = len(siblings)
        moving = set(items)
        new_order = ([s for s in siblings[:index] if s not in moving]
                     + items
                     + [s for s in siblings[index:] if s not in moving])
        changes = [(item, parent, i) for i, item in enumerate(new_order)]
        self.undo_stack.push(commands.ChangeHierarchy(self, changes, text))

    def select_items(self, items):
        """Select the given items, opening the groups they are in."""

        self.cancel_active_modes()
        self.clearSelection()
        for item in items:
            for ancestor in hierarchy.ancestors(item):
                if isinstance(ancestor, BeeGroupItem):
                    self.open_group(ancestor)
                    break
            item.setSelected(True)

    def drop_target_group(self, pos, items):
        """The group under the given position into which the given
        (moving) items would be dropped, or ``None``.

        That's the innermost group under the position, unless it's
        inside a closed group: Then the outermost closed group is the
        target, as for clicks.
        """

        if isinstance(pos, QtCore.QPoint):
            pos = QtCore.QPointF(pos)
        excluded = set(items)
        for item in items:
            excluded.update(hierarchy.descendants(item))
        view = self.views()[0]
        for item in self.items(pos,
                               Qt.ItemSelectionMode.IntersectsItemShape,
                               Qt.SortOrder.DescendingOrder,
                               view.transform()):
            if isinstance(item, BeeGroupItem) and item not in excluded:
                target = self.effective_item(item)
                return None if target in excluded else target
        return None

    def items_to_drop(self, pos, items):
        """After moving items, they get put into the group they have
        been dropped on, or taken out of their group if they have been
        dropped outside of it.

        Only items that are top-level items or in a group are affected
        (not children of images etc.).

        :returns: (items, target group or ``None``)
        """

        if not self.settings.valueOrDefault('Items/drag_into_groups'):
            return [], None
        target = self.drop_target_group(pos, items)
        items = [item for item in hierarchy.top_most(items)
                 if (item.parentItem() is None
                     or isinstance(item.parentItem(), BeeGroupItem))
                 and item.parentItem() is not target]
        return items, target

    def items_for_action(self, items=None):
        """The items an organizing action should affect.

        These are the given items (e.g. the contents of a group) or, if
        ``None``, the selected items, or all items if nothing is
        selected.
        """

        if items is not None:
            return list(items)
        return self.selectedItems(user_only=True) or self.user_items()

    def group_contents(self, group):
        """The items that group-scoped actions affect: The group's
        direct children (subgroups count as one item)."""

        return self.ordered_children(group)

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

    def normalize_width_or_height(self, mode, items=None):
        """Scale the selected images to have the same width or height, as
        specified by ``mode``.

        :param mode: "width" or "height".
        """

        self.cancel_active_modes()
        items = self.items_for_action(items)
        values = [(item, getattr(rect, mode)())
                  for item, rect in zip(items, self._item_rects(items))]
        self._normalize(values, lambda target, value: target / value)

    def normalize_height(self, items=None):
        """Scale selected images to the same height."""
        return self.normalize_width_or_height('height', items)

    def normalize_width(self, items=None):
        """Scale selected images to the same width."""
        return self.normalize_width_or_height('width', items)

    def normalize_size(self, items=None):
        """Scale selected images to the same size.

        Size meaning the area = widh * height.
        """

        self.cancel_active_modes()
        items = self.items_for_action(items)
        values = [(item, rect.width() * rect.height())
                  for item, rect in zip(items, self._item_rects(items))]
        self._normalize(
            values, lambda target, value: math.sqrt(target / value))

    def normalize_longest_side(self, items=None):
        """Scale selected items so that their longest sides are equal."""

        self.cancel_active_modes()
        items = self.items_for_action(items)
        values = [(item, max(rect.width(), rect.height()))
                  for item, rect in zip(items, self._item_rects(items))]
        self._normalize(values, lambda target, value: target / value)

    def normalize_scale(self, items=None):
        """Give selected items the same scale factor.

        Useful for giving text notes the same text size.
        """

        self.cancel_active_modes()
        values = [(item, item.scale())
                  for item in self.items_for_action(items)]
        self._normalize(values, lambda target, value: target / value)

    def align(self, edge, items=None):
        """Push items to one side of all affected items.

        Every item moves towards the given edge until it reaches it or
        another item (kept apart by the arrange gap), so nothing ends
        up on top of anything else.

        :param edge: "left", "right", "top" or "bottom"
        """

        self.cancel_active_modes()
        items = self.items_for_action(items)
        if len(items) < 2:
            return
        if edge not in ('left', 'right', 'top', 'bottom'):
            raise ValueError(f'Unknown edge: {edge}')
        rects = self._item_rects(items)
        gap = self.settings.valueOrDefault('Items/arrange_gap')
        positions = self._push_positions(edge, rects, gap)
        self.undo_stack.push(commands.ArrangeItems(self, items, positions))

    @staticmethod
    def _push_positions(edge, rects, gap):
        """New top left positions for the given rects when pushed to
        ``edge``, keeping ``gap`` between rects that share a row/column.
        """

        horizontal = edge in ('left', 'right')
        sign = 1 if edge in ('left', 'top') else -1

        def lo(r):  # start of rect along the push direction
            return r.left() if horizontal else r.top()

        def hi(r):
            return r.right() if horizontal else r.bottom()

        def cross_overlap(r1, r2):
            if horizontal:
                return r1.top() < r2.bottom() and r1.bottom() > r2.top()
            return r1.left() < r2.right() and r1.right() > r2.left()

        if sign == 1:
            bound = min(lo(r) for r in rects)
            order = sorted(range(len(rects)), key=lambda i: lo(rects[i]))
        else:
            bound = max(hi(r) for r in rects)
            order = sorted(range(len(rects)), key=lambda i: -hi(rects[i]))

        placed = []  # (index, start, end) along the push direction
        positions = [None] * len(rects)
        for i in order:
            r = rects[i]
            length = hi(r) - lo(r)
            if sign == 1:
                start = bound
                for j, p_start, p_end in placed:
                    if cross_overlap(r, rects[j]):
                        start = max(start, p_end + gap)
                end = start + length
            else:
                end = bound
                for j, p_start, p_end in placed:
                    if cross_overlap(r, rects[j]):
                        end = min(end, p_start - gap)
                start = end - length
            placed.append((i, start, end))
            if horizontal:
                positions[i] = QtCore.QPointF(start, r.top())
            else:
                positions[i] = QtCore.QPointF(r.left(), start)
        return positions

    def distribute(self, vertical=False, items=None):
        """Distribute items with equal spacing between them.

        The outermost items keep their positions.
        """

        self.cancel_active_modes()
        items = self.items_for_action(items)
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

    def stack(self, items=None):
        """Pile up items on top of each other, centered on their common
        center. The stacking order (z values) is kept.
        """

        self.cancel_active_modes()
        items = self.items_for_action(items)
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

    def arrange(self, vertical=False, items=None):
        """Arrange items in a line (horizontally or vertically)."""

        self.cancel_active_modes()

        items = sort_by_filename(self.items_for_action(items))
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

    def arrange_optimal(self, items=None):
        self.cancel_active_modes()

        items = self.items_for_action(items)
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

    def arrange_square(self, order='filename', items=None):
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
        items = orders[order](self.items_for_action(items))

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
        items = self.selected_top_items()
        if not items:
            return
        center = self.items_center(items)
        copies = [item.copy_with_children() for item in items]
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

        if (event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier):
            url = self.link_at(event.scenePos())
            if url:
                self.views()[0].open_link(url)
                event.accept()
                return

        if event.button() == Qt.MouseButton.LeftButton:
            self.event_start = event.scenePos()
            self.last_move_delta = None
            item_at_pos = self.interactive_item_at(event.scenePos())

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
            # Don't snap to items that move along or contain the
            # moving items
            selected = self.selectedItems(user_only=True)
            excluded = set(selected)
            for item in selected:
                excluded.update(hierarchy.descendants(item))
                excluded.update(hierarchy.ancestors(item))
            self.snap_others = [
                self.itemsBoundingRect(items=[item])
                for item in self.items_for_save()
                if item not in excluded and item.isVisible()]

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

    def link_at(self, pos):
        """The link target in a text note at the given scene position."""

        for item in self.items(pos):
            if hasattr(item, 'anchor_at') and item.isVisible():
                url = item.anchor_at(item.mapFromScene(pos))
                if url:
                    return url
                return None
        return None

    def mouseDoubleClickEvent(self, event):
        self.cancel_active_modes()
        item = self.itemAt(event.scenePos(), self.views()[0].transform())
        if (isinstance(item, BeeGroupItem)
                and self.effective_item(item) is item
                and item.title_contains(item.mapFromScene(event.scenePos()))
                and not self.items_locked):
            # Rename the group via its title
            self.select_items([item])
            self.views()[0].rename_item(item)
            return
        if item and hierarchy.is_user_item(item):
            target = self.effective_item(item)
            if (isinstance(target, BeeGroupItem) and target is not item
                    and not self.items_locked):
                # Enter the group and select the item that has been
                # clicked on, in this group's level
                self.clearSelection()
                self.open_group(target)
                inner = self.interactive_item_at(event.scenePos())
                if inner:
                    inner.setSelected(True)
                return
            item = target
        if item:
            if not item.isSelected():
                item.setSelected(True)
            if item.is_editable and not self.items_locked:
                item.enter_edit_mode()
                if getattr(item, 'TYPE', None) != 'drawing':
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
                for item in self.selected_top_items():
                    if item.flags() & item.GraphicsItemFlag.ItemIsMovable:
                        item.setPos(
                            item.pos()
                            - hierarchy.scene_delta_to_parent(
                                item, correction))
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
                items = self.selected_top_items()
                move = commands.MoveItemsBy(items,
                                            delta,
                                            ignore_first_redo=True)
                drop, target = self.items_to_drop(event.scenePos(), items)
                if drop:
                    self.undo_stack.beginMacro('Move items')
                    self.undo_stack.push(move)
                    if target:
                        self.open_group(target)
                    self.move_in_hierarchy(drop, target, text='Move items')
                    self.undo_stack.endMacro()
                else:
                    self.undo_stack.push(move)
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
        selected = self.selectedItems(user_only=True)
        self.selection_history = (
            [i for i in self.selection_history if i in selected]
            + items_in_order(
                [i for i in selected if i not in self.selection_history]))
        self.close_unused_groups()
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
        self.fit_groups()

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
        self.fit_groups()
