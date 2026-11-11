"""Tests for the window modes added in phase 2."""

from unittest.mock import MagicMock, patch

import pytest

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef import window
from myRef.items import BeePixmapItem
from myRef.widgets.settings import SettingsDialog, WindowOpacityWidget
from myRef.window import (
    keysequence_to_native,
    NativeEventFilter,
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
)


@pytest.fixture
def no_recreate(view):
    """Don't recreate the native window (slow and flaky in tests)."""
    with patch.object(view, 'recreate_window') as recreate_mock:
        yield recreate_mock


@pytest.fixture
def no_native_click_through():
    with patch('myRef.window.set_click_through') as click_mock:
        yield click_mock


def make_image(view, w=200, h=150, selected=True):
    img = QtGui.QImage(w, h, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(255, 0, 0))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.setSelected(selected)
    return item


# Global shortcuts

@pytest.mark.parametrize('shortcut,expected', [
    ('Ctrl+Alt+T', (MOD_CONTROL | MOD_ALT, 0x54)),
    ('F5', (0, 0x74)),
    ('Ctrl+Alt+Up', (MOD_CONTROL | MOD_ALT, 0x26)),
    ('Shift+5', (MOD_SHIFT, 0x35)),
    ('Ctrl+PgDown', (MOD_CONTROL, 0x22)),
    ('Ctrl+K, Ctrl+L', None),
    ('', None),
])
def test_keysequence_to_native(shortcut, expected):
    assert keysequence_to_native(shortcut) == expected


@patch('myRef.window.NativeEventFilter.install')
@patch('myRef.window.NativeEventFilter.is_supported', return_value=True)
def test_native_filter_registers_hotkeys(supported_mock, install_mock):
    callback = MagicMock()
    hotkeys = NativeEventFilter(callback)
    with patch.object(hotkeys, '_register_native',
                      side_effect=[True, False]) as reg_mock:
        failed = hotkeys.register({'foo': ['Ctrl+Alt+T', 'Ctrl+Alt+Y'],
                                   'bar': ['Ctrl+K, Ctrl+L']})
    assert failed == ['Ctrl+Alt+Y', 'Ctrl+K, Ctrl+L']
    reg_mock.assert_any_call(1, MOD_CONTROL | MOD_ALT, 0x54)
    assert hotkeys.registered == {1: 'foo'}
    install_mock.assert_called_once()


@patch('myRef.window.NativeEventFilter.install')
@patch('myRef.window.NativeEventFilter.is_supported', return_value=True)
def test_native_filter_handle_hotkey(supported_mock, install_mock, qtbot):
    callback = MagicMock()
    hotkeys = NativeEventFilter(callback)
    with patch.object(hotkeys, '_register_native', return_value=True):
        hotkeys.register({'foo': ['Ctrl+Alt+T']})
    assert hotkeys.handle_hotkey(5) is False
    assert hotkeys.handle_hotkey(1) is True
    qtbot.waitUntil(lambda: callback.called)
    callback.assert_called_once_with('foo')


@patch('myRef.window.NativeEventFilter.install')
@patch('myRef.window.NativeEventFilter.is_supported', return_value=True)
def test_native_filter_unregister_all(supported_mock, install_mock):
    hotkeys = NativeEventFilter(MagicMock())
    with patch.object(hotkeys, '_register_native', return_value=True):
        hotkeys.register({'foo': ['Ctrl+Alt+T']})
    with patch.object(hotkeys, '_unregister_native') as unreg_mock:
        hotkeys.unregister_all()
    unreg_mock.assert_called_once_with(1)
    assert hotkeys.registered == {}


@patch('myRef.window.NativeEventFilter.is_supported', return_value=False)
def test_native_filter_does_nothing_when_unsupported(supported_mock):
    hotkeys = NativeEventFilter(MagicMock())
    with patch.object(hotkeys, '_register_native') as reg_mock:
        assert hotkeys.register({'foo': ['Ctrl+Alt+T']}) == []
    reg_mock.assert_not_called()
    hotkeys.set_locked_window(123)
    assert hotkeys.installed is False


def test_global_hotkey_bindings_off_by_default(view):
    assert view.global_hotkey_bindings() == {}


def test_global_hotkey_bindings(view, settings):
    settings.setValue('Window/global_hotkeys', True)
    bindings = view.global_hotkey_bindings()
    assert bindings['click_through'] == ['Ctrl+T']
    assert bindings['opacity_increase'] == ['Ctrl+Shift++', 'Ctrl+Shift+=']
    # Actions without shortcuts aren't registered
    assert 'opacity_reset' not in bindings
    # Only window actions
    assert 'save' not in bindings


