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

"""Shapes of drawing items.

A shape is a JSON-friendly dict::

    {'type': 'pen' | 'line' | 'arrow' | 'rect' | 'ellipse',
     'points': [[x, y], ...],  # all points for 'pen', start and end
                               # for the other types
     'color': '#aarrggbb',
     'width': 3.0,
     'style': 'solid' | 'dashed' | 'dotted'}

Coordinates are in the drawing item's coordinate system.
"""

import copy
import math

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt


TOOLS = ('pen', 'line', 'arrow', 'rect', 'ellipse', 'eraser')
SHAPE_TYPES = ('pen', 'line', 'arrow', 'rect', 'ellipse')
STYLES = {
    'solid': Qt.PenStyle.SolidLine,
    'dashed': Qt.PenStyle.DashLine,
    'dotted': Qt.PenStyle.DotLine,
}
DEFAULT_COLOR = '#ffff3b30'
DEFAULT_WIDTH = 4.0


def make_shape(typ, points, color=DEFAULT_COLOR, width=DEFAULT_WIDTH,
               style='solid'):
    return {'type': typ,
            'points': [[float(x), float(y)] for x, y in points],
            'color': color,
            'width': float(width),
            'style': style if style in STYLES else 'solid'}


def copy_shapes(shapes):
    return copy.deepcopy(shapes)


def is_valid_shape(shape):
    try:
        return (shape['type'] in SHAPE_TYPES
                and len(shape['points']) >= 1
                and all(len(p) == 2 for p in shape['points']))
    except (KeyError, TypeError):
        return False


def qpoints(shape):
    return [QtCore.QPointF(x, y) for x, y in shape['points']]


# Constraining (Shift)

def constrain(typ, start, end):
    """Constrain lines to multiples of 45 degrees and rectangles and
    ellipses to squares and circles."""

    delta = end - start
    if typ in ('line', 'arrow'):
        length = math.hypot(delta.x(), delta.y())
        angle = math.atan2(delta.y(), delta.x())
        angle = round(angle / (math.pi / 4)) * (math.pi / 4)
        return start + QtCore.QPointF(length * math.cos(angle),
                                      length * math.sin(angle))
    if typ in ('rect', 'ellipse'):
        size = max(abs(delta.x()), abs(delta.y()))
        return start + QtCore.QPointF(math.copysign(size, delta.x() or 1),
                                      math.copysign(size, delta.y() or 1))
    return end


# Smoothing

