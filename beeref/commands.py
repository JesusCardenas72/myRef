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

import time

from PyQt6 import QtCore, QtGui

from beeref import hierarchy


def is_group(item):
    return getattr(item, 'TYPE', None) == 'group'


def fit_groups(scene):
    """Fit all groups to their children, innermost groups first."""
    if hasattr(scene, 'fit_groups'):
        scene.fit_groups()


def remove_empty_groups(scene, candidates):
    """Remove groups that have no children anymore.

    Removing a group can leave its parent group empty, too.

    :returns: List of (group, parent) for ``restore_groups``
    """
    removed = []
    for group in candidates:
        while (group is not None and is_group(group) and group.scene()
               and not hierarchy.user_children(group)):
            parent = group.parentItem()
            removed.append((group, parent))
            scene.removeItem(group)
            group = parent
    return removed


def restore_groups(scene, removed):
    """Re-add groups removed by ``remove_empty_groups``."""
    for group, parent in reversed(removed):
        add_to_parent(scene, group, parent)


def add_to_parent(scene, item, parent):
    """Add the item to the scene, as child of ``parent`` if given.

    Items removed from the scene lose their parent, but keep their
    position relative to it.
    """
    if parent is not None:
        item.setParentItem(parent)
    else:
        scene.addItem(item)


def local_anchor(item, anchor):
    """Map a scene anchor to item coordinates.

    An anchor of ``None`` means the item's own center.
    """
    if anchor is None:
        return item.center
    return item.mapFromScene(anchor)


class InsertItems(QtGui.QUndoCommand):

    def __init__(self, scene, items, position=None, ignore_first_redo=False):
        super().__init__('Insert items')
        self.scene = scene
        self.items = items
        self.position = position
        self.ignore_first_redo = ignore_first_redo

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return

        self.scene.deselect_all_items()
        if self.position:
            self.old_positions = []
            rect = self.scene.itemsBoundingRect(items=self.items)
            for item in self.items:
                self.old_positions.append(item.pos())
                item.setPos(item.pos() + self.position - rect.center())
        for item in self.items:
            if getattr(item, 'added_at', None) is None:
                item.added_at = time.time()
            self.scene.addItem(item)
            item.setSelected(True)
            item.bring_to_front()

    def undo(self):
        self.scene.deselect_all_items()
        for item in self.items:
            self.scene.removeItem(item)
        if self.position:
            for item, pos in zip(self.items, self.old_positions):
                item.setPos(pos)


class DeleteItems(QtGui.QUndoCommand):
    """Delete items (and their children). Groups that end up empty are
    deleted, too."""

    def __init__(self, scene, items):
        super().__init__('Delete items')
        self.scene = scene
        # Children get removed together with their parents:
        self.items = hierarchy.top_most(items)
        self.parents = [item.parentItem() for item in self.items]
        self.removed_groups = []

    def redo(self):
        for item in self.items:
            self.scene.removeItem(item)
        self.removed_groups = remove_empty_groups(
            self.scene, [p for p in self.parents if p is not None])
        fit_groups(self.scene)

    def undo(self):
        self.scene.deselect_all_items()
        restore_groups(self.scene, self.removed_groups)
        for item, parent in zip(self.items, self.parents):
            add_to_parent(self.scene, item, parent)
            item.setSelected(True)
        fit_groups(self.scene)


class MoveItemsBy(QtGui.QUndoCommand):

    def __init__(self, items, delta, ignore_first_redo=False):
        super().__init__('Move items')
        self.items = items
        self.delta = delta
        self.ignore_first_redo = ignore_first_redo

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return
        for item in self.items:
            delta = hierarchy.scene_delta_to_parent(item, self.delta)
            item.moveBy(delta.x(), delta.y())

    def undo(self):
        for item in self.items:
            delta = hierarchy.scene_delta_to_parent(item, self.delta)
            item.moveBy(-delta.x(), -delta.y())


class ScaleItemsBy(QtGui.QUndoCommand):
    """Scale items by a given factor around the given anchor.

    An anchor of ``None`` scales each item around its own center.
    """

    def __init__(self, items, factor, anchor, ignore_first_redo=False):
        super().__init__('Scale items')
        self.ignore_first_redo = ignore_first_redo
        self.items = items
        self.factor = factor
        self.anchor = anchor

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return
        for item in self.items:
            item.setScale(item.scale() * self.factor,
                          local_anchor(item, self.anchor))

    def undo(self):
        for item in self.items:
            item.setScale(item.scale() / self.factor,
                          local_anchor(item, self.anchor))


