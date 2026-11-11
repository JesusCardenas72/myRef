"""Tests for dragging on items with modifiers or held keys (PureRef
controls): rotate, scale, opacity, flip, crop with C, pan/zoom inside
the crop with V/Shift+V, zoom with Z, color with S and coordinates
with D. Also Shift+Click selection and moving the window with the
right mouse button."""

from unittest.mock import MagicMock, patch

from pytest import approx

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from myRef.drag_tools import panned_crop, zoomed_crop
from myRef.items import BeePixmapItem


NO_MOD = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier
LEFT = Qt.MouseButton.LeftButton
RIGHT = Qt.MouseButton.RightButton


def add_image(view, x=0, y=0, width=100, height=100):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(200, 100, 50))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.setPos(x, y)
    return item


def view_pos(view, scene_x, scene_y):
    return QtCore.QPointF(view.mapFromScene(QtCore.QPointF(scene_x, scene_y)))


def mouse_event(pos, button=LEFT, modifiers=NO_MOD):
    event = MagicMock()
    event.button.return_value = button
    event.modifiers.return_value = modifiers
    event.position.return_value = QtCore.QPointF(pos)
    event.pos.return_value = QtCore.QPointF(pos).toPoint()
    return event


def drag(view, start, end, modifiers=NO_MOD, button=LEFT):
    view.mousePressEvent(mouse_event(start, button, modifiers))
    view.mouseMoveEvent(mouse_event(end, button, modifiers))
    view.mouseReleaseEvent(mouse_event(end, button, modifiers))


def hold_key(view, key):
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, key, NO_MOD)
    view.drag_tools_key_press(event)


def release_key(view, key):
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyRelease, key, NO_MOD)
    view.drag_tools_key_release(event)


# Pure helpers

def test_panned_crop_stays_inside_image():
    bounds = QtCore.QRectF(0, 0, 100, 100)
    crop = QtCore.QRectF(10, 10, 50, 50)
    assert panned_crop(crop, QtCore.QPointF(20, 5), bounds) == QtCore.QRectF(
        30, 15, 50, 50)
    assert panned_crop(crop, QtCore.QPointF(100, -100), bounds) == (
        QtCore.QRectF(50, 0, 50, 50))


def test_zoomed_crop_keeps_center_and_aspect():
    bounds = QtCore.QRectF(0, 0, 200, 100)
    crop = QtCore.QRectF(50, 25, 100, 50)
    zoomed = zoomed_crop(crop, 2, bounds)
    assert zoomed == QtCore.QRectF(75, 37.5, 50, 25)
    # Zooming out stops at the image size
    out = zoomed_crop(crop, 0.1, bounds)
    assert out == QtCore.QRectF(0, 0, 200, 100)


# Modifier drags

def test_ctrl_drag_rotates_item(view):
    item = add_image(view)
    start = view_pos(view, 95, 50)
    end = view_pos(view, 50, 95)
    drag(view, start, end, CTRL)
    assert item.rotation() == approx(90, abs=1)
    assert item.isSelected()
    # Rotated around the center
    assert view.scene.itemsBoundingRect(
        items=[item]).center().x() == approx(50, abs=1)
    view.undo_stack.undo()
    assert item.rotation() == approx(0)


def test_ctrl_shift_drag_rotates_in_steps(view, settings):
    item = add_image(view)
    start = view_pos(view, 95, 50)
    end = view_pos(view, 95, 72)  # ~26 degrees
    drag(view, start, end, CTRL | SHIFT)
    assert item.rotation() == approx(45)


def test_ctrl_click_on_empty_canvas_is_not_a_drag(view):
    add_image(view)
    with patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent') as press:
        view.mousePressEvent(
            mouse_event(view_pos(view, 500, 500), LEFT, CTRL))
    press.assert_called_once()
    assert view.item_drag is None


def test_ctrl_alt_drag_scales_items(view):
    item = add_image(view)
    start = view_pos(view, 50, 50)
    end = start + QtCore.QPointF(200, 0)
    drag(view, start, end, CTRL | ALT)
    assert item.scale() == approx(2)
    view.undo_stack.undo()
    assert item.scale() == approx(1)


def test_ctrl_alt_shift_drag_changes_opacity(view):
    item = add_image(view)
    start = view_pos(view, 50, 50)
    end = start - QtCore.QPointF(150, 0)
    drag(view, start, end, CTRL | ALT | SHIFT)
    assert item.opacity() == approx(0.5)
    view.undo_stack.undo()
    assert item.opacity() == approx(1)


def test_opacity_drag_has_a_minimum(view):
    item = add_image(view)
    start = view_pos(view, 50, 50)
    drag(view, start, start - QtCore.QPointF(1000, 0), CTRL | ALT | SHIFT)
    assert item.opacity() == approx(0.05)


def test_alt_shift_drag_flips_in_drag_direction(view):
    item = add_image(view)
    start = view_pos(view, 50, 50)
    drag(view, start, start + QtCore.QPointF(30, 2), ALT | SHIFT)
    assert item.flip() == -1
    assert item.rotation() == approx(0)

    item2 = add_image(view, 300, 0)
    start = view_pos(view, 350, 50)
    drag(view, start, start + QtCore.QPointF(2, 30), ALT | SHIFT)
    assert item2.flip() == -1
    assert item2.rotation() == approx(180)


