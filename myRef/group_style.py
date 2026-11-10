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

"""The look of groups: border, title and opacity.

Sizes (border width, title size) are in scene units, so they scale
with the zoom like images do and get exported as they are shown.
"""

import math

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt


#: Dash patterns in units of the pen width; None is a solid line
BORDER_STYLES = {
    'solid': None,
    'dash': [4, 2],
    'dot': [1, 2],
    'dash_dot': [4, 2, 1, 2],
    'dash_dot_dot': [4, 2, 1, 2, 1, 2],
}

#: Shapes of the border line; the profile of one period of the wave
#: as (t, f) points, t from 0 to 1 along the side, f from 0 (on the
#: group's edge) to 1 (``amplitude`` inside the group). ``None`` is a
#: straight line.
BORDER_SHAPES = {
    'straight': None,
    'zigzag': [(0, 0), (0.5, 1), (1, 0)],
    'wave': [(i / 16, (1 - math.cos(2 * math.pi * i / 16)) / 2)
             for i in range(17)],
    'scallop': [(i / 16, math.sqrt(max(0, 1 - (2 * i / 16 - 1) ** 2)))
                for i in range(17)],
    'battlement': [(0, 0), (0.25, 0), (0.25, 1), (0.75, 1), (0.75, 0),
                   (1, 0)],
}

DEFAULTS = {
    'border_color': '#ff969696',
    'border_width': 2.0,
    'border_style': 'solid',
    'border_shape': 'straight',
    'border_amplitude': 8.0,
    'border_wavelength': 30.0,
    'title_color': '#ffc8c8c8',
    'title_size': 14.0,
}

STYLE_KEYS = tuple(DEFAULTS)

MAX_BORDER_WIDTH = 100
MAX_TITLE_SIZE = 500
MAX_AMPLITUDE = 200
MIN_WAVELENGTH = 4
MAX_WAVELENGTH = 1000


def default_style():
    return dict(DEFAULTS)


def _color(value):
    if isinstance(value, str) and QtGui.QColor(value).isValid():
        return value
    return None


def _number(value, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value:  # NaN
        return None
    return float(min(max(value, 0), maximum))


def clean_value(key, value):
    """The value if it's valid for the given style key, else the
    default."""

    if key in ('border_color', 'title_color'):
        result = _color(value)
    elif key == 'border_width':
        result = _number(value, MAX_BORDER_WIDTH)
    elif key == 'title_size':
        result = _number(value, MAX_TITLE_SIZE)
    elif key == 'border_style':
        result = value if value in BORDER_STYLES else None
    elif key == 'border_shape':
        result = value if value in BORDER_SHAPES else None
    elif key == 'border_amplitude':
        result = _number(value, MAX_AMPLITUDE)
    elif key == 'border_wavelength':
        result = _number(value, MAX_WAVELENGTH)
        if result is not None:
            result = max(result, MIN_WAVELENGTH)
    else:
        raise KeyError(key)
    return DEFAULTS[key] if result is None else result


def from_data(data):
    """The style from a group's saved data; invalid or missing values
    fall back to the defaults."""

    data = data or {}
    return {key: clean_value(key, data[key]) if key in data
            else DEFAULTS[key]
            for key in STYLE_KEYS}


def to_data(style):
    """The values of the style that differ from the defaults."""

    return {key: value for key, value in style.items()
            if key in DEFAULTS and value != DEFAULTS[key]}


def clean_opacity(value):
    result = _number(value, 1)
    return 1.0 if result is None else result


def is_wavy(style):
    return BORDER_SHAPES[style['border_shape']] is not None


def border_inset(style):
    """How far the border reaches into the group: its width plus the
    amplitude of the wave."""

    inset = style['border_width']
    if is_wavy(style) and inset > 0:
        inset += style['border_amplitude']
    return inset


def periods(length, wavelength):
    """The number of whole periods on a side, so that the waves end
    exactly in the corners."""

    return max(1, round(length / wavelength))


def side_points(start, end, inward, profile, amplitude, wavelength):
    """The points of the wave along one side, from start (incl.) to
    end (excl.)."""

    side = end - start
    length = math.hypot(side.x(), side.y())
    count = periods(length, wavelength)
    points = []
    for i in range(count):
        for t, f in profile[:-1]:
            pos = start + side * ((i + t) / count)
            points.append(pos + inward * (f * amplitude))
    return points


def border_path(rect, shape, amplitude, wavelength):
    """The closed outline of the border.

    The line runs along ``rect`` (the middle of the border line) and
    the wave swings inwards from there, so it never leaves the rect.
    Each side has a whole number of periods; the line passes through
    all four corners.
    """

    path = QtGui.QPainterPath()
    profile = BORDER_SHAPES[shape]
    if profile is None or amplitude <= 0:
        path.addRect(rect)
        return path
    # Keep the waves of opposite sides from crossing
    amplitude = min(amplitude, rect.width() / 2, rect.height() / 2)
    corners = [rect.topLeft(), rect.topRight(),
               rect.bottomRight(), rect.bottomLeft()]
    inwards = [QtCore.QPointF(0, 1), QtCore.QPointF(-1, 0),
               QtCore.QPointF(0, -1), QtCore.QPointF(1, 0)]
    points = []
    for i, inward in enumerate(inwards):
        points.extend(side_points(corners[i], corners[(i + 1) % 4],
                                  inward, profile, amplitude, wavelength))
    path.addPolygon(QtGui.QPolygonF(points))
    path.closeSubpath()
    return path


def svg_path_data(path):
    """The given path as SVG path data (only straight segments)."""

    parts = []
    for polygon in path.toSubpathPolygons():
        points = [f'{p.x():g} {p.y():g}' for p in polygon]
        if points:
            parts.append('M ' + ' L '.join(points) + ' Z')
    return ' '.join(parts)


def svg_dasharray(style):
    """The dash pattern for SVG (in scene units), or None."""

    pattern = BORDER_STYLES[style['border_style']]
    if not pattern:
        return None
    width = style['border_width']
    return ' '.join(f'{v * width:g}' for v in pattern)


def border_pen(style):
    """The pen for the group's border, or None if there's no border."""

    width = style['border_width']
    if width <= 0:
        return None
    pen = QtGui.QPen(QtGui.QColor(style['border_color']))
    pen.setWidthF(width)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin if is_wavy(style)
                     else Qt.PenJoinStyle.MiterJoin)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    pattern = BORDER_STYLES[style['border_style']]
    if pattern:
        pen.setDashPattern(pattern)
    return pen


def title_font(style):
    """The font for the group's title, or None if there's no title."""

    size = style['title_size']
    if size < 1:
        return None
    font = QtGui.QFont()
    font.setPixelSize(round(size))
    return font
