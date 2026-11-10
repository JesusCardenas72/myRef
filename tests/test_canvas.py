from unittest.mock import MagicMock, patch

import pytest

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from myRef import commands
from myRef import snapping
from myRef.actions.actions import actions
from myRef.items import BeePixmapItem
from myRef.widgets.settings import (
    CanvasGridSizeWidget,
    CanvasGridStyleWidget,
    CanvasHighlightWidget,
    CanvasMarginWidget,
    CanvasSnapDistanceWidget,
    SettingsDialog,
)


NO_MOD = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
ALT = Qt.KeyboardModifier.AltModifier


def rect(x, y, w=100, h=100):
    return QtCore.QRectF(x, y, w, h)


def make_item(view, x, y, width=100, height=100, selected=True):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.setPos(x, y)
    item.setSelected(selected)
    return item


def mouse_event(pos, modifiers=NO_MOD):
    event = MagicMock()
    event.scenePos.return_value = QtCore.QPointF(*pos)
    event.modifiers.return_value = modifiers
    event.button.return_value = Qt.MouseButton.LeftButton
    return event


def start_move(view, start=(50, 50)):
    scene = view.scene
    scene.active_mode = scene.MOVE_MODE
    scene.event_start = QtCore.QPointF(*start)
    scene.last_move_delta = None
    scene.start_move_snapping()


def move(view, item_start, pos, modifiers=NO_MOD, items=None):
    """Simulate Qt moving the items by the raw delta, then our
    correction."""

    scene = view.scene
    raw = QtCore.QPointF(*pos) - scene.event_start
    for item, start in zip(items, item_start):
        item.setPos(QtCore.QPointF(*start) + raw)
    with patch('PyQt6.QtWidgets.QGraphicsScene.mouseMoveEvent'):
        scene.mouseMoveEvent(mouse_event(pos, modifiers))


def draw_background(view, painter, rect):
    with patch('PyQt6.QtWidgets.QGraphicsView.drawBackground'):
        view.drawBackground(painter, rect)


def draw_foreground(view, painter, rect):
    with patch('PyQt6.QtWidgets.QGraphicsView.drawForeground'):
        view.drawForeground(painter, rect)


# Pure snapping functions

@pytest.mark.parametrize('base,scale,expected', [
    (50, 1, 50),
    (50, 0.5, 50),
    (50, 0.2, 100),
    (50, 0.1, 200),
    (10, 4, 10),
    (0, 1, 0),
])
def test_effective_grid_size(base, scale, expected):
    assert snapping.effective_grid_size(base, scale) == expected


def test_grid_lines():
    assert snapping.grid_lines(-60, 120, 50) == [-50, 0, 50, 100]


def test_grid_lines_includes_borders():
    assert snapping.grid_lines(0, 100, 50) == [0, 50, 100]


def test_grid_lines_invalid_size():
    assert snapping.grid_lines(0, 100, 0) == []


def test_is_major_line():
    assert snapping.is_major_line(250, 50) is True
    assert snapping.is_major_line(-250, 50) is True
    assert snapping.is_major_line(100, 50) is False


def test_snap_to_grid_picks_smallest_correction():
    assert snapping.snap_to_grid((40, 140), 50) == 10
    assert snapping.snap_to_grid((22, 147), 50) == 3


def test_snap_to_grid_no_size():
    assert snapping.snap_to_grid((40,), 0) is None


def test_snap_to_edges_within_threshold():
    assert snapping.snap_to_edges((95, 195), (100, 300), 10) == (5, 100)


def test_snap_to_edges_outside_threshold():
    assert snapping.snap_to_edges((80,), (100,), 10) == (None, None)


def test_snap_delta_to_grid():
    delta, guides = snapping.snap_delta(
        rect(0, 0), QtCore.QPointF(40, 7), grid_size=50)
    assert delta == QtCore.QPointF(50, 0)
    assert guides == []


def test_snap_delta_to_grid_with_right_edge():
    delta, guides = snapping.snap_delta(
        rect(0, 0, 30, 30), QtCore.QPointF(18, 0), grid_size=50)
    # Right edge at 48 is closer to 50 than the left edge at 18 to 0
    assert delta == QtCore.QPointF(20, 0)