def test_small_flip_drag_does_nothing(view):
    item = add_image(view)
    start = view_pos(view, 50, 50)
    drag(view, start, start + QtCore.QPointF(3, 3), ALT | SHIFT)
    assert item.flip() == 1


def test_drag_transforms_whole_selection(view):
    a = add_image(view)
    b = add_image(view, 200, 0)
    a.setSelected(True)
    b.setSelected(True)
    start = view_pos(view, 50, 50)
    drag(view, start, start + QtCore.QPointF(200, 0), CTRL | ALT)
    assert a.scale() == approx(2)
    assert b.scale() == approx(2)


def test_drag_on_unselected_item_selects_only_it(view):
    a = add_image(view)
    b = add_image(view, 200, 0)
    b.setSelected(True)
    start = view_pos(view, 50, 50)
    drag(view, start, start + QtCore.QPointF(200, 0), CTRL | ALT)
    assert a.scale() == approx(2)
    assert b.scale() == approx(1)


def test_escape_cancels_drag(view):
    item = add_image(view)
    start = view_pos(view, 50, 50)
    view.mousePressEvent(mouse_event(start, LEFT, CTRL | ALT))
    view.mouseMoveEvent(
        mouse_event(start + QtCore.QPointF(200, 0), LEFT, CTRL | ALT))
    view.cancel_active_modes()
    assert item.scale() == approx(1)
    assert view.item_drag is None


# Held keys

def test_c_drag_crops_selected_images(view):
    item = add_image(view)
    item.setSelected(True)
    hold_key(view, Qt.Key.Key_C)
    drag(view, view_pos(view, 20, 30), view_pos(view, 60, 80))
    release_key(view, Qt.Key.Key_C)
    assert item.crop.left() == approx(20, abs=1)
    assert item.crop.top() == approx(30, abs=1)
    assert item.crop.right() == approx(60, abs=1)
    assert item.crop.bottom() == approx(80, abs=1)
    assert view.scene.rubberband_item.scene() is None
    view.undo_stack.undo()
    assert item.crop == QtCore.QRectF(0, 0, 100, 100)


def test_c_drag_outside_image_does_not_crop(view):
    item = add_image(view)
    item.setSelected(True)
    hold_key(view, Qt.Key.Key_C)
    drag(view, view_pos(view, 200, 200), view_pos(view, 300, 300))
    assert item.crop == QtCore.QRectF(0, 0, 100, 100)


def test_v_drag_pans_image_inside_crop(view):
    item = add_image(view)
    item.crop = QtCore.QRectF(20, 20, 50, 50)
    item.setSelected(True)
    frame = view.scene.itemsBoundingRect(items=[item])
    hold_key(view, Qt.Key.Key_V)
    start = view_pos(view, 40, 40)
    drag(view, start, start + QtCore.QPointF(10, 0))
    # Dragging right shows more of the left part
    assert item.crop == QtCore.QRectF(10, 20, 50, 50)
    # The frame stays in place
    new_frame = view.scene.itemsBoundingRect(items=[item])
    assert new_frame.left() == approx(frame.left())
    assert new_frame.top() == approx(frame.top())
    view.undo_stack.undo()
    assert item.crop == QtCore.QRectF(20, 20, 50, 50)
    assert item.pos() == QtCore.QPointF(0, 0)


def test_shift_v_drag_zooms_inside_crop(view):
    item = add_image(view)
    item.crop = QtCore.QRectF(20, 20, 50, 50)
    item.setSelected(True)
    frame = view.scene.itemsBoundingRect(items=[item])
    hold_key(view, Qt.Key.Key_V)
    start = view_pos(view, 40, 40)
    drag(view, start, start + QtCore.QPointF(200, 0), SHIFT)
    assert item.crop.width() == approx(25)
    assert item.scale() == approx(2)
    new_frame = view.scene.itemsBoundingRect(items=[item])
    assert new_frame.center().x() == approx(frame.center().x())
    assert new_frame.width() == approx(frame.width())


def test_z_drag_zooms_view(view):
    add_image(view)
    hold_key(view, Qt.Key.Key_Z)
    with patch.object(view, 'zoom') as zoom_mock:
        start = view_pos(view, 50, 50)
        drag(view, start, start - QtCore.QPointF(0, 10))
    zoom_mock.assert_called_once()
    assert zoom_mock.call_args[0][0] == 200


def test_s_drag_shows_color(view):
    add_image(view)
    hold_key(view, Qt.Key.Key_S)
    start = view_pos(view, 50, 50)
    view.mousePressEvent(mouse_event(start))
    assert view.cursor_info.isVisibleTo(view.viewport())
    assert '#c86432' in view.cursor_info.text()
    view.mouseReleaseEvent(mouse_event(start))
    assert not view.cursor_info.isVisibleTo(view.viewport())