def test_global_hotkeys_registered_when_setting_changes(view, settings):
    with patch.object(view.native_filter, 'register',
                      return_value=[]) as reg_mock:
        settings.setValue('Window/global_hotkeys', True)
    assert 'click_through' in reg_mock.call_args[0][0]


def test_global_hotkeys_registered_when_shortcuts_change(
        view, settings, kbsettings):
    from myRef.actions.actions import actions
    settings.setValue('Window/global_hotkeys', True)
    action = actions['opacity_reset']
    # Don't write to the real keyboard settings file
    with patch.object(action, 'kb_settings', kbsettings):
        with patch.object(view.native_filter, 'register',
                          return_value=[]) as reg_mock:
            action.set_shortcuts(['Ctrl+Alt+Home'])
        assert reg_mock.call_args[0][0]['opacity_reset'] == [
            'Ctrl+Alt+Home']


@patch('myRef.widgets.BeeNotification')
def test_global_hotkeys_notifies_failure(notify_mock, view):
    with patch.object(view.native_filter, 'register',
                      return_value=['Ctrl+Alt+T']):
        view.register_global_hotkeys()
    notify_mock.assert_called_once()
    assert 'Ctrl+Alt+T' in notify_mock.call_args[0][1]


def test_on_global_hotkey_triggers_action(view, no_native_click_through):
    with patch.object(view, 'recreate_window'):
        view.on_global_hotkey('click_through')
    assert view.click_through is True
    assert view.get_qaction('click_through').isChecked() is True


def test_close_window_modes(view):
    with patch.object(view.native_filter, 'unregister_all') as unreg_mock:
        view.parent.close()
    unreg_mock.assert_called_once()


# Opacity

def test_opacity_decrease_increase(view, settings):
    view.on_action_opacity_decrease()
    assert settings.valueOrDefault('Window/opacity') == 90
    assert view.parent.windowOpacity() == pytest.approx(0.9, abs=0.01)
    view.on_action_opacity_increase()
    assert settings.valueOrDefault('Window/opacity') == 100
    view.on_action_opacity_increase()
    assert settings.valueOrDefault('Window/opacity') == 100


def test_opacity_has_minimum(view, settings):
    for i in range(20):
        view.on_action_opacity_decrease()
    assert settings.valueOrDefault('Window/opacity') == 5


def test_opacity_reset(view, settings):
    view.set_window_opacity(30)
    view.on_action_opacity_reset()
    assert settings.valueOrDefault('Window/opacity') == 100
    assert view.parent.windowOpacity() == pytest.approx(1)


def test_opacity_setting_applies_to_window(view, settings):
    settings.setValue('Window/opacity', 50)
    assert view.parent.windowOpacity() == pytest.approx(0.5, abs=0.01)


@patch('myRef.widgets.BeeNotification')
def test_opacity_notifies(notify_mock, view):
    view.notify_window_modes = True
    view.on_action_opacity_decrease()
    notify_mock.assert_called_once_with(view, 'Opacity: 90 %')


@patch('myRef.widgets.BeeNotification')
def test_notification_can_be_turned_off(notify_mock, view, settings):
    settings.setValue('Window/notify_mode_change', False)
    view.notify_window_modes = True
    view.on_action_opacity_decrease()
    notify_mock.assert_not_called()


@patch('myRef.widgets.BeeNotification')
def test_no_notifications_before_startup(notify_mock, view):
    view.notify_window_modes = False
    view.on_action_opacity_decrease()
    notify_mock.assert_not_called()


# Always on top / bottom

def test_always_on_bottom_unchecks_always_on_top(view, no_recreate,
                                                 settings):
    view.get_qaction('always_on_top').setChecked(True)
    no_recreate.reset_mock()
    view.get_qaction('always_on_bottom').setChecked(True)
    no_recreate.assert_called_once_with({
        Qt.WindowType.WindowStaysOnBottomHint: True,
        Qt.WindowType.WindowStaysOnTopHint: False})
    assert view.get_qaction('always_on_top').isChecked() is False
    assert settings.value('Window/last_always_on_top', type=bool) is False
    assert settings.value('Window/last_always_on_bottom', type=bool) is True


