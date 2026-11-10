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

"""Grid and edge snapping for moving items.

Everything in here works in scene coordinates and has no state, so
that it can be tested without a scene.
"""

from PyQt6 import QtCore


# Minimum distance between two grid lines on screen, in pixels. When
# zoomed out further, the grid gets coarser.
GRID_MIN_SCREEN_SPACING = 12
# Every n-th grid line is drawn a bit brighter
GRID_MAJOR_EVERY = 5


def effective_grid_size(base, scale, min_spacing=GRID_MIN_SCREEN_SPACING):
    """The grid size actually used at the given view scale.

    The grid size doubles until two grid lines are at least
    ``min_spacing`` screen pixels apart, so that the grid never gets
    too dense when zooming out.
    """

    size = float(base)
    if size <= 0 or scale <= 0:
        return size
    while size * scale < min_spacing:
        size *= 2
    return size


def grid_lines(start, end, size):
    """Coordinates of all grid lines between ``start`` and ``end``."""

    if size <= 0:
        return []
    first = int(start // size)
    last = int(end // size) + 1
    return [i * size for i in range(first, last + 1)
            if start <= i * size <= end]


def is_major_line(value, size, every=GRID_MAJOR_EVERY):
    return round(value / size) % every == 0


def snap_to_grid(edges, size):
    """The smallest correction that moves one of the ``edges`` onto a
    grid line, or ``None``."""

    if size <= 0 or not edges:
        return None
    best = None
    for edge in edges:
        diff = round(edge / size) * size - edge
        if best is None or abs(diff) < abs(best):
            best = diff
    return best


def snap_to_edges(edges, targets, threshold):
    """The smallest correction that moves one of the ``edges`` onto one
    of the ``targets`` if it is at most ``threshold`` away.

    :return: ``(correction, target)`` or ``(None, None)``
    """

    best = (None, None)
    for edge in edges:
        for target in targets:
            diff = target - edge
            if abs(diff) <= threshold and (
                    best[0] is None or abs(diff) < abs(best[0])):
                best = (diff, target)
    return best


def x_edges(rect):
    return (rect.left(), rect.center().x(), rect.right())


def y_edges(rect):
    return (rect.top(), rect.center().y(), rect.bottom())


def snap_delta(start_rect, delta, grid_size=None, others=None,
               threshold=0, axes=(True, True)):
    """Correct the move ``delta`` of the items with the bounding rect
    ``start_rect`` so that they snap to the edges of the ``others``
    rects (if they are close enough) or else to the grid.

    :param grid_size: Grid size in scene coordinates, or ``None`` to
        not snap to the grid.
    :param others: Bounding rects of the items to snap to, or ``None``.
    :param threshold: Maximum distance for snapping to other items, in
        scene coordinates.
    :param axes: Which axes may be snapped (x, y).
    :return: The corrected delta and a list of guide lines (QLineF)
        that show the edges the items snapped to.
    """

    rect = start_rect.translated(delta)
    dx = dy = 0
    guides = []
    others = others or []

    for axis, enabled in enumerate(axes):
        if not enabled:
            continue
        edges_func = x_edges if axis == 0 else y_edges
        edges = edges_func(rect)
        targets = [t for other in others for t in edges_func(other)]
        correction, target = snap_to_edges(edges, targets, threshold)
        if correction is not None:
            snapped = [other for other in others
                       if target in edges_func(other)]
            guides.append((axis, target, snapped))
        elif grid_size:
            # Only the outer edges snap to the grid
            correction = snap_to_grid(edges[::2], grid_size)
        if correction:
            if axis == 0:
                dx = correction
            else:
                dy = correction

    new_delta = QtCore.QPointF(delta.x() + dx, delta.y() + dy)
    rect = start_rect.translated(new_delta)
    lines = []
    for axis, target, snapped in guides:
        union = rect
        for other in snapped:
            union = union.united(other)
        if axis == 0:
            lines.append(QtCore.QLineF(
                target, union.top(), target, union.bottom()))
        else:
            lines.append(QtCore.QLineF(
                union.left(), target, union.right(), target))
    return new_delta, lines
