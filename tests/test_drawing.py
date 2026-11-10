from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from beeref import commands, drawing
from beeref.actions.actions import actions, CONTEXT_DRAW, CONTEXT_GLOBAL
from beeref.items import BeeDrawingItem, BeeTextItem, item_registry
from beeref.widgets import drawing as draw_widgets


P = QtCore.QPointF
SHIFT = Qt.KeyboardModifier.ShiftModifier


def line(x1, y1, x2, y2, **kwargs):
    return drawing.make_shape('line', [(x1, y1), (x2, y2)], **kwargs)


def stroke(view, points, modifiers=Qt.KeyboardModifier.NoModifier):
    session = view.draw_session
    session.press(points[0], modifiers)
    for point in points[1:]:
        session.move(point, modifiers)
    session.release(points[-1], modifiers)


def reset_tools():
    draw_widgets.tool_settings.update({
        'tool': 'pen', 'color': drawing.DEFAULT_COLOR,
        'width': drawing.DEFAULT_WIDTH, 'style': 'solid'})


# Shapes

def test_make_shape():
    shape = drawing.make_shape('rect', [(1, 2), (3, 4)], color='#ff000000',
                               width=2, style='bogus')
    assert shape == {'type': 'rect', 'points': [[1.0, 2.0], [3.0, 4.0]],
                     'color': '#ff000000', 'width': 2.0, 'style': 'solid'}


def test_is_valid_shape():
    assert drawing.is_valid_shape(line(0, 0, 1, 1))
    assert not drawing.is_valid_shape({'type': 'blob', 'points': [[0, 0]]})
    assert not drawing.is_valid_shape({'type': 'pen', 'points': []})
    assert not drawing.is_valid_shape({'type': 'pen'})
    assert not drawing.is_valid_shape(None)


def test_constrain_line_to_45_degrees():
    end = drawing.constrain('line', P(0, 0), P(10, 1))
    assert end.y() == 0
    end = drawing.constrain('arrow', P(0, 0), P(10, 9))
    assert abs(end.x() - end.y()) < 1e-9


def test_constrain_rect_to_square():
    end = drawing.constrain('rect', P(0, 0), P(10, -4))
    assert end == P(10, -10)
    end = drawing.constrain('ellipse', P(0, 0), P(-3, 8))
    assert end == P(-8, 8)
    assert drawing.constrain('pen', P(0, 0), P(3, 8)) == P(3, 8)


def test_simplify():
    points = [[0, 0], [1, 0.01], [2, 0], [3, 0.02], [4, 0], [4, 5]]
    assert drawing.simplify(points, 0.5) == [[0, 0], [4, 0], [4, 5]]
    assert drawing.simplify([[0, 0], [1, 1]], 1) == [[0, 0], [1, 1]]


def test_shape_paths():
    for typ in drawing.SHAPE_TYPES:
        shape = drawing.make_shape(typ, [(0, 0), (5, 5), (10, 0)])
        assert not drawing.shape_path(shape).isEmpty()
    dot = drawing.make_shape('pen', [(1, 1)])
    assert drawing.shape_path(dot).elementCount() == 2


def test_arrow_has_head():
    arrow = drawing.make_shape('arrow', [(0, 0), (100, 0)])
    plain = drawing.make_shape('line', [(0, 0), (100, 0)])
    assert (drawing.shape_path(arrow).elementCount()
            > drawing.shape_path(plain).elementCount())


def test_shape_hit():
    shape = line(0, 0, 100, 0, width=2)
    assert drawing.shape_hit(shape, P(50, 2), 2)
    assert not drawing.shape_hit(shape, P(50, 20), 2)


def test_shapes_rect():
    rect = drawing.shapes_rect([line(0, 0, 100, 50, width=2)])
    assert rect.contains(QtCore.QRectF(0, 0, 100, 50))
    assert drawing.shapes_rect([]).isNull()


def test_path_to_svg():
    shape = drawing.make_shape('pen', [(0, 0), (5, 5), (10, 0), (15, 5)])
    data = drawing.path_to_svg(drawing.shape_path(shape))
    assert data.startswith('M 0 0')
    assert ' C ' in data
    assert data.endswith('L 15 5')


def test_svg_attributes_styles():
    shape = line(0, 0, 1, 1, color='#80ff0000', width=2, style='dashed')
    attrib = drawing.svg_attributes(shape)
    assert attrib['stroke'] == '#ff0000'
    assert attrib['stroke-dasharray'] == '8 4'
    assert attrib['fill'] == 'none'
    assert float(attrib['stroke-opacity']) < 0.6
    shape['style'] = 'dotted'
    assert drawing.svg_attributes(shape)['stroke-dasharray'] == '2 4'