def test_snap_delta_to_other_items():
    delta, guides = snapping.snap_delta(
        rect(0, 0), QtCore.QPointF(195, 30), others=[rect(300, 0)],
        threshold=10)
    assert delta == QtCore.QPointF(200, 30)
    assert guides == [QtCore.QLineF(300, 0, 300, 130)]


def test_snap_delta_to_other_items_centers():
    delta, guides = snapping.snap_delta(
        rect(0, 0), QtCore.QPointF(0, 197), others=[rect(300, 200)],
        threshold=10)
    assert delta == QtCore.QPointF(0, 200)
    assert len(guides) == 1
    assert guides[0].y1() == guides[0].y2()


def test_snap_delta_items_have_priority_over_grid():
    delta, guides = snapping.snap_delta(
        rect(0, 0), QtCore.QPointF(193, 0), grid_size=50,
        others=[rect(297, 0)], threshold=10)
    assert delta == QtCore.QPointF(197, 0)


def test_snap_delta_falls_back_to_grid():
    delta, guides = snapping.snap_delta(
        rect(0, 0), QtCore.QPointF(140, 0), grid_size=50,
        others=[rect(400, 1000)], threshold=10)
    assert delta == QtCore.QPointF(150, 0)
    assert guides == []


def test_snap_delta_respects_axes():
    delta, guides = snapping.snap_delta(
        rect(0, 0), QtCore.QPointF(40, 7), grid_size=50,
        axes=(True, False))
    assert delta == QtCore.QPointF(50, 7)


def test_snap_delta_nothing_to_snap_to():
    delta, guides = snapping.snap_delta(rect(0, 0), QtCore.QPointF(3, 4))
    assert delta == QtCore.QPointF(3, 4)
    assert guides == []


# Snapping while moving items

def test_move_snaps_to_grid(view):
    view.snap_to_grid = True
    item = make_item(view, 0, 0)
    start_move(view)
    move(view, [(0, 0)], (90, 57), items=[item])
    assert item.pos() == QtCore.QPointF(50, 0)
    assert view.scene.last_move_delta == QtCore.QPointF(50, 0)


def test_move_snaps_to_grid_off(view):
    view.snap_to_grid = False
    item = make_item(view, 0, 0)
    start_move(view)
    move(view, [(0, 0)], (90, 57), items=[item])
    assert item.pos() == QtCore.QPointF(40, 7)


def test_move_with_alt_does_not_snap(view):
    view.snap_to_grid = True
    item = make_item(view, 0, 0)
    start_move(view)
    move(view, [(0, 0)], (90, 57), ALT, items=[item])
    assert item.pos() == QtCore.QPointF(40, 7)


def test_move_snaps_to_grid_with_shift_stays_on_axis(view):
    view.snap_to_grid = True
    item = make_item(view, 0, 7)
    start_move(view)
    move(view, [(0, 7)], (90, 53), SHIFT, items=[item])
    assert item.pos() == QtCore.QPointF(50, 7)


def test_move_snaps_to_items_and_shows_guides(view):
    view.snap_to_items = True
    other = make_item(view, 300, 0, selected=False)
    item = make_item(view, 0, 0)
    start_move(view)
    assert view.scene.snap_others == [
        view.scene.itemsBoundingRect(items=[other])]
    move(view, [(0, 0)], (245, 80), items=[item])
    assert item.pos() == QtCore.QPointF(200, 30)
    assert view.scene.snap_guides == [QtCore.QLineF(300, 0, 300, 130)]


def test_move_snap_distance_is_in_screen_pixels(view, settings):
    view.snap_to_items = True
    settings.setValue('Canvas/snap_distance', 10)
    view.scale(2, 2)
    make_item(view, 300, 0, selected=False)
    item = make_item(view, 0, 0)
    start_move(view)
    # 8 scene px away = 16 screen px: too far
    move(view, [(0, 0)], (242, 50), items=[item])
    assert item.pos() == QtCore.QPointF(192, 0)
    # 4 scene px away = 8 screen px: snaps
    move(view, [(0, 0)], (246, 50), items=[item])
    assert item.pos() == QtCore.QPointF(200, 0)