class RotateItemsBy(QtGui.QUndoCommand):
    """Rotate items by a given delta around the given anchor.

    An anchor of ``None`` rotates each item around its own center.
    """

    def __init__(self, items, delta, anchor, ignore_first_redo=False):
        super().__init__('Rotate items')
        self.ignore_first_redo = ignore_first_redo
        self.items = items
        self.delta = delta
        self.anchor = anchor

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return
        for item in self.items:
            item.setRotation(
                item.rotation() + self.delta * item.flip(),
                local_anchor(item, self.anchor))

    def undo(self):
        for item in self.items:
            item.setRotation(item.rotation() - self.delta * item.flip(),
                             local_anchor(item, self.anchor))


class NormalizeItems(QtGui.QUndoCommand):

    def __init__(self, items, scale_factors):
        super().__init__('Normalize items')
        self.items = items
        self.scale_factors = scale_factors

    def redo(self):
        self.old_scale_factors = []
        for item, factor in zip(self.items, self.scale_factors):
            self.old_scale_factors.append(item.scale())
            item.setScale(item.scale() * factor, item.center)

    def undo(self):
        for item, factor in zip(self.items, self.old_scale_factors):
            item.setScale(factor, item.center)


class FlipItems(QtGui.QUndoCommand):

    def __init__(self, items, anchor, vertical):
        super().__init__('Flip items')
        self.items = items
        self.anchor = anchor
        self.vertical = vertical

    def redo(self):
        for item in self.items:
            item.do_flip(self.vertical, item.mapFromScene(self.anchor))

    def undo(self):
        self.redo()