def _point_line_distance(p, a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    return abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / (
        math.hypot(dx, dy))


def simplify(points, epsilon):
    """Ramer-Douglas-Peucker simplification of a list of [x, y]."""

    if len(points) < 3:
        return [list(p) for p in points]
    # Iterative to avoid deep recursion for long strokes
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        max_dist = 0
        index = None
        for i in range(first + 1, last):
            dist = _point_line_distance(points[i], points[first],
                                        points[last])
            if dist > max_dist:
                max_dist = dist
                index = i
        if index is not None and max_dist > epsilon:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [list(p) for p, k in zip(points, keep) if k]


# Painting

def arrow_head(start, end, width):
    """The two end points of the arrow head's lines."""

    angle = math.atan2(end.y() - start.y(), end.x() - start.x())
    length = max(10.0, width * 4)
    spread = math.pi / 7
    return [end - QtCore.QPointF(length * math.cos(angle - spread),
                                 length * math.sin(angle - spread)),
            end - QtCore.QPointF(length * math.cos(angle + spread),
                                 length * math.sin(angle + spread))]


def shape_path(shape):
    """The shape's outline as QPainterPath (to be stroked)."""

    path = QtGui.QPainterPath()
    points = qpoints(shape)
    if not points:
        return path
    typ = shape['type']
    if typ == 'pen':
        path.moveTo(points[0])
        if len(points) == 1:
            # A dot; Qt drops zero-length segments
            path.lineTo(points[0] + QtCore.QPointF(0.01, 0))
        elif len(points) == 2:
            path.lineTo(points[1])
        else:
            # Quadratic curves through the midpoints for smooth strokes
            for i in range(1, len(points) - 1):
                mid = (points[i] + points[i + 1]) / 2
                path.quadTo(points[i], mid)
            path.lineTo(points[-1])
        return path
    start = points[0]
    end = points[-1]
    if typ in ('line', 'arrow'):
        path.moveTo(start)
        path.lineTo(end)
        if typ == 'arrow' and start != end:
            for point in arrow_head(start, end, shape.get('width', 1)):
                path.moveTo(end)
                path.lineTo(point)
    elif typ == 'rect':
        path.addRect(QtCore.QRectF(start, end).normalized())
    elif typ == 'ellipse':
        path.addEllipse(QtCore.QRectF(start, end).normalized())
    return path


def shape_pen(shape):
    pen = QtGui.QPen(QtGui.QColor(shape.get('color', DEFAULT_COLOR)))
    pen.setWidthF(max(0.1, float(shape.get('width', DEFAULT_WIDTH))))
    pen.setStyle(STYLES.get(shape.get('style'), Qt.PenStyle.SolidLine))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def paint_shape(painter, shape):
    painter.setPen(shape_pen(shape))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(shape_path(shape))


def stroked_path(shape, extra=0):
    """The area covered by the painted shape, plus ``extra``."""

    stroker = QtGui.QPainterPathStroker()
    stroker.setWidth(float(shape.get('width', DEFAULT_WIDTH)) + extra)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return stroker.createStroke(shape_path(shape))


def shapes_rect(shapes):
    """Bounding rect of all shapes including their line widths."""

    rect = QtCore.QRectF()
    for shape in shapes:
        width = float(shape.get('width', DEFAULT_WIDTH))
        if shape['type'] == 'arrow':
            width *= 5
        shape_rect = shape_path(shape).boundingRect().adjusted(
            -width, -width, width, width)
        rect = rect.united(shape_rect)
    return rect


def shape_hit(shape, pos, radius):
    """Whether the painted shape is within ``radius`` of ``pos``."""

    area = QtGui.QPainterPath()
    area.addEllipse(pos, radius, radius)
    return stroked_path(shape).intersects(area)


# SVG

def path_to_svg(path):
    """Convert a QPainterPath to SVG path data."""

    def fmt(value):
        return f'{round(value, 3):g}'

    parts = []
    i = 0
    count = path.elementCount()
    ElementType = QtGui.QPainterPath.ElementType
    while i < count:
        element = path.elementAt(i)
        if element.type == ElementType.MoveToElement:
            parts.append(f'M {fmt(element.x)} {fmt(element.y)}')
            i += 1
        elif element.type == ElementType.LineToElement:
            parts.append(f'L {fmt(element.x)} {fmt(element.y)}')
            i += 1
        elif element.type == ElementType.CurveToElement:
            c1 = element
            c2 = path.elementAt(i + 1)
            end = path.elementAt(i + 2)
            parts.append(
                f'C {fmt(c1.x)} {fmt(c1.y)} {fmt(c2.x)} {fmt(c2.y)} '
                f'{fmt(end.x)} {fmt(end.y)}')
            i += 3
        else:
            i += 1
    return ' '.join(parts)


def svg_attributes(shape):
    color = QtGui.QColor(shape.get('color', DEFAULT_COLOR))
    attrib = {
        'd': path_to_svg(shape_path(shape)),
        'fill': 'none',
        'stroke': color.name(QtGui.QColor.NameFormat.HexRgb),
        'stroke-opacity': f'{color.alphaF():g}',
        'stroke-width': f'{float(shape.get("width", DEFAULT_WIDTH)):g}',
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
    }
    width = float(shape.get('width', DEFAULT_WIDTH))
    if shape.get('style') == 'dashed':
        attrib['stroke-dasharray'] = f'{width * 4:g} {width * 2:g}'
    elif shape.get('style') == 'dotted':
        attrib['stroke-dasharray'] = f'{width:g} {width * 2:g}'
    return attrib