def test_always_on_top_unchecks_always_on_bottom(view, no_recreate,
                                                 settings):
    view.get_qaction('always_on_bottom').setChecked(True)
    no_recreate.reset_mock()
    view.get_qaction('always_on_top').setChecked(True)
    no_recreate.assert_called_once_with({
        Qt.WindowType.WindowStaysOnTopHint: True,
        Qt.WindowType.WindowStaysOnBottomHint: False})
    assert view.get_qaction('always_on_bottom').isChecked() is False
    assert settings.value('Window/last_always_on_top', type=bool) is True


@patch('PyQt6.QtWidgets.QWidget.create')
@patch('PyQt6.QtWidgets.QWidget.destroy')
@patch('PyQt6.QtWidgets.QWidget.show')
def test_recreate_window_sets_flags(show_mock, destroy_mock, create_mock,
                                    view):
    view.recreate_window({Qt.WindowType.WindowStaysOnBottomHint: True})
    assert view.parent.windowFlags() & Qt.WindowType.WindowStaysOnBottomHint
    show_mock.assert_called_once()


@patch('myRef.widgets.BeeNotification')
def test_always_on_top_of_app_only_on_windows(notify_mock, view):
    with patch('myRef.window.IS_WINDOWS', False):
        view.on_action_always_on_top_of_app()
    notify_mock.assert_called_once_with(
        view, 'This is only available on Windows')


@patch('myRef.window.AppOnTopTracker')
@patch('myRef.window.list_app_windows',
       return_value=[('Foo', 123), ('Bar', 456)])
@patch('PyQt6.QtWidgets.QInputDialog.getItem', return_value=('Foo', True))
def test_always_on_top_of_app(dialog_mock, list_mock, tracker_mock, view,
                              no_recreate):
    view.get_qaction('always_on_top').setChecked(True)
    with patch('myRef.window.IS_WINDOWS', True):
        view.on_action_always_on_top_of_app()
    assert dialog_mock.call_args[0][3] == ['(None)', 'Bar', 'Foo']
    assert tracker_mock.call_args[0][1] == 123
    assert view.app_on_top is tracker_mock.return_value
    assert view.get_qaction('always_on_top').isChecked() is False

    # Choosing "(None)" stops it again
    dialog_mock.return_value = ('(None)', True)
    with patch('myRef.window.IS_WINDOWS', True):
        view.on_action_always_on_top_of_app()
    tracker_mock.return_value.stop.assert_called_once()
    assert view.app_on_top is None


@patch('myRef.window.list_app_windows', return_value=[])
@patch('PyQt6.QtWidgets.QInputDialog.getItem', return_value=('', False))
def test_always_on_top_of_app_canceled(dialog_mock, list_mock, view):
    with patch('myRef.window.IS_WINDOWS', True):
        view.on_action_always_on_top_of_app()
    assert view.app_on_top is None


def test_always_on_top_stops_app_on_top(view, no_recreate):
    tracker = MagicMock()
    view.app_on_top = tracker
    view.get_qaction('always_on_top').setChecked(True)
    tracker.stop.assert_called_once()
    assert view.app_on_top is None


# Startup mode

def test_startup_mode_normal(view, no_recreate, settings):
    settings.setValue('Window/last_always_on_top', True)
    view.apply_startup_window_mode()
    assert view.get_qaction('always_on_top').isChecked() is False
    assert view.notify_window_modes is True


def test_startup_mode_last(view, no_recreate, settings):
    settings.setValue('Window/startup_mode', 'last')
    settings.setValue('Window/last_always_on_top', True)
    view.apply_startup_window_mode()
    assert view.get_qaction('always_on_top').isChecked() is True
    assert view.get_qaction('click_through').isChecked() is False


def test_startup_mode_click_through(view, no_recreate,
                                    no_native_click_through, settings):
    settings.setValue('Window/startup_mode', 'click_through')
    view.apply_startup_window_mode()
    assert view.get_qaction('always_on_top').isChecked() is True
    assert view.click_through is True


def test_startup_restores_titlebar_on_hover(view, no_recreate, settings):
    settings.setValue('Window/titlebar_on_hover', True)
    view.apply_startup_window_mode()
    assert view.titlebar_on_hover is True
    assert view.get_qaction('show_titlebar').isChecked() is False


# Click-through

