"""Tests for transform additions of phase 1: axis-constrained moving and
scaling/rotating several items around their own centers."""

from unittest.mock import MagicMock, patch

from pytest import approx

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from myRef import commands
from myRef.items import BeePixmapItem


SHIFT = Qt.KeyboardModifier.ShiftModifier
SHIFT_ALT = Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier
NO_MOD = Qt.KeyboardModifier.NoModifier


def make_item(view, x, y, width=100, height=100):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.setPos(x, y)
    item.setSelected(True)
    return item


def mouse_event(pos, modifiers=NO_MOD):
    event = MagicMock()
    event.scenePos.return_value = QtCore.QPointF(*pos)
    event.modifiers.return_value = modifiers
    return event


def center(view, item):
    return view.scene.itemsBoundingRect(items=[item]).center()


# Commands with own-center anchor

def test_local_anchor_none_is_item_center(view):
    item = make_item(view, 0, 0, 100, 50)
    assert commands.local_anchor(item, None) == QtCore.QPointF(50, 25)


def test_local_anchor_maps_from_scene(view):
    item = make_item(view, 10, 20)
    assert commands.local_anchor(item, QtCore.QPointF(15, 25)) \
        == QtCore.QPointF(5, 5)


def test_scale_items_by_own_centers(view):
    item1 = make_item(view, 0, 0)
    item2 = make_item(view, 300, 0)
    centers = [center(view, item1), center(view, item2)]
    cmd = commands.ScaleItemsBy([item1, item2], 2, None)
    cmd.redo()
    assert item1.scale() == 2
    assert center(view, item1) == centers[0]
    assert center(view, item2) == centers[1]
    cmd.undo()
    assert item1.scale() == 1
    assert item1.pos() == QtCore.QPointF(0, 0)
    assert item2.pos() == QtCore.QPointF(300, 0)


def test_rotate_items_by_own_centers(view):
    item1 = make_item(view, 0, 0)
    item2 = make_item(view, 300, 0)
    centers = [center(view, item1), center(view, item2)]
    cmd = commands.RotateItemsBy([item1, item2], 90, None)
    cmd.redo()
    assert item1.rotation() == 90
    assert center(view, item1).x() == approx(centers[0].x())
    assert center(view, item2).x() == approx(centers[1].x())
    cmd.undo()
    assert item1.rotation() == 0
    assert item2.pos().x() == approx(300)


# Interactive multi-selection transforms

def setup_multi_scale(view, item1, item2):
    multi = view.scene.multi_select_item
    view.scene.on_selection_change()
    multi.active_mode = multi.SCALE_MODE
    multi.event_start = QtCore.QPointF(0, 0)
    multi.event_direction = QtCore.QPointF(1, 0)
    multi.event_anchor = QtCore.QPointF(0, 0)
    multi.scale_orig_factor = multi.scale()
    for item in (item1, item2):
        item.scale_orig_factor = item.scale()
        item.scale_orig_pos = item.pos()
    return multi


def test_multi_scale_own_centers_on_release(view):
    item1 = make_item(view, 0, 0)
    item2 = make_item(view, 300, 0)
    centers = [center(view, item1), center(view, item2)]
    multi = setup_multi_scale(view, item1, item2)
    imgsize = (multi.width ** 2 + multi.height ** 2) ** 0.5
    multi.mouseReleaseEvent(mouse_event((imgsize, 0), SHIFT_ALT))

    assert item1.scale() == approx(2)
    assert center(view, item1).x() == approx(centers[0].x())
    assert center(view, item2).x() == approx(centers[1].x())
    cmd = view.undo_stack.command(view.undo_stack.count() - 1)
    assert isinstance(cmd, commands.ScaleItemsBy)
    assert cmd.anchor is None
    view.undo_stack.undo()
    assert item2.pos() == QtCore.QPointF(300, 0)


def test_multi_scale_switch_modifier_mid_drag(view):
    item1 = make_item(view, 0, 0)
    item2 = make_item(view, 300, 0)
    multi = setup_multi_scale(view, item1, item2)
    imgsize = (multi.width ** 2 + multi.height ** 2) ** 0.5
    multi.mouseMoveEvent(mouse_event((imgsize, 0), SHIFT_ALT))
    # Releasing with common anchor must give the same result as scaling
    # around the common anchor from the start:
    multi.mouseReleaseEvent(mouse_event((imgsize, 0), NO_MOD))
    assert item1.pos() == QtCore.QPointF(0, 0)
    assert item2.pos() == QtCore.QPointF(600, 0)


def test_rotate_snap_is_applied_on_release(view, item):
    view.scene.addItem(item)
    item.setSelected(True)
    item.active_mode = item.ROTATE_MODE
    item.rotate_orig_degrees = 0
    item.rotate_start_angle = -3
    item.event_anchor = QtCore.QPointF(10, 20)
    item.event_start = QtCore.QPointF(10, 10)
    item.mouseReleaseEvent(mouse_event((15, 25), SHIFT))
    cmd = view.undo_stack.command(view.undo_stack.count() - 1)
    assert cmd.delta == -45
    assert item.rotation() == 315


# Axis-constrained moving

def test_constrain_move_delta_horizontal(view):
    delta = view.scene.constrain_move_delta(QtCore.QPointF(10, 3), SHIFT)
    assert delta == QtCore.QPointF(10, 0)


def test_constrain_move_delta_vertical(view):
    delta = view.scene.constrain_move_delta(QtCore.QPointF(-2, -8), SHIFT)
    assert delta == QtCore.QPointF(0, -8)


def test_constrain_move_delta_without_shift(view):
    delta = view.scene.constrain_move_delta(QtCore.QPointF(10, 3), NO_MOD)
    assert delta == QtCore.QPointF(10, 3)


def test_scene_move_with_shift_corrects_positions(view):
    item = make_item(view, 0, 0)
    scene = view.scene
    scene.active_mode = scene.MOVE_MODE
    scene.event_start = QtCore.QPointF(50, 50)
    # Simulate Qt having moved the item by the raw delta:
    item.setPos(30, 10)
    event = mouse_event((80, 60), SHIFT)
    with patch('PyQt6.QtWidgets.QGraphicsScene.mouseMoveEvent'):
        scene.mouseMoveEvent(event)
    assert item.pos() == QtCore.QPointF(30, 0)
    assert scene.last_move_delta == QtCore.QPointF(30, 0)


def test_scene_move_release_uses_constrained_delta(view):
    item = make_item(view, 30, 0)
    scene = view.scene
    scene.active_mode = scene.MOVE_MODE
    scene.event_start = QtCore.QPointF(50, 50)
    scene.last_move_delta = QtCore.QPointF(30, 0)
    with patch('PyQt6.QtWidgets.QGraphicsScene.mouseReleaseEvent'):
        scene.mouseReleaseEvent(mouse_event((80, 60), NO_MOD))
    cmd = view.undo_stack.command(view.undo_stack.count() - 1)
    assert isinstance(cmd, commands.MoveItemsBy)
    assert cmd.delta == QtCore.QPointF(30, 0)
    view.undo_stack.undo()
    assert item.pos() == QtCore.QPointF(0, 0)
