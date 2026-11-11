from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

import pytest


def mouse_event(kind, pos, button=Qt.MouseButton.LeftButton):
    return QtGui.QMouseEvent(
        kind, QtCore.QPointF(*pos), QtCore.QPointF(*pos), button,
        button, Qt.KeyboardModifier.NoModifier)


def test_starts_collapsed_in_top_right(view):
    control = view.opacity_control
    assert control.expanded is False
    assert control.height() == control.ICON_SIZE
    area = view.viewport().geometry()
    assert control.x() + control.width() == (
        area.right() + 1 - control.MARGIN)
    assert control.y() == area.top() + control.MARGIN


def test_moves_left_of_lock_icon_in_same_corner(view, settings):
    settings.setValue('LockIcon/corner', 'top_right')
    control = view.opacity_control
    assert control.x() + control.width() < view.lock_button.x()


def test_expand_and_collapse(view):
    control = view.opacity_control
    control.expand()
    assert control.expanded is True
    assert control.height() == control.expanded_height()
    control.collapse()
    assert control.expanded is False
    assert control.height() == control.ICON_SIZE


def test_does_not_collapse_while_dragging(view):
    control = view.opacity_control
    control.expand()
    control.dragging = True
    control.collapse()
    assert control.expanded is True


def test_top_is_full_and_bottom_is_minimum(view):
    control = view.opacity_control
    track = control.track_rect()
    assert control.y_to_percent(track.top()) == 100
    assert control.y_to_percent(track.bottom()) == 5
    assert control.y_to_percent(track.top() - 50) == 100
    assert control.y_to_percent(track.bottom() + 50) == 5
    assert control.percent_to_y(100) == pytest.approx(track.top())
    assert control.percent_to_y(5) == pytest.approx(track.bottom())


def test_drag_previews_and_release_saves(view, settings):
    control = view.opacity_control
    control.expand()
    track = control.track_rect()
    x = control.width() / 2
    middle = track.center().y()
    control.mousePressEvent(
        mouse_event(QtCore.QEvent.Type.MouseButtonPress, (x, middle)))
    assert control.dragging is True
    assert view.parent.windowOpacity() == pytest.approx(0.52, abs=0.02)
    assert settings.valueOrDefault('Window/opacity') == 100

    control.mouseReleaseEvent(
        mouse_event(QtCore.QEvent.Type.MouseButtonRelease,
                    (x, track.bottom())))
    assert control.dragging is False
    assert settings.valueOrDefault('Window/opacity') == 5
    assert view.parent.windowOpacity() == pytest.approx(0.05, abs=0.01)


def test_press_on_icon_does_not_change_opacity(view, settings):
    control = view.opacity_control
    control.expand()
    control.mousePressEvent(
        mouse_event(QtCore.QEvent.Type.MouseButtonPress, (10, 10)))
    assert control.dragging is False
    assert settings.valueOrDefault('Window/opacity') == 100


def test_tooltip_follows_opacity(view):
    view.set_window_opacity(40)
    assert '40' in view.opacity_control.toolTip()


def test_is_visible(view):
    view.parent.show()
    assert view.opacity_control.isVisibleTo(view)


def test_handle_follows_drag_before_saving(view, settings):
    control = view.opacity_control
    control.expand()
    control.set_from_y(control.percent_to_y(60), save=False)
    assert control.percent() == 60
    assert settings.valueOrDefault('Window/opacity') == 100
