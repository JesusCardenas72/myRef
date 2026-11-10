"""Tests for wavy group borders and exporting groups (G4)."""

import math

import pytest

from PyQt6 import QtCore, QtGui

from myRef import group_style
from myRef.fileio.export import SceneToPixmapExporter, SceneToSVGExporter
from myRef.widgets.groups import GroupStyleDialog

from .test_groups import make_group, make_image


RECT = QtCore.QRectF(10, 20, 300, 200)
WAVY = [s for s, p in group_style.BORDER_SHAPES.items() if p is not None]


def path_points(path):
    return [p for polygon in path.toSubpathPolygons() for p in polygon]


# group_style

@pytest.mark.parametrize('length,wavelength,expected', [
    (300, 30, 10), (310, 30, 10), (320, 30, 11), (5, 30, 1), (0, 30, 1)])
def test_periods(length, wavelength, expected):
    assert group_style.periods(length, wavelength) == expected


def test_straight_path_is_rect(qapp):
    path = group_style.border_path(RECT, 'straight', 8, 30)
    assert path.boundingRect() == RECT


def test_zero_amplitude_is_rect(qapp):
    path = group_style.border_path(RECT, 'wave', 0, 30)
    assert path.boundingRect() == RECT


@pytest.mark.parametrize('shape', WAVY)
def test_wavy_path_is_closed_and_stays_inside(qapp, shape):
    path = group_style.border_path(RECT, shape, 8, 30)
    polygons = path.toSubpathPolygons()
    assert len(polygons) == 1
    polygon = polygons[0]
    assert polygon.first() == polygon.last()
    bounds = path.boundingRect()
    assert RECT.adjusted(-1e-6, -1e-6, 1e-6, 1e-6).contains(bounds)


@pytest.mark.parametrize('shape', WAVY)
def test_wavy_path_passes_through_corners(qapp, shape):
    points = path_points(group_style.border_path(RECT, shape, 8, 30))
    for corner in (RECT.topLeft(), RECT.topRight(),
                   RECT.bottomRight(), RECT.bottomLeft()):
        assert any(math.hypot(p.x() - corner.x(), p.y() - corner.y())
                   < 1e-6 for p in points), corner


@pytest.mark.parametrize('shape', WAVY)
def test_wavy_path_reaches_amplitude(qapp, shape):
    points = path_points(group_style.border_path(RECT, shape, 8, 30))
    top_side = [p for p in points if p.x() > RECT.left() + 30
                and p.x() < RECT.right() - 30 and p.y() < RECT.center().y()]
    depths = [p.y() - RECT.top() for p in top_side]
    assert max(depths) == pytest.approx(8, abs=0.01)
    assert min(depths) >= -1e-6


def test_amplitude_limited_to_half_the_rect(qapp):
    rect = QtCore.QRectF(0, 0, 100, 10)
    path = group_style.border_path(rect, 'zigzag', 50, 10)
    assert rect.adjusted(-1e-6, -1e-6, 1e-6, 1e-6).contains(
        path.boundingRect())


def test_svg_path_data(qapp):
    path = group_style.border_path(QtCore.QRectF(0, 0, 4, 2), 'straight',
                                   0, 30)
    assert group_style.svg_path_data(path) == \
        'M 0 0 L 4 0 L 4 2 L 0 2 L 0 0 Z'


def test_svg_dasharray():
    style = group_style.default_style()
    assert group_style.svg_dasharray(style) is None
    style.update(border_style='dash', border_width=3)
    assert group_style.svg_dasharray(style) == '12 6'


@pytest.mark.parametrize('key,value,expected', [
    ('border_shape', 'cloud', 'straight'),
    ('border_shape', 'wave', 'wave'),
    ('border_amplitude', -5, 0),
    ('border_amplitude', 10**6, group_style.MAX_AMPLITUDE),
    ('border_wavelength', 1, group_style.MIN_WAVELENGTH),
    ('border_wavelength', 'x', 30),
])
def test_clean_wave_values(key, value, expected):
    assert group_style.clean_value(key, value) == expected


def test_border_inset():
    style = group_style.default_style()
    style.update(border_width=3, border_amplitude=7)
    assert group_style.border_inset(style) == 3
    style['border_shape'] = 'wave'
    assert group_style.border_inset(style) == 10
    style['border_width'] = 0
    assert group_style.border_inset(style) == 0


# Group item

def test_wave_grows_margins(view):
    a = make_image(view)
    group = make_group(view, [a])
    left = group.margins()[0]
    group.set_style(border_shape='zigzag', border_amplitude=12)
    assert group.margins()[0] == left + 12
    assert group.title_rect().top() >= (
        group.bounding_rect_unselected().top() + 12)


def test_border_path_cache(view):
    a = make_image(view)
    group = make_group(view, [a])
    group.set_style(border_shape='wave')
    path = group.border_path()
    assert group.border_path() is path
    group.set_style(border_wavelength=50)
    assert group.border_path() is not path
    path = group.border_path()
    a.moveBy(50, 0)
    view.scene.fit_groups()
    assert group.border_path() is not path