def test_click_through_on_off(view, no_recreate, no_native_click_through,
                              settings):
    view.on_action_click_through(True)
    assert view.click_through is True
    assert settings.value('Window/last_click_through', type=bool) is True
    if window.IS_WINDOWS:
        no_native_click_through.assert_called_once()
    else:
        no_recreate.assert_called_once_with(
            {Qt.WindowType.WindowTransparentForInput: True})
    view.on_action_click_through(False)
    assert view.click_through is False


def test_click_through_shows_tray_icon(view, no_recreate,
                                       no_native_click_through,
                                       tray_available):
    assert view.tray_icon is None
    view.get_qaction('click_through').setChecked(True)
    assert view.tray_icon.isVisible() is True
    # Clicking the tray icon ends click-through
    view.tray_icon.on_activated(
        QtWidgets.QSystemTrayIcon.ActivationReason.Trigger)
    assert view.click_through is False
    assert view.tray_icon.isVisible() is False


def test_tray_icon_setting(view, settings, tray_available):
    settings.setValue('Window/tray_icon', True)
    assert view.tray_icon.isVisible() is True
    settings.setValue('Window/tray_icon', False)
    assert view.tray_icon.isVisible() is False


def test_tray_icon_toggle_window(view, settings, tray_available):
    settings.setValue('Window/tray_icon', True)
    view.tray_icon.toggle_window()
    assert view.parent.isVisible() is False
    view.tray_icon.toggle_window()
    assert view.parent.isVisible() is True


@pytest.fixture
def tray_available(qapp):
    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        pytest.skip('No system tray')


# Locking the window

def test_lock_window_fixes_size(view):
    size = view.parent.size()
    view.on_action_lock_window(True)
    assert view.parent.minimumSize() == size
    assert view.parent.maximumSize() == size
    view.on_action_lock_window(False)
    assert view.parent.minimumSize() == QtCore.QSize(0, 0)
    assert view.parent.maximumSize().width() > 10000


def test_lock_window_blocks_native_move(view):
    view.on_action_lock_window(True)
    assert view.native_filter.locked_hwnd == int(view.parent.winId())
    view.on_action_lock_window(False)
    assert view.native_filter.locked_hwnd is None


@patch('myRef.widgets.BeeNotification')
def test_lock_window_blocks_move_window_mode(notify_mock, view):
    make_image(view)
    view.on_action_lock_window(True)
    view.enter_movewin_mode()
    assert view.movewin_active is False
    notify_mock.assert_called_with(view, 'The window is locked')


@patch('myRef.widgets.BeeNotification')
def test_lock_window_blocks_move_window_mode_overlay(notify_mock, view):
    view.on_action_lock_window(True)
    view.welcome_overlay.enter_movewin_mode()
    assert view.welcome_overlay.movewin_active is False


@patch('myRef.widgets.BeeNotification')
def test_lock_window_blocks_fullscreen(notify_mock, view):
    view.on_action_lock_window(True)
    view.get_qaction('fullscreen').setChecked(True)
    assert view.parent.isFullScreen() is False
    assert view.get_qaction('fullscreen').isChecked() is False


# Maximize

def test_maximize_window(view, settings):
    geom = view.parent.geometry()
    view.get_qaction('maximize_window').setChecked(True)
    assert view.normal_geometry == geom
    available = view.parent.screen().availableGeometry()
    assert view.parent.geometry().width() > geom.width()
    assert available.contains(view.parent.geometry())
    view.get_qaction('maximize_window').setChecked(False)
    assert view.parent.geometry() == geom
    assert view.normal_geometry is None


def test_maximize_window_over_taskbar(view, settings):
    settings.setValue('Window/maximize_over_taskbar', True)
    with patch.object(view, 'client_geometry_for',
                      side_effect=lambda r: r) as geom_mock:
        view.get_qaction('maximize_window').setChecked(True)
    geom_mock.assert_called_once_with(view.parent.screen().geometry())


def test_maximize_window_lock_when_maximized(view, settings):
    settings.setValue('Window/lock_when_maximized', True)
    view.get_qaction('maximize_window').setChecked(True)
    assert view.is_window_size_locked() is True
    assert view.parent.minimumSize() == view.parent.maximumSize()
    view.get_qaction('maximize_window').setChecked(False)
    assert view.is_window_size_locked() is False
    assert view.parent.minimumSize() == QtCore.QSize(0, 0)


@patch('myRef.widgets.BeeNotification')
def test_maximize_window_when_locked(notify_mock, view):
    geom = view.parent.geometry()
    view.on_action_lock_window(True)
    view.get_qaction('maximize_window').setChecked(True)
    assert view.get_qaction('maximize_window').isChecked() is False
    assert view.parent.geometry() == geom