def test_move_snap_to_items_ignores_selected_items(view):
    view.snap_to_items = True
    make_item(view, 300, 0)
    make_item(view, 0, 0)
    start_move(view)
    assert view.scene.snap_others == []


def test_release_clears_snapping(view):
    view.snap_to_items = True
    make_item(view, 300, 0, selected=False)
    item = make_item(view, 0, 0)
    start_move(view)
    move(view, [(0, 0)], (245, 80), items=[item])
    with patch('PyQt6.QtWidgets.QGraphicsScene.mouseReleaseEvent'):
        view.scene.mouseReleaseEvent(mouse_event((245, 80)))
    assert view.scene.snap_guides == []
    assert view.scene.move_start_rect is None
    assert view.scene.snap_others == []
    cmd = view.undo_stack.command(view.undo_stack.count() - 1)
    assert isinstance(cmd, commands.MoveItemsBy)
    assert cmd.delta == QtCore.QPointF(200, 30)


def test_mouse_press_on_item_starts_snapping(view):
    item = make_item(view, 0, 0)
    with patch('PyQt6.QtWidgets.QGraphicsScene.mousePressEvent'):
        with patch.object(view.scene, 'itemAt', return_value=item):
            view.scene.mousePressEvent(mouse_event((50, 50)))
    assert view.scene.move_start_rect == view.scene.itemsBoundingRect(
        selection_only=True)


def test_snap_move_delta_without_start_rect(view):
    view.snap_to_grid = True
    view.scene.move_start_rect = None
    delta, guides = view.scene.snap_move_delta(QtCore.QPointF(3, 4), NO_MOD)
    assert delta == QtCore.QPointF(3, 4)


# Grid

def test_grid_actions_set_state(view):
    actions['show_grid'].qaction.setChecked(True)
    assert view.show_grid is True
    actions['snap_to_grid'].qaction.setChecked(True)
    assert view.snap_to_grid is True
    actions['snap_to_items'].qaction.setChecked(True)
    assert view.snap_to_items is True
    actions['show_grid'].qaction.setChecked(False)
    actions['snap_to_grid'].qaction.setChecked(False)
    actions['snap_to_items'].qaction.setChecked(False)
    assert view.show_grid is False
    assert view.snap_to_grid is False
    assert view.snap_to_items is False


def test_grid_actions_are_remembered(view, settings):
    actions['show_grid'].qaction.setChecked(True)
    assert settings.value('Canvas/show_grid', type=bool) is True
    actions['show_grid'].qaction.setChecked(False)
    assert settings.value('Canvas/show_grid', type=bool) is False


def test_grid_size_adapts_to_zoom(view, settings):
    settings.setValue('Canvas/grid_size', 50)
    assert view.grid_size() == 50
    view.scale(0.1, 0.1)
    assert view.grid_size() == 200


@pytest.mark.parametrize('style', ['lines', 'dots'])
def test_draw_grid(view, settings, style):
    settings.setValue('Canvas/grid_style', style)
    view.show_grid = True
    painter = MagicMock()
    draw_background(view, painter, QtCore.QRectF(-60, -60, 200, 120))
    if style == 'lines':
        lines = [line for call in painter.drawLines.call_args_list
                 for line in call[0][0]]
        assert QtCore.QLineF(0, -60, 0, 60) in lines
        assert QtCore.QLineF(-60, 50, 140, 50) in lines
        assert len(lines) == 4 + 3
    else:
        points = [p for call in painter.drawPoints.call_args_list
                  for p in call[0][0]]
        assert QtCore.QPointF(50, 50) in points
        assert len(points) == 4 * 3


def test_draw_background_without_grid(view):
    view.show_grid = False
    painter = MagicMock()
    draw_background(view, painter, QtCore.QRectF(0, 0, 100, 100))
    painter.drawLines.assert_not_called()
    painter.drawPoints.assert_not_called()


def test_grid_renders(view, settings):
    make_item(view, 0, 0)
    view.show_grid = True
    settings.setValue('Canvas/highlight_canvas', True)
    for style in ('lines', 'dots'):
        settings.setValue('Canvas/grid_style', style)
        assert not view.viewport().grab().isNull()


