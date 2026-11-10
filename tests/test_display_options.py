"""Tests for grayscale canvas and pixelated (nearest neighbor) display."""

from unittest.mock import MagicMock

from PyQt6 import QtGui

from myRef import commands
from myRef.items import BeePixmapItem, BeeTextItem


def make_image(view, selected=True):
    img = QtGui.QImage(10, 10, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(255, 0, 0))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.setSelected(selected)
    return item


def test_grayscale_canvas_affects_display_not_item(view):
    item = make_image(view)
    assert item.displays_grayscale is False
    view.on_action_grayscale_canvas(True)
    assert item.displays_grayscale is True
    assert item.grayscale is False
    assert item.get_extra_save_data()['grayscale'] is False
    view.on_action_grayscale_canvas(False)
    assert item.displays_grayscale is False


def test_grayscale_canvas_sample_color_is_gray(view):
    item = make_image(view)
    view.scene.set_grayscale_canvas(True)
    color = item.sample_color_at(item.mapToScene(5, 5))
    assert color.red() == color.green() == color.blue()


def test_grayscale_pixmap_is_cached_and_reset_on_new_pixmap(view):
    item = make_image(view)
    pm = item.get_grayscale_pixmap()
    assert item.get_grayscale_pixmap() is pm
    item.setPixmap(QtGui.QPixmap(5, 5))
    assert item.get_grayscale_pixmap() is not pm


def test_grayscale_setter_false_frees_cache(view):
    item = make_image(view)
    item.grayscale = True
    assert item._grayscale_pixmap is not None
    item.grayscale = False
    assert item._grayscale_pixmap is None


def test_nearest_neighbor_default_off(view):
    item = make_image(view)
    assert item.nearest_neighbor is False
    assert 'nearest_neighbor' not in item.get_extra_save_data()


def test_nearest_neighbor_saved_and_loaded(view):
    item = make_image(view)
    item.nearest_neighbor = True
    data = item.get_extra_save_data()
    assert data['nearest_neighbor'] is True
    new = BeePixmapItem.create_from_data(
        item=BeePixmapItem(QtGui.QImage()), data=data)
    assert new.nearest_neighbor is True


def test_nearest_neighbor_copied(view):
    item = make_image(view)
    item.nearest_neighbor = True
    assert item.create_copy().nearest_neighbor is True


def test_toggle_nearest_neighbor_command(view):
    item = make_image(view)
    text = BeeTextItem('foo')
    view.scene.addItem(text)
    cmd = commands.ToggleNearestNeighbor([item, text], True)
    cmd.redo()
    assert item.nearest_neighbor is True
    cmd.undo()
    assert item.nearest_neighbor is False


def test_action_nearest_neighbor_pushes_command(view):
    item = make_image(view)
    view.on_action_nearest_neighbor(True)
    assert item.nearest_neighbor is True
    view.undo_stack.undo()
    assert item.nearest_neighbor is False


def test_action_nearest_neighbor_noop_when_unchanged(view):
    make_image(view)
    view.on_action_nearest_neighbor(False)
    assert view.undo_stack.count() == 0


def paint_render_hints(item):
    painter = MagicMock()
    painter.combinedTransform.return_value.m11.return_value = 1
    item.paint(painter, MagicMock(), None)
    return painter.setRenderHint.call_args_list


def test_paint_smooth_by_default(view):
    item = make_image(view, selected=False)
    assert paint_render_hints(item)


def test_paint_not_smooth_when_nearest_neighbor(view):
    item = make_image(view, selected=False)
    item.nearest_neighbor = True
    assert not paint_render_hints(item)


def test_selection_change_updates_nearest_neighbor_check(view):
    from myRef.actions.actions import actions
    item = make_image(view, selected=False)
    item.nearest_neighbor = True
    item.setSelected(True)
    view.on_selection_changed()
    assert actions['nearest_neighbor'].qaction.isChecked() is True