# Fit window to selection

def test_fit_window_to_selection(view, qtbot):
    view.parent.resize(600, 500)
    make_image(view, 200, 150)
    view.setTransform(QtGui.QTransform())
    view.on_action_fit_window_to_selection()
    assert view.scale_on_resize_paused is True
    qtbot.waitUntil(lambda: view.scale_on_resize_paused is False)
    viewport = view.viewport().size()
    assert abs(viewport.width() - 200) <= 6
    assert abs(viewport.height() - 150) <= 6


def test_fit_window_to_selection_uses_all_items_without_selection(
        view, qtbot):
    make_image(view, 200, 150, selected=False)
    with patch.object(view.scene, 'itemsBoundingRect',
                      return_value=QtCore.QRectF(0, 0, 200, 150)) as rect:
        view.on_action_fit_window_to_selection()
    assert rect.call_args_list[0] == ((), {"selection_only": False})
    qtbot.waitUntil(lambda: view.scale_on_resize_paused is False)


@patch('myRef.widgets.BeeNotification')
def test_fit_window_to_selection_when_locked(notify_mock, view):
    make_image(view)
    geom = view.parent.geometry()
    view.on_action_lock_window(True)
    view.on_action_fit_window_to_selection()
    assert view.parent.geometry() == geom
    notify_mock.assert_called_with(view, 'The window is locked')


# Scale on resize

def test_scale_scene_on_resize(view, settings):
    settings.setValue('Window/scale_on_resize', True)
    make_image(view)
    view.setTransform(QtGui.QTransform())
    view.scale_scene_on_resize(
        QtCore.QSize(200, 100), QtCore.QSize(100, 60), QtCore.QPointF(0, 0))
    assert view.transform().m11() == pytest.approx(0.5)


def test_scale_scene_on_resize_off_by_default(view):
    make_image(view)
    view.setTransform(QtGui.QTransform())
    view.scale_scene_on_resize(
        QtCore.QSize(200, 100), QtCore.QSize(100, 60), QtCore.QPointF(0, 0))
    assert view.transform().m11() == 1


def test_scale_scene_on_resize_paused(view, settings):
    settings.setValue('Window/scale_on_resize', True)
    make_image(view)
    view.setTransform(QtGui.QTransform())
    view.scale_on_resize_paused = True
    view.scale_scene_on_resize(
        QtCore.QSize(200, 100), QtCore.QSize(100, 60), QtCore.QPointF(0, 0))
    assert view.transform().m11() == 1


def test_scale_scene_on_resize_invalid_old_size(view, settings):
    settings.setValue('Window/scale_on_resize', True)
    make_image(view)
    view.setTransform(QtGui.QTransform())
    view.scale_scene_on_resize(
        QtCore.QSize(-1, -1), QtCore.QSize(100, 60), QtCore.QPointF(0, 0))
    assert view.transform().m11() == 1


def test_resize_event_scales_scene(view, settings, qtbot):
    settings.setValue('Window/scale_on_resize', True)
    make_image(view)
    view.setTransform(QtGui.QTransform())
    view.parent.resize(400, 400)
    qtbot.waitUntil(lambda: view.parent.width() == 400)
    view.setTransform(QtGui.QTransform())
    view.parent.resize(200, 200)
    qtbot.waitUntil(lambda: view.transform().m11() < 0.9)


# Title bar on hover and frameless windows

def test_titlebar_on_hover_hides_titlebar(view, no_recreate, settings):
    view.get_qaction('titlebar_on_hover').setChecked(True)
    assert view.titlebar_on_hover is True
    assert view.get_qaction('show_titlebar').isChecked() is False
    no_recreate.assert_called_once_with(
        {Qt.WindowType.FramelessWindowHint: True})
    assert settings.value('Window/titlebar_on_hover', type=bool) is True


def test_show_titlebar_ends_titlebar_on_hover(view, no_recreate, settings):
    view.get_qaction('titlebar_on_hover').setChecked(True)
    view.get_qaction('show_titlebar').setChecked(True)
    assert view.titlebar_on_hover is False
    assert view.get_qaction('titlebar_on_hover').isChecked() is False
    assert settings.value('Window/titlebar_on_hover', type=bool) is False


@pytest.fixture
def frameless(view):
    controller = view.frame_controller
    with patch.object(controller, 'is_frameless', return_value=True):
        yield controller