# Item

def test_drawing_item_in_registry():
    assert item_registry['drawing'] == BeeDrawingItem


def test_drawing_item_save_and_load(qapp):
    item = BeeDrawingItem(shapes=[line(0, 0, 10, 10), {'type': 'x'}])
    assert len(item.shapes) == 1
    data = item.get_extra_save_data()
    loaded = BeeDrawingItem.create_from_data(data=data)
    assert loaded.shapes == item.shapes
    assert loaded.shapes is not item.shapes
    assert BeeDrawingItem.create_from_data(data={}).shapes == []


def test_drawing_item_bounding_rect(qapp):
    item = BeeDrawingItem()
    assert item.bounding_rect_unselected() == QtCore.QRectF(0, 0, 1, 1)
    item.add_shape(line(0, 0, 100, 50))
    assert item.bounding_rect_unselected().width() > 100
    item.update_last_shape(line(0, 0, 10, 5))
    assert len(item.shapes) == 1
    assert item.bounding_rect_unselected().width() < 100


def test_drawing_item_contains_only_strokes(view):
    item = BeeDrawingItem(shapes=[line(0, 0, 100, 0, width=2)])
    view.scene.addItem(item)
    assert item.contains(P(50, 1))
    assert not item.contains(P(50, 40))
    assert not item.shape().contains(P(50, 40))
    assert item.shape().contains(P(50, 0))


def test_drawing_item_contains_when_selected(view):
    item = BeeDrawingItem(shapes=[line(0, 0, 100, 100, width=2)])
    view.scene.addItem(item)
    item.setSelected(True)
    assert item.contains(P(80, 20))


def test_drawing_item_create_copy(qapp):
    item = BeeDrawingItem(shapes=[line(0, 0, 10, 10)])
    item.setPos(5, 6)
    item.setScale(2)
    item.setRotation(30)
    item.do_flip()
    copy = item.create_copy()
    assert copy.shapes == item.shapes
    assert copy.shapes[0] is not item.shapes[0]
    assert copy.pos() == P(5, 6)
    assert copy.scale() == 2
    assert copy.flip() == -1


def test_drawing_item_copy_to_clipboard(qapp):
    item = BeeDrawingItem(shapes=[line(0, 0, 10, 10)])
    clipboard = MagicMock()
    item.copy_to_clipboard(clipboard)
    image = clipboard.setImage.call_args[0][0]
    assert image.width() > 10