def test_draw_foreground_draws_snap_guides(view):
    view.scene.snap_guides = [QtCore.QLineF(0, 0, 0, 100)]
    painter = MagicMock()
    draw_foreground(view, painter, QtCore.QRectF(0, 0, 100, 100))
    painter.drawLines.assert_called_once_with(view.scene.snap_guides)


def test_draw_foreground_without_guides(view):
    view.scene.snap_guides = []
    painter = MagicMock()
    draw_foreground(view, painter, QtCore.QRectF(0, 0, 100, 100))
    painter.drawLines.assert_not_called()


# Canvas area

def test_canvas_rect_empty_scene(view):
    assert view.canvas_rect() is None


def test_canvas_rect(view, settings):
    settings.setValue('Canvas/margin', 20)
    make_item(view, 0, 0)
    assert view.canvas_rect() == QtCore.QRectF(-20, -20, 140, 140)


def test_draw_background_highlights_canvas(view, settings):
    settings.setValue('Canvas/highlight_canvas', True)
    settings.setValue('Canvas/margin', 0)
    make_item(view, 0, 0)
    painter = MagicMock()
    draw_background(view, painter, QtCore.QRectF(0, 0, 100, 100))
    painter.fillRect.assert_called_once()
    assert painter.fillRect.call_args[0][0] == QtCore.QRectF(0, 0, 100, 100)


def test_draw_background_canvas_not_highlighted(view, settings):
    settings.setValue('Canvas/highlight_canvas', False)
    make_item(view, 0, 0)
    painter = MagicMock()
    draw_background(view, painter, QtCore.QRectF(0, 0, 100, 100))
    painter.fillRect.assert_not_called()


def test_focus_canvas(view, settings):
    settings.setValue('Canvas/margin', 10)
    make_item(view, 0, 0)
    with patch.object(view, 'fit_rect') as fit_mock:
        view.on_action_focus_canvas()
    fit_mock.assert_called_once_with(QtCore.QRectF(-10, -10, 120, 120))


def test_focus_canvas_empty_scene(view):
    with patch.object(view, 'fit_rect') as fit_mock:
        view.on_action_focus_canvas()
    fit_mock.assert_not_called()


def test_optimize_canvas_centers_items_on_origin(view):
    item1 = make_item(view, 10000, 5000)
    item2 = make_item(view, 10200, 5000)
    view.on_action_optimize_canvas()
    assert view.scene.itemsBoundingRect().center() == QtCore.QPointF(0, 0)
    assert item2.pos() - item1.pos() == QtCore.QPointF(200, 0)
    view.undo_stack.undo()
    assert item1.pos() == QtCore.QPointF(10000, 5000)


def test_optimize_canvas_already_centered(view):
    make_item(view, -50, -50)
    count = view.undo_stack.count()
    view.on_action_optimize_canvas()
    assert view.undo_stack.count() == count


def test_optimize_canvas_empty_scene(view):
    view.on_action_optimize_canvas()
    assert view.undo_stack.count() == 0


def test_canvas_actions_need_items(view):
    assert actions['focus_canvas'].qaction.isEnabled() is False
    assert actions['optimize_canvas'].qaction.isEnabled() is False
    make_item(view, 0, 0)
    view.on_scene_changed(None)
    assert actions['focus_canvas'].qaction.isEnabled() is True
    assert actions['optimize_canvas'].qaction.isEnabled() is True


def test_canvas_settings_change_updates_viewport(view, settings):
    with patch.object(view.viewport(), 'update') as update_mock:
        settings.setValue('Canvas/grid_size', 20)
    update_mock.assert_called()


def test_settings_dialog_has_canvas_tab(view):
    dialog = SettingsDialog(view)
    tab = dialog.tabs.widget(6)
    assert dialog.tabs.tabText(6) == '&Canvas'
    for cls in (CanvasGridSizeWidget, CanvasGridStyleWidget,
                CanvasSnapDistanceWidget, CanvasHighlightWidget,
                CanvasMarginWidget):
        assert isinstance(tab.findChild(cls), cls)
    dialog.close()