def test_d_drag_shows_coordinates(view):
    add_image(view)
    hold_key(view, Qt.Key.Key_D)
    pos = view_pos(view, 12, 30)
    view.mousePressEvent(mouse_event(pos))
    scene_pos = view.mapToScene(pos.toPoint())
    assert (f'Pixel: {int(scene_pos.x())}, {int(scene_pos.y())}'
            in view.cursor_info.text())
    assert '100 × 100' in view.cursor_info.text()


def test_held_keys_ignored_while_editing_text(view):
    view.scene.edit_item = MagicMock()
    hold_key(view, Qt.Key.Key_C)
    assert view.held_keys == set()
    view.scene.edit_item = None


def test_autorepeat_release_keeps_key_held(view):
    hold_key(view, Qt.Key.Key_V)
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyRelease, Qt.Key.Key_V,
                            NO_MOD, '', True)
    view.drag_tools_key_release(event)
    assert Qt.Key.Key_V in view.held_keys


# Shift selection

def scene_event(pos, modifiers=NO_MOD, button=LEFT):
    event = MagicMock()
    event.scenePos.return_value = QtCore.QPointF(*pos)
    event.modifiers.return_value = modifiers
    event.button.return_value = button
    return event


SCENE_PRESS = 'PyQt6.QtWidgets.QGraphicsScene.mousePressEvent'
SCENE_MOVE = 'PyQt6.QtWidgets.QGraphicsScene.mouseMoveEvent'
SCENE_RELEASE = 'PyQt6.QtWidgets.QGraphicsScene.mouseReleaseEvent'


@patch(SCENE_PRESS)
@patch(SCENE_RELEASE)
def test_shift_click_adds_to_selection(release_mock, press_mock, view):
    a = add_image(view)
    b = add_image(view, 200, 0)
    a.setSelected(True)
    view.scene.mousePressEvent(scene_event((250, 50), SHIFT))
    view.scene.mouseReleaseEvent(scene_event((250, 50), SHIFT))
    assert a.isSelected()
    assert b.isSelected()


@patch(SCENE_PRESS)
@patch(SCENE_RELEASE)
def test_shift_click_removes_from_selection(release_mock, press_mock, view):
    a = add_image(view)
    b = add_image(view, 200, 0)
    a.setSelected(True)
    b.setSelected(True)
    view.scene.mousePressEvent(scene_event((250, 50), SHIFT))
    view.scene.mouseReleaseEvent(scene_event((250, 50), SHIFT))
    assert a.isSelected()
    assert not b.isSelected()
    # Qt's own handling would select only the clicked item:
    release_mock.assert_not_called()


@patch(SCENE_PRESS)
@patch(SCENE_MOVE)
@patch(SCENE_RELEASE)
def test_shift_rubberband_adds_to_selection(release_mock, move_mock,
                                            press_mock, view):
    a = add_image(view)
    b = add_image(view, 200, 0)
    a.setSelected(True)
    view.scene.mousePressEvent(scene_event((180, -10), SHIFT))
    view.scene.mouseMoveEvent(scene_event((320, 120), SHIFT))
    view.scene.mouseReleaseEvent(scene_event((320, 120), SHIFT))
    assert a.isSelected()
    assert b.isSelected()


@patch(SCENE_PRESS)
@patch(SCENE_MOVE)
@patch(SCENE_RELEASE)
def test_rubberband_without_shift_replaces_selection(release_mock, move_mock,
                                                     press_mock, view):
    a = add_image(view)
    b = add_image(view, 200, 0)
    a.setSelected(True)
    view.scene.mousePressEvent(scene_event((180, -10)))
    view.scene.mouseMoveEvent(scene_event((320, 120)))
    view.scene.mouseReleaseEvent(scene_event((320, 120)))
    assert not a.isSelected()
    assert b.isSelected()


# Moving the window with the right mouse button

def test_right_drag_moves_window(view):
    add_image(view)
    view.main_window.move(100, 100)
    start = QtCore.QPointF(20, 20)
    view.mousePressEvent(mouse_event(start, RIGHT))
    assert view.movewin_active is False
    view.mouseMoveEvent(mouse_event(start + QtCore.QPointF(30, 5), RIGHT))
    assert view.movewin_active is True
    view.mouseReleaseEvent(
        mouse_event(start + QtCore.QPointF(30, 5), RIGHT))
    assert view.movewin_active is False


def test_right_click_opens_context_menu(view, qtbot):
    add_image(view)
    start = QtCore.QPointF(20, 20)
    with patch.object(view, 'on_context_menu') as menu_mock:
        view.mousePressEvent(mouse_event(start, RIGHT))
        view.mouseReleaseEvent(mouse_event(start, RIGHT))
        qtbot.waitUntil(lambda: menu_mock.called)
    assert view.movewin_active is False


def test_right_drag_pans_when_maximized(view):
    add_image(view)
    with patch.object(view, 'window_fills_screen', return_value=True):
        view.mousePressEvent(mouse_event(QtCore.QPointF(20, 20), RIGHT))
    assert view.active_mode == view.PAN_MODE
    assert view.movewin_pending is None
