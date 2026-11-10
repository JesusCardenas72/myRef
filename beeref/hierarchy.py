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

"""Helpers for parent-child relations between items.

Positions, scales and rotations of child items are relative to their
parent. These helpers take care of mapping between scene and parent
coordinates.
"""

import math

from PyQt6 import QtCore, QtGui


def is_user_item(item):
    """Items added by the user (as opposed to selection outlines etc.)"""
    return hasattr(item, 'save_id')


def user_children(item):
    """The direct children of the given item that were added by the user."""
    return [child for child in item.childItems() if is_user_item(child)]


def descendants(item):
    """All user items below the given item in the hierarchy."""
    result = []
    for child in user_children(item):
        result.append(child)
        result.extend(descendants(child))
    return result


def ancestors(item):
    """The parent, grandparent etc. of the given item."""
    result = []
    parent = item.parentItem()
    while parent is not None:
        result.append(parent)
        parent = parent.parentItem()
    return result


def top_most(items):
    """The given items without the items whose ancestors are given, too.

    Transforming an item transforms its children, so when parents and
    children are selected, only the parents need to be transformed.
    """
    items = list(items)
    item_set = set(items)
    return [item for item in items
            if not any(a in item_set for a in ancestors(item))]


def decompose_transform(transform):
    """Split a transform into the values BeeRef items use.

    :returns: (position, scale, rotation, flip) with flip being 1 or -1
    """
    det = (transform.m11() * transform.m22()
           - transform.m12() * transform.m21())
    flip = -1 if det < 0 else 1
    scale = math.sqrt(abs(det)) or 1
    # Qt applies the flip (the item's transform()) after scale and
    # rotation, i.e. matrix = scale * rotation * flip
    rotation = math.degrees(math.atan2(
        transform.m12() / scale, flip * transform.m11() / scale))
    return (QtCore.QPointF(transform.dx(), transform.dy()),
            scale, rotation % 360, flip)


def set_local_transform(item, transform):
    """Set position, scale, rotation and flip of the item according to
    the given transform (in parent coordinates)."""
    pos, scale, rotation, flip = decompose_transform(transform)
    item.setTransform(QtGui.QTransform.fromScale(flip, 1))
    item.setScale(scale)
    item.setRotation(rotation)
    item.setPos(pos)


def set_parent_keep_transform(item, parent):
    """Give the item a new parent (or none) without changing how it
    looks in the scene."""
    if item.parentItem() is parent:
        return
    scene_transform = item.sceneTransform()
    item.setParentItem(parent)
    if parent is not None:
        inverted, ok = parent.sceneTransform().inverted()
        transform = scene_transform * inverted
    else:
        transform = scene_transform
    set_local_transform(item, transform)


def scene_delta_to_parent(item, delta):
    """Map a movement in scene coordinates to the item's parent
    coordinates, for use with ``setPos`` and ``moveBy``."""
    parent = item.parentItem()
    if parent is None:
        return QtCore.QPointF(delta)
    return parent.mapFromScene(delta) - parent.mapFromScene(
        QtCore.QPointF(0, 0))


def set_scene_pos(item, pos):
    """Set the item's position given in scene coordinates."""
    parent = item.parentItem()
    if parent is None:
        item.setPos(pos)
    else:
        item.setPos(parent.mapFromScene(pos))