def test_drawing_item_paint(qapp):
    item = BeeDrawingItem(shapes=[line(0, 0, 10, 10)])
    image = QtGui.QImage(20, 20, QtGui.QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QtGui.QPainter(image)
    item.paint(painter, MagicMock(), None)
    painter.end()
    assert image.pixelColor(5, 5).alpha() > 0


def test_change_drawing_command(qapp):
    item = BeeDrawingItem(shapes=[line(0, 0, 1, 1)])
    old = list(item.shapes)
    new = old + [line(2, 2, 3, 3)]
    command = commands.ChangeDrawing(item, new, old)
    command.redo()
    assert item.shapes == new
    command.undo()
    assert item.shapes == old


def test_change_drawing_ignore_first_redo(qapp):
    item = BeeDrawingItem(shapes=[line(0, 0, 1, 1)])
    command = commands.ChangeDrawing(item, [], list(item.shapes),
                                     ignore_first_redo=True)
    command.redo()
    assert len(item.shapes) == 1
    command.redo()
    assert item.shapes == []


# Draw mode

def test_enter_and_exit_draw_mode(view):
    reset_tools()
    view.on_action_draw_mode()
    assert view.draw_session is not None
    assert actions.active_context == CONTEXT_DRAW
    assert view.draw_toolbar.isVisibleTo(view)
    view.on_action_draw_mode()
    assert view.draw_session is None
    assert actions.active_context == CONTEXT_GLOBAL
    assert not view.draw_toolbar.isVisibleTo(view)


def test_draw_mode_not_in_locked_scene(view):
    view.scene.set_items_locked(True)
    view.enter_draw_mode()
    assert view.draw_session is None


def test_pen_stroke_creates_drawing_item_with_undo(view):
    reset_tools()
    view.enter_draw_mode()
    stroke(view, [P(0, 0), P(10, 0), P(20, 5), P(30, 0)])
    items = list(view.scene.items_by_type('drawing'))
    assert len(items) == 1
    assert items[0].shapes[0]['type'] == 'pen'
    assert len(items[0].shapes) == 1
    stroke(view, [P(0, 50), P(30, 50)])
    assert len(items[0].shapes) == 2
    view.undo_stack.undo()
    assert len(items[0].shapes) == 1
    view.undo_stack.undo()
    assert list(view.scene.items_by_type('drawing')) == []
    view.undo_stack.redo()
    assert len(list(view.scene.items_by_type('drawing'))) == 1


def test_stroke_after_undoing_item_creates_new_item(view):
    reset_tools()
    view.enter_draw_mode()
    stroke(view, [P(0, 0), P(10, 10)])
    view.undo_stack.undo()
    stroke(view, [P(0, 0), P(10, 10)])
    assert len(list(view.scene.items_by_type('drawing'))) == 1


def test_line_width_in_screen_pixels(view):
    reset_tools()
    view.scale(2, 2)
    view.enter_draw_mode()
    stroke(view, [P(0, 0), P(10, 10)])
    item = list(view.scene.items_by_type('drawing'))[0]
    assert item.scale() == 0.5
    assert abs(item.shapes[0]['width'] * item.screen_scale()
               - drawing.DEFAULT_WIDTH) < 1e-6


def test_draw_rect_with_shift_is_square(view):
    reset_tools()
    view.enter_draw_mode()
    view.on_action_draw_tool_rect()
    stroke(view, [P(0, 0), P(40, 10)], SHIFT)
    item = list(view.scene.items_by_type('drawing'))[0]
    (x1, y1), (x2, y2) = item.shapes[0]['points']
    assert abs(x2 - x1) == abs(y2 - y1)


def test_tool_actions(view):
    reset_tools()
    view.enter_draw_mode()
    for tool in drawing.TOOLS:
        getattr(view, f'on_action_draw_tool_{tool}')()
        assert view.draw_session.tool == tool
        assert view.draw_toolbar.tool_buttons[tool].isChecked()
    reset_tools()


def test_tool_actions_outside_draw_mode_do_nothing(view):
    reset_tools()
    view.on_action_draw_tool_eraser()
    assert draw_widgets.tool_settings['tool'] == 'pen'


def test_tiny_shape_is_dropped(view):
    reset_tools()
    view.enter_draw_mode()
    view.on_action_draw_tool_line()
    stroke(view, [P(0, 0), P(0.1, 0)])
    assert list(view.scene.items_by_type('drawing')) == []
    stroke(view, [P(0, 0), P(50, 0)])
    item = list(view.scene.items_by_type('drawing'))[0]
    stroke(view, [P(0, 20), P(0.1, 20)])
    assert len(item.shapes) == 1
    reset_tools()


def test_tool_settings_apply_to_shapes(view):
    reset_tools()
    draw_widgets.tool_settings.update(
        {'tool': 'arrow', 'color': '#ff00ff00', 'style': 'dotted'})
    view.enter_draw_mode()
    stroke(view, [P(0, 0), P(50, 0)])
    shape = list(view.scene.items_by_type('drawing'))[0].shapes[0]
    assert shape['type'] == 'arrow'
    assert shape['color'] == '#ff00ff00'
    assert shape['style'] == 'dotted'
    reset_tools()


def test_eraser_removes_whole_strokes(view):
    reset_tools()
    view.enter_draw_mode()
    view.on_action_draw_tool_line()
    stroke(view, [P(0, 0), P(100, 0)])
    stroke(view, [P(0, 50), P(100, 50)])
    item = list(view.scene.items_by_type('drawing'))[0]
    view.on_action_draw_tool_eraser()
    stroke(view, [P(50, 30), P(50, 49)])
    assert len(item.shapes) == 1
    assert item.shapes[0]['points'][0][1] == 0
    view.undo_stack.undo()
    assert len(item.shapes) == 2
    reset_tools()


def test_eraser_picks_drawing_under_cursor(view):
    reset_tools()
    item = BeeDrawingItem(shapes=[line(0, 0, 100, 0)])
    view.scene.addItem(item)
    view.enter_draw_mode()
    view.on_action_draw_tool_eraser()
    stroke(view, [P(-50, -50)])
    assert len(item.shapes) == 1
    stroke(view, [P(50, 0)])
    assert item.shapes == []
    view.exit_draw_mode()
    # Empty drawing gets removed
    assert item.scene() is None
    reset_tools()


def test_exit_draw_mode_selects_drawing(view):
    reset_tools()
    view.enter_draw_mode()
    stroke(view, [P(0, 0), P(30, 30)])
    item = view.draw_session.item
    view.exit_draw_mode()
    assert item.isSelected()


def test_draw_mode_continues_selected_drawing(view):
    reset_tools()
    item = BeeDrawingItem(shapes=[line(0, 0, 100, 0)])
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_draw_mode()
    assert view.draw_session.item is item
    stroke(view, [P(0, 30), P(30, 30)])
    assert len(item.shapes) == 2


def test_double_click_drawing_enters_draw_mode(view):
    item = BeeDrawingItem(shapes=[line(0, 0, 100, 0, width=4)])
    view.scene.addItem(item)
    event = MagicMock()
    event.scenePos.return_value = P(50, 0)
    with patch.object(view.scene, 'mousePressEvent') as press_mock:
        view.scene.mouseDoubleClickEvent(event)
    assert view.draw_session.item is item
    press_mock.assert_not_called()


def test_enter_draw_mode_ends_text_editing(view):
    text = BeeTextItem('foo')
    view.scene.addItem(text)
    text.enter_edit_mode()
    view.enter_draw_mode()
    assert view.scene.edit_item is None
    assert actions.active_context == CONTEXT_DRAW


def test_lock_scene_exits_draw_mode(view):
    view.enter_draw_mode()
    view.on_action_lock_items(True)
    assert view.draw_session is None


def test_clear_scene_exits_draw_mode(view):
    view.enter_draw_mode()
    view.clear_scene()
    assert view.draw_session is None
    assert actions.active_context == CONTEXT_GLOBAL


def test_escape_exits_draw_mode(view):
    view.enter_draw_mode()
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                            Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(event)
    assert view.draw_session is None


def test_view_mouse_events_draw(view, qtbot):
    reset_tools()
    view.show()
    view.enter_draw_mode()
    vp = view.viewport()
    qtbot.mousePress(vp, Qt.MouseButton.LeftButton,
                     pos=QtCore.QPoint(10, 10))
    qtbot.mouseMove(vp, QtCore.QPoint(40, 40))
    qtbot.mouseMove(vp, QtCore.QPoint(80, 30))
    qtbot.mouseRelease(vp, Qt.MouseButton.LeftButton,
                       pos=QtCore.QPoint(80, 30))
    items = list(view.scene.items_by_type('drawing'))
    assert len(items) == 1
    assert len(items[0].shapes[0]['points']) >= 2


def test_toolbar_controls_change_tool_settings(view):
    reset_tools()
    view.enter_draw_mode()
    toolbar = view.draw_toolbar
    toolbar.width_box.setValue(9)
    assert draw_widgets.tool_settings['width'] == 9
    toolbar.style_box.setCurrentIndex(toolbar.style_box.findData('dashed'))
    assert draw_widgets.tool_settings['style'] == 'dashed'
    toolbar.tool_buttons['ellipse'].click()
    assert view.draw_session.tool == 'ellipse'
    with patch('PyQt6.QtWidgets.QColorDialog.getColor',
               return_value=QtGui.QColor('blue')):
        toolbar.on_color()
    assert draw_widgets.tool_settings['color'] == '#ff0000ff'
    toolbar.done_button.click()
    assert view.draw_session is None
    reset_tools()


def test_draw_toolbar_retranslate(view):
    view.enter_draw_mode()
    with patch.object(view.draw_toolbar, 'retranslate') as retranslate:
        view.on_language_changed()
    retranslate.assert_called_once_with()


# Export and files

def test_svg_export_contains_paths(view):
    from beeref.fileio.export import SceneToSVGExporter
    item = BeeDrawingItem(shapes=[line(0, 0, 100, 0)])
    view.scene.addItem(item)
    item.setPos(10, 20)
    exporter = SceneToSVGExporter(view.scene)
    exporter.size = QtCore.QSize(100, 100)
    svg = exporter.render_to_svg()
    paths = [e for e in svg.iter() if e.tag == 'path']
    assert len(paths) == 1
    group = [e for e in svg.iter() if e.tag == 'g'][0]
    assert group.get('transform').startswith('matrix(')
    ET.tostring(svg)


def test_save_and_load_drawing(view, tmpfile):
    item = BeeDrawingItem(shapes=[line(0, 0, 100, 0, color='#ff123456')])
    view.scene.addItem(item)
    from beeref.fileio import load_bee, save_bee
    save_bee(tmpfile, view.scene, create_new=True)
    view.scene.clear()
    load_bee(tmpfile, view.scene)
    view.scene.add_queued_items()
    items = list(view.scene.items_by_type('drawing'))
    assert len(items) == 1
    assert items[0].shapes[0]['color'] == '#ff123456'