def test_edges_at(view, frameless):
    view.parent.resize(300, 200)
    assert frameless.edges_at(QtCore.QPoint(2, 2)) == (
        Qt.Edge.LeftEdge | Qt.Edge.TopEdge)
    assert frameless.edges_at(QtCore.QPoint(299, 100)) == Qt.Edge.RightEdge
    assert frameless.edges_at(QtCore.QPoint(150, 199)) == Qt.Edge.BottomEdge
    assert not frameless.edges_at(QtCore.QPoint(150, 100))


def test_edges_at_respects_border_setting(view, frameless, settings):
    settings.setValue('Window/resize_border', 20)
    assert frameless.edges_at(QtCore.QPoint(15, 100)) == Qt.Edge.LeftEdge


def test_edges_at_when_locked(view, frameless):
    view.on_action_lock_window(True)
    assert not frameless.edges_at(QtCore.QPoint(2, 2))


def test_edges_at_when_not_frameless(view):
    assert not view.frame_controller.edges_at(QtCore.QPoint(2, 2))


def test_update_cursor(view, frameless):
    viewport = view.viewport()
    frameless.update_cursor(viewport, Qt.Edge.LeftEdge)
    assert viewport.cursor().shape() == Qt.CursorShape.SizeHorCursor
    frameless.update_cursor(viewport, Qt.Edge(0))
    assert viewport.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert viewport not in frameless.cursor_overridden


def test_update_titlebar(view, frameless):
    titlebar = frameless.titlebar
    frameless.update_titlebar(QtCore.QPoint(50, 5))
    assert titlebar.isVisible() is False
    view.titlebar_on_hover = True
    frameless.update_titlebar(QtCore.QPoint(50, 5))
    assert titlebar.isVisible() is True
    assert titlebar.width() == view.parent.width()
    frameless.update_titlebar(QtCore.QPoint(50, titlebar.HEIGHT + 5))
    assert titlebar.isVisible() is True
    frameless.update_titlebar(QtCore.QPoint(50, 100))
    assert titlebar.isVisible() is False


def test_titlebar_shows_window_title(view, frameless):
    view.titlebar_on_hover = True
    frameless.update_titlebar(QtCore.QPoint(50, 5))
    assert frameless.titlebar.title.text() == view.parent.windowTitle()


def test_titlebar_toggle_maximized(view):
    titlebar = view.frame_controller.titlebar
    with patch.object(view.parent, 'showMaximized') as max_mock:
        titlebar.toggle_maximized()
    max_mock.assert_called_once()


def test_press_on_border_starts_resize(view, frameless):
    view.parent.resize(300, 200)
    handle = MagicMock()
    with patch.object(view.parent, 'windowHandle', return_value=handle):
        event = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QPointF(1, 100),
            view.parent.mapToGlobal(QtCore.QPointF(1, 100)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier)
        assert frameless.eventFilter(view.viewport(), event) is True
    handle.startSystemResize.assert_called_once_with(Qt.Edge.LeftEdge)


def test_press_inside_does_not_resize(view, frameless):
    view.parent.resize(300, 200)
    event = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonPress,
        QtCore.QPointF(150, 100),
        view.parent.mapToGlobal(QtCore.QPointF(150, 100)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    assert frameless.eventFilter(view.viewport(), event) is False


# Settings

def test_settings_dialog_window_tab(view):
    dialog = SettingsDialog(view)
    assert dialog.tabs.tabText(5) == '&Window'
    assert isinstance(dialog.tabs.widget(5).findChild(WindowOpacityWidget),
                      WindowOpacityWidget)
    dialog.close()


@patch('myRef.widgets.BeeNotification')
def test_new_notice_replaces_previous(notify_mock, view):
    first, second = MagicMock(), MagicMock()
    notify_mock.side_effect = [first, second]
    view.notify_window_modes = True
    view.on_action_opacity_decrease()
    view.on_action_opacity_decrease()
    first.deleteLater.assert_called_once()
    assert view.window_mode_notice is second


def test_new_notice_when_previous_already_deleted(view, qtbot):
    view.notify_window_modes = True
    view.on_action_opacity_decrease()
    view.window_mode_notice.deleteLater()
    qtbot.waitUntil(lambda: _is_deleted(view.window_mode_notice))
    view.on_action_opacity_decrease()
    assert view.window_mode_notice.isVisible() is True


def _is_deleted(widget):
    try:
        widget.isVisible()
    except RuntimeError:
        return True
    return False