class ResetScale(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Scale')
        self.items = items

    def redo(self):
        self.old_scale_factors = []
        for item in self.items:
            self.old_scale_factors.append(item.scale())
            item.setScale(1, anchor=item.center)

    def undo(self):
        for item, scale_factor in zip(self.items, self.old_scale_factors):
            item.setScale(scale_factor, anchor=item.center)


class ResetRotation(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Rotation')
        self.items = items

    def redo(self):
        self.old_rotations = []
        for item in self.items:
            self.old_rotations.append(item.rotation())
            item.setRotation(0, anchor=item.center)

    def undo(self):
        for item, rotation in zip(self.items, self.old_rotations):
            item.setRotation(rotation, anchor=item.center)


class ResetFlip(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Flip')
        self.items = items

    def redo(self):
        self.old_flips = []
        for item in self.items:
            self.old_flips.append(item.flip())
            if item.flip() == -1:
                item.do_flip(anchor=item.center)

    def undo(self):
        for item, flip in zip(self.items, self.old_flips):
            if flip == -1:
                item.do_flip(anchor=item.center)


class ResetCrop(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Crop')
        self.items = [item for item in items if item.is_image]

    def redo(self):
        self.old_crops = []
        for item in self.items:
            self.old_crops.append(item.crop)
            item.reset_crop()

    def undo(self):
        for item, crop in zip(self.items, self.old_crops):
            item.crop = crop


class ResetTransforms(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset All Transformations')
        self.items = items

    def redo(self):
        self.old_values = []
        for item in self.items:
            values = {
                'scale': item.scale(),
                'rotation': item.rotation(),
                'flip': item.flip(),
            }
            if item.is_image:
                values['crop'] = item.crop
                item.reset_crop()
            self.old_values.append(values)

            item.setScale(1, anchor=item.center)
            item.setRotation(0, anchor=item.center)
            if item.flip() == -1:
                item.do_flip(anchor=item.center)

    def undo(self):
        for item, old in zip(self.items, self.old_values):
            item.setScale(old['scale'], anchor=item.center)
            item.setRotation(old['rotation'], anchor=item.center)
            if old['flip'] == -1:
                item.do_flip(anchor=item.center)
            if item.is_image:
                item.crop = old['crop']


class ArrangeItems(QtGui.QUndoCommand):

    def __init__(self, scene, items, positions):
        super().__init__('Arrange items')
        self.scene = scene
        self.items = items
        self.positions = positions

    def redo(self):
        self.old_positions = []
        for item, pos in zip(self.items, self.positions):
            self.old_positions.append(item.pos())
            orig_topleft = item.mapToScene(QtCore.QPointF(0, 0))
            rect_topleft = self.scene.itemsBoundingRect(
                items=[item]).topLeft()
            hierarchy.set_scene_pos(item, pos + orig_topleft - rect_topleft)

    def undo(self):
        for item, pos in zip(self.items, self.old_positions):
            item.setPos(pos)


class CropItem(QtGui.QUndoCommand):
    def __init__(self, item, crop):
        super().__init__('Crop item')
        self.item = item
        self.crop = crop

    def redo(self):
        self.old_crop = self.item.crop
        self.item.crop = self.crop

    def undo(self):
        self.item.crop = self.old_crop


class ChangeText(QtGui.QUndoCommand):
    """Change the (HTML) text of a note, and optionally its text
    width."""

    def __init__(self, item, new_text, old_text,
                 new_width=None, old_width=None):
        super().__init__('Change text')
        self.item = item
        self.new_text = new_text
        self.old_text = old_text
        self.new_width = new_width
        self.old_width = old_width

    def _apply(self, text, width):
        if width is None:
            self.item.setHtml(text)
        else:
            self.item.set_text_state(text, width)

    def redo(self):
        self._apply(self.new_text, self.new_width)

    def undo(self):
        self._apply(self.old_text, self.old_width)


class ChangeNoteBackground(QtGui.QUndoCommand):
    """Change the background color of text notes."""

    def __init__(self, items, background):
        super().__init__('Change note background')
        self.items = items
        self.background = background
        self.old = [item.background for item in items]

    def redo(self):
        for item in self.items:
            item.set_background(self.background)

    def undo(self):
        for item, old in zip(self.items, self.old):
            item.set_background(old)


class ChangeOpacity(QtGui.QUndoCommand):
    """Change opacity on images."""

    def __init__(self, items, opacity, ignore_first_redo=False):
        super().__init__('Change Opacity')
        self.ignore_first_redo = ignore_first_redo
        self.items = list(filter(lambda item: item.is_image, items))
        self.opacity = opacity
        self.old_opacities = [item.opacity() for item in items]

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return

        for item in self.items:
            item.setOpacity(self.opacity)

    def undo(self):
        for item, opacity in zip(self.items, self.old_opacities):
            item.setOpacity(opacity)


class ToggleNearestNeighbor(QtGui.QUndoCommand):
    """Toggle pixelated display (no smoothing) on images."""

    def __init__(self, items, value):
        super().__init__('Toggle Pixelated')
        self.items = [item for item in items if item.is_image]
        self.value = value
        self.old_values = [item.nearest_neighbor for item in self.items]

    def redo(self):
        for item in self.items:
            item.nearest_neighbor = self.value
            item.update()

    def undo(self):
        for item, value in zip(self.items, self.old_values):
            item.nearest_neighbor = value
            item.update()


class ToggleGrayscale(QtGui.QUndoCommand):
    """Toggle grayscale mode on images."""

    def __init__(self, items, grayscale):
        super().__init__('Toggle Grayscale')
        self.items = list(filter(lambda item: item.is_image, items))
        self.grayscale = grayscale
        self.old_grayscales = [item.grayscale for item in items]

    def redo(self):
        for item in self.items:
            item.grayscale = self.grayscale

    def undo(self):
        for item, grayscale in zip(self.items, self.old_grayscales):
            item.grayscale = grayscale


class ChangeHierarchy(QtGui.QUndoCommand):
    """Change parents and/or the order of items in the hierarchy.

    Items keep their appearance in the scene when changing parents.
    Groups that end up empty are deleted.

    :param changes: List of (item, new parent, new sort order)
    """

    def __init__(self, scene, changes, text='Change hierarchy'):
        super().__init__(text)
        self.scene = scene
        self.changes = changes
        self.old = [(item, item.parentItem(),
                     getattr(item, 'sort_order', None))
                    for item, _, _ in changes]
        self.removed_groups = []

    def apply(self, values):
        for item, parent, sort_order in values:
            hierarchy.set_parent_keep_transform(item, parent)
            item.sort_order = sort_order

    def redo(self):
        self.apply(self.changes)
        self.removed_groups = remove_empty_groups(
            self.scene, [p for _, p, _ in self.old if p is not None])
        fit_groups(self.scene)

    def undo(self):
        restore_groups(self.scene, self.removed_groups)
        self.apply(reversed(self.old))
        fit_groups(self.scene)


class GroupItems(QtGui.QUndoCommand):
    """Put items into a new group.

    The group gets the parent of the first item and covers the area of
    all items.
    """

    def __init__(self, scene, items, group):
        super().__init__('Group items')
        self.scene = scene
        self.items = hierarchy.top_most(items)
        self.group = group
        self.old = [(item, item.parentItem(),
                     getattr(item, 'sort_order', None))
                    for item in self.items]
        self.parent = self.items[0].parentItem() if self.items else None
        orders = [o for _, _, o in self.old if o is not None]
        self.group.sort_order = min(orders) if orders else None
        if getattr(self.group, 'added_at', None) is None:
            self.group.added_at = time.time()

    def redo(self):
        self.scene.deselect_all_items()
        rect = self.scene.itemsBoundingRect(items=self.items)
        add_to_parent(self.scene, self.group, self.parent)
        hierarchy.set_scene_pos(self.group, rect.topLeft())
        self.group.setZValue(max(item.zValue() for item in self.items))
        for item, _, _ in self.old:
            hierarchy.set_parent_keep_transform(item, self.group)
        self.group.fit_to_children()
        fit_groups(self.scene)
        self.group.setSelected(True)

    def undo(self):
        self.scene.deselect_all_items()
        for item, parent, sort_order in self.old:
            hierarchy.set_parent_keep_transform(item, parent)
            item.sort_order = sort_order
        self.scene.removeItem(self.group)
        fit_groups(self.scene)
        for item in self.items:
            item.setSelected(True)


class UngroupItems(QtGui.QUndoCommand):
    """Dissolve groups; their children go to the groups' parents."""

    def __init__(self, scene, groups):
        super().__init__('Ungroup items')
        self.scene = scene
        self.groups = [g for g in groups if is_group(g)]
        self.data = [(group, group.parentItem(),
                      hierarchy.user_children(group))
                     for group in self.groups]

    def redo(self):
        self.scene.deselect_all_items()
        for group, parent, children in self.data:
            for child in children:
                hierarchy.set_parent_keep_transform(child, parent)
            self.scene.removeItem(group)
        fit_groups(self.scene)
        for _, _, children in self.data:
            for child in children:
                child.setSelected(True)

    def undo(self):
        self.scene.deselect_all_items()
        for group, parent, children in reversed(self.data):
            add_to_parent(self.scene, group, parent)
            for child in children:
                hierarchy.set_parent_keep_transform(child, group)
            group.fit_to_children()
        fit_groups(self.scene)
        for group in self.groups:
            group.setSelected(True)


class SetItemsLocked(QtGui.QUndoCommand):
    """Lock or unlock single items (not the whole scene)."""

    def __init__(self, items, locked):
        super().__init__('Lock items' if locked else 'Unlock items')
        self.items = items
        self.locked = locked
        self.old = [item.locked for item in items]

    def redo(self):
        for item in self.items:
            item.set_item_locked(self.locked)

    def undo(self):
        for item, locked in zip(self.items, self.old):
            item.set_item_locked(locked)


class ChangeComment(QtGui.QUndoCommand):

    def __init__(self, items, comment):
        super().__init__('Change comment')
        self.items = items
        self.comment = comment
        self.old = [item.comment for item in items]

    def redo(self):
        for item in self.items:
            item.set_comment(self.comment)

    def undo(self):
        for item, comment in zip(self.items, self.old):
            item.set_comment(comment)


class RenameItem(QtGui.QUndoCommand):

    def __init__(self, item, name):
        super().__init__('Rename item')
        self.item = item
        self.name = name
        self.old = item.name

    def redo(self):
        self.item.name = self.name

    def undo(self):
        self.item.name = self.old


class ChangeGroupColor(QtGui.QUndoCommand):

    def __init__(self, groups, color):
        super().__init__('Change group color')
        self.groups = [g for g in groups if is_group(g)]
        self.color = color
        self.old = [g.color for g in self.groups]

    def redo(self):
        for group in self.groups:
            group.color = self.color
            group.update()

    def undo(self):
        for group, color in zip(self.groups, self.old):
            group.color = color
            group.update()