def test_border_path_inside_group_rect(view):
    a = make_image(view)
    group = make_group(view, [a])
    group.set_style(border_shape='scallop', border_width=6,
                    border_amplitude=10)
    rect = group.bounding_rect_unselected()
    pen = group_style.border_pen(group.style)
    stroker = QtGui.QPainterPathStroker(pen)
    outline = stroker.createStroke(group.border_path()).boundingRect()
    # Round joins may reach a bit further at the corners
    assert rect.adjusted(-3, -3, 3, 3).contains(outline)
    child = group.mapRectFromScene(a.sceneBoundingRect())
    inner = group.border_path().boundingRect().adjusted(16, 16, -16, -16)
    assert child.intersected(inner) == child or inner.contains(child)


def test_save_and_load_wave_style(view, tmpfile):
    from myRef.fileio.sql import SQLiteIO
    a = make_image(view)
    group = make_group(view, [a])
    group.set_style(border_shape='battlement', border_amplitude=5,
                    border_wavelength=40)
    SQLiteIO(tmpfile, view.scene, create_new=True).write()
    view.scene.clear()
    SQLiteIO(tmpfile, view.scene, readonly=True).read()
    view.scene.add_queued_items()
    loaded = list(view.scene.items_by_type('group'))[0]
    assert loaded.style['border_shape'] == 'battlement'
    assert loaded.style['border_amplitude'] == 5
    assert loaded.style['border_wavelength'] == 40


def test_paint_wavy_group(view):
    a = make_image(view)
    group = make_group(view, [a])
    for shape in WAVY:
        group.set_style(border_shape=shape, border_style='dash_dot')
        image = QtGui.QImage(300, 300, QtGui.QImage.Format.Format_ARGB32)
        painter = QtGui.QPainter(image)
        view.scene.render(painter)
        painter.end()


def test_png_export_includes_wavy_border(view):
    a = make_image(view)
    group = make_group(view, [a])
    group.set_style(border_shape='battlement', border_width=6,
                    border_amplitude=10, border_wavelength=40,
                    border_color='#ffff0000', title_size=0)
    view.scene.clearSelection()
    exporter = SceneToPixmapExporter(view.scene)
    exporter.size = exporter.default_size
    image = exporter.render_to_image()
    margin = round(exporter.margin)
    red = QtGui.QColor('#ffff0000')
    column = [image.pixelColor(margin + 2, y) for y in range(image.height())]
    assert red in column


# Dialog

def test_dialog_shape_enables_wave_inputs(view):
    a = make_image(view)
    group = make_group(view, [a])
    dialog = GroupStyleDialog(view, [group], view.undo_stack, show=False)
    assert not dialog.amplitude_input.isEnabled()
    dialog.border_shape_input.setCurrentIndex(
        dialog.border_shape_input.findData('wave'))
    assert dialog.amplitude_input.isEnabled()
    assert group.style['border_shape'] == 'wave'
    dialog.amplitude_input.setValue(15)
    dialog.wavelength_input.setValue(45)
    dialog.accept()
    assert group.style['border_amplitude'] == 15
    assert group.style['border_wavelength'] == 45
    view.undo_stack.undo()
    assert group.style['border_shape'] == 'straight'


# SVG export

def svg_of(view):
    view.scene.clearSelection()
    exporter = SceneToSVGExporter(view.scene)
    exporter.size = exporter.default_size
    return exporter.render_to_svg()


def test_svg_export_group(view):
    a = make_image(view)
    group = make_group(view, [a])
    group.name = 'Refs'
    group.set_style(border_style='dash', border_width=4,
                    border_color='#80ff0000', opacity=0.5)
    svg = svg_of(view)
    groups = [e for e in svg if e.tag == 'g']
    assert len(groups) == 1
    element = groups[0]
    assert element.get('opacity') == '0.5'
    tags = [e.tag for e in element]
    assert tags == ['rect', 'path', 'text']
    border = element[1]
    assert border.get('stroke') == '#ff0000'
    assert float(border.get('stroke-opacity')) == pytest.approx(0.5, 0.01)
    assert border.get('stroke-dasharray') == '16 8'
    assert element[2].text == 'Refs'
    # The group comes before its child, so it's drawn below it
    assert list(svg).index(element) < [e.tag for e in svg].index('image')


def test_svg_export_child_includes_group_opacity(view):
    a = make_image(view)
    a.setOpacity(0.5)
    group = make_group(view, [a])
    group.set_style(opacity=0.5)
    image = [e for e in svg_of(view) if e.tag == 'image'][0]
    assert float(image.get('opacity')) == pytest.approx(0.25)


def test_svg_export_wavy_group(view):
    a = make_image(view)
    group = make_group(view, [a])
    group.set_style(border_shape='zigzag', title_size=0)
    element = [e for e in svg_of(view) if e.tag == 'g'][0]
    assert [e.tag for e in element] == ['path', 'path']
    assert element[1].get('stroke-linejoin') == 'round'
    assert element[1].get('d').count('L') > 20


def test_svg_export_group_without_border(view):
    a = make_image(view)
    group = make_group(view, [a])
    group.set_style(border_width=0, title_size=0)
    element = [e for e in svg_of(view) if e.tag == 'g'][0]
    assert [e.tag for e in element] == ['rect']
