from unittest.mock import MagicMock, patch

from PyQt6 import QtCore, QtGui, QtTest, QtWidgets
from PyQt6.QtCore import Qt
import pytest

from beeref.actions.actions import actions
from beeref.config import settings_events
from beeref.config.controls import mouse_binding_matches_event
from beeref.config.settings import cast_bool, is_valid_mouse_binding
from beeref.items import BeePixmapItem, BeeTextItem
from beeref.widgets.settings import (
    ExportNameTemplateWidget,
    LockIconCornerWidget,
    LockIconSizeWidget,
    LockIconTransparencyWidget,
    SettingsDialog,
    TabletPanWidget,
    TabletZoomInvertedWidget,
)
from beeref.widgets.view_buttons import TitleBarButton


RIGHT = Qt.MouseButton.RightButton
LEFT = Qt.MouseButton.LeftButton
MIDDLE = Qt.MouseButton.MiddleButton
NO_MODIFIER = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier


def mouse_event(button=RIGHT, modifiers=NO_MODIFIER, pos=(10, 10)):
    event = MagicMock()
    event.button.return_value = button
    event.modifiers.return_value = modifiers
    event.position.return_value = QtCore.QPointF(*pos)
    event.pos.return_value = QtCore.QPoint(*pos)
    return event


@pytest.fixture
def tablet_view(view, item):
    view.scene.addItem(item)
    actions['tablet_mode'].qaction.setChecked(True)
    return view


def lock_items():
    actions['lock_items'].qaction.setChecked(True)


# Mouse bindings

@pytest.mark.parametrize('binding,event_button,event_modifiers,expected', [
    ('Right', RIGHT, NO_MODIFIER, True),
    ('Right', RIGHT, CTRL, False),
    ('Right', LEFT, NO_MODIFIER, False),
    ('Ctrl+Right', RIGHT, CTRL, True),
    ('Ctrl+Right', RIGHT, NO_MODIFIER, False),
    ('Middle', MIDDLE, NO_MODIFIER, True),
    ('Shift+Ctrl+Left', LEFT, Qt.KeyboardModifier.ShiftModifier | CTRL, True),
    ('Not Configured', Qt.MouseButton.NoButton, NO_MODIFIER, False),
])
def test_mouse_binding_matches_event(
        binding, event_button, event_modifiers, expected):
    event = mouse_event(event_button, event_modifiers)
    assert mouse_binding_matches_event(binding, event) is expected


@pytest.mark.parametrize('value,expected', [
    ('Right', True),
    ('Ctrl+Alt+Left', True),
    ('Not Configured', True),
    ('Foo', False),
    ('Foo+Right', False),
    ('', False),
])
def test_is_valid_mouse_binding(value, expected):
    assert is_valid_mouse_binding(value) is expected


@pytest.mark.parametrize('value,expected', [
    ('true', True), ('false', False), (True, True), (False, False)])
def test_cast_bool(value, expected):
    assert cast_bool(value) is expected


def test_invalid_mouse_binding_falls_back_to_default(settings):
    QtCore.QSettings.setValue(settings, 'TabletMode/pan', 'Foo')
    assert settings.valueOrDefault('TabletMode/pan') == 'Right'


def test_confirm_close_setting_survives_reading_from_file(settings):
    QtCore.QSettings.setValue(settings, 'Save/confirm_close_unsaved', 'false')
    assert settings.valueOrDefault('Save/confirm_close_unsaved') is False
    QtCore.QSettings.setValue(settings, 'Save/confirm_close_unsaved', 'true')
    assert settings.valueOrDefault('Save/confirm_close_unsaved') is True


def test_boolean_settings_survive_reading_from_file(settings):
    # Booleans come back as strings after a restart
    QtCore.QSettings.setValue(
        settings, 'TabletMode/show_titlebar_button', 'false')
    assert settings.valueOrDefault('TabletMode/show_titlebar_button') is False


# Tablet mode: Pan and zoom

def test_tablet_mode_is_off_by_default(view):
    assert view.tablet_mode is False


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_right_button_does_nothing_when_tablet_mode_off(press_mock, view):
    view.mousePressEvent(mouse_event())
    assert view.active_mode is None
    assert view.context_menu_blocked is False
    press_mock.assert_called_once()


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_right_button_pans_in_tablet_mode(press_mock, tablet_view):
    tablet_view.mousePressEvent(mouse_event())
    assert tablet_view.active_mode == tablet_view.PAN_MODE
    press_mock.assert_not_called()


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_ctrl_right_button_zooms_in_tablet_mode(press_mock, tablet_view):
    tablet_view.mousePressEvent(mouse_event(modifiers=CTRL))
    assert tablet_view.active_mode == tablet_view.ZOOM_MODE
    assert tablet_view.event_inverted is False
    press_mock.assert_not_called()


def test_regular_controls_still_work_in_tablet_mode(tablet_view):
    tablet_view.mousePressEvent(mouse_event(button=MIDDLE))
    assert tablet_view.active_mode == tablet_view.PAN_MODE
    assert tablet_view.context_menu_blocked is False


def test_tablet_controls_can_be_configured(tablet_view, settings):
    settings.setValue('TabletMode/pan', 'Alt+Right')
    settings.setValue('TabletMode/zoom', 'Left')
    settings.setValue('TabletMode/zoom_inverted', True)

    tablet_view.mousePressEvent(mouse_event(button=LEFT))
    assert tablet_view.active_mode == tablet_view.ZOOM_MODE
    assert tablet_view.event_inverted is True
    tablet_view.active_mode = None

    tablet_view.mousePressEvent(
        mouse_event(modifiers=Qt.KeyboardModifier.AltModifier))
    assert tablet_view.active_mode == tablet_view.PAN_MODE


@patch('PyQt6.QtWidgets.QGraphicsView.mousePressEvent')
def test_not_configured_binding_is_ignored(press_mock, tablet_view, settings):
    settings.setValue('TabletMode/pan', 'Not Configured')
    tablet_view.mousePressEvent(mouse_event())
    assert tablet_view.active_mode is None
    press_mock.assert_called_once()


def test_pan_ignores_jitter_and_then_follows_drag(tablet_view):
    tablet_view.pan = MagicMock()
    tablet_view.mousePressEvent(mouse_event())
    tablet_view.mouseMoveEvent(mouse_event(pos=(11, 11)))
    tablet_view.pan.assert_not_called()

    tablet_view.mouseMoveEvent(mouse_event(pos=(40, 10)))
    tablet_view.pan.assert_called_once_with(QtCore.QPointF(-30, 0))
    assert tablet_view.right_gesture_moved is True

    # Once dragging, small movements count, too
    tablet_view.mouseMoveEvent(mouse_event(pos=(41, 10)))
    assert tablet_view.pan.call_count == 2


def test_zoom_follows_drag_only_after_threshold(tablet_view):
    tablet_view.zoom = MagicMock()
    tablet_view.mousePressEvent(mouse_event(modifiers=CTRL))
    tablet_view.mouseMoveEvent(mouse_event(modifiers=CTRL, pos=(10, 11)))
    tablet_view.zoom.assert_not_called()
    tablet_view.mouseMoveEvent(mouse_event(modifiers=CTRL, pos=(10, 60)))
    tablet_view.zoom.assert_called_once_with(
        -50 * 20, QtCore.QPointF(10, 10))


def test_release_ends_gesture_and_mode(tablet_view):
    tablet_view.mousePressEvent(mouse_event())
    tablet_view.mouseMoveEvent(mouse_event(pos=(100, 10)))
    tablet_view.mouseReleaseEvent(mouse_event(pos=(100, 10)))
    assert tablet_view.active_mode is None
    assert tablet_view.right_gesture_start is None


# Tablet mode: Context menu

def test_right_click_without_drag_opens_context_menu(tablet_view, qtbot):
    tablet_view.context_menu = MagicMock()
    tablet_view.mousePressEvent(mouse_event())
    tablet_view.mouseReleaseEvent(mouse_event(pos=(11, 11)))
    qtbot.waitUntil(lambda: tablet_view.context_menu.exec.called)
    tablet_view.context_menu.exec.assert_called_once_with(
        tablet_view.mapToGlobal(QtCore.QPoint(11, 11)))
    assert tablet_view.context_menu_blocked is False


def test_right_drag_does_not_open_context_menu(tablet_view, qtbot):
    tablet_view.context_menu = MagicMock()
    tablet_view.mousePressEvent(mouse_event())
    tablet_view.mouseMoveEvent(mouse_event(pos=(100, 10)))
    tablet_view.mouseReleaseEvent(mouse_event(pos=(100, 10)))
    qtbot.waitUntil(lambda: not tablet_view.context_menu_blocked)
    tablet_view.context_menu.exec.assert_not_called()


def test_context_menu_requests_are_ignored_during_gesture(tablet_view, qtbot):
    tablet_view.context_menu = MagicMock()
    tablet_view.mousePressEvent(mouse_event())
    # Some platforms send it on mouse press...
    tablet_view.on_context_menu(QtCore.QPoint(1, 1))
    tablet_view.mouseMoveEvent(mouse_event(pos=(100, 10)))
    tablet_view.mouseReleaseEvent(mouse_event(pos=(100, 10)))
    # ... and others directly after the mouse release:
    tablet_view.on_context_menu(QtCore.QPoint(1, 1))
    tablet_view.context_menu.exec.assert_not_called()

    qtbot.waitUntil(lambda: not tablet_view.context_menu_blocked)
    tablet_view.on_context_menu(QtCore.QPoint(1, 1))
    tablet_view.context_menu.exec.assert_called_once()


def test_right_click_with_real_events_opens_menu_once(
        tablet_view, qtbot, qapp):
    """Goes through Qt's event delivery, including its own context menu
    event, which is sent at a platform dependent time."""

    tablet_view.context_menu = MagicMock()
    QtTest.QTest.mouseClick(tablet_view.parent.windowHandle(), RIGHT,
                            pos=QtCore.QPoint(50, 50))
    qtbot.waitUntil(lambda: tablet_view.context_menu.exec.called)
    qapp.processEvents()
    tablet_view.context_menu.exec.assert_called_once()
    assert tablet_view.active_mode is None


def test_right_drag_with_real_events_pans_without_menu(
        tablet_view, qtbot, qapp):
    tablet_view.context_menu = MagicMock()
    tablet_view.pan = MagicMock()
    window = tablet_view.parent.windowHandle()
    QtTest.QTest.mousePress(window, RIGHT, pos=QtCore.QPoint(50, 50))
    assert tablet_view.active_mode == tablet_view.PAN_MODE
    QtTest.QTest.mouseMove(window, QtCore.QPoint(120, 80))
    QtTest.QTest.mouseRelease(window, RIGHT, pos=QtCore.QPoint(120, 80))
    qtbot.waitUntil(lambda: not tablet_view.context_menu_blocked)
    qapp.processEvents()
    tablet_view.context_menu.exec.assert_not_called()
    tablet_view.pan.assert_called()


def test_tablet_mode_state_is_stored(view, settings):
    actions['tablet_mode'].qaction.setChecked(True)
    assert settings.value('TabletMode/enabled', type=bool) is True


def test_tablet_mode_state_is_restored(settings, qtbot, qapp):
    from beeref.__main__ import BeeRefMainWindow
    settings.setValue('TabletMode/enabled', True)
    main = BeeRefMainWindow(qapp)
    qtbot.addWidget(main)
    assert main.view.tablet_mode is True


# Locking: Scene

def is_locked(item):
    return not (item.flags()
                & (QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                   | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                   ))


def test_lock_and_unlock_all_items(view, item):
    text = BeeTextItem('foo')
    view.scene.addItem(item)
    view.scene.addItem(text)
    assert not is_locked(item)

    view.scene.set_items_locked(True)
    assert is_locked(item)
    assert is_locked(text)

    view.scene.set_items_locked(False)
    assert not is_locked(item)
    assert not is_locked(text)
    item.setSelected(True)
    assert item.isSelected()


def test_lock_clears_selection_and_disables_selection_actions(view, item):
    view.scene.addItem(item)
    item.setSelected(True)
    assert actions['delete'].qaction.isEnabled()

    lock_items()
    assert view.scene.selectedItems() == []
    assert not actions['delete'].qaction.isEnabled()


def test_lock_clears_multi_selection(view, item):
    item2 = BeePixmapItem(
        QtGui.QImage(10, 10, QtGui.QImage.Format.Format_RGB32))
    view.scene.addItem(item)
    view.scene.addItem(item2)
    view.scene.select_all_items()
    assert view.scene.multi_select_item.scene()

    lock_items()
    assert view.scene.selectedItems() == []
    assert view.scene.multi_select_item.scene() is None


def test_select_all_selects_nothing_when_locked(view, item):
    view.scene.addItem(item)
    lock_items()
    view.scene.select_all_items()
    assert view.scene.selectedItems() == []


def test_items_added_while_locked_are_locked(view, item):
    lock_items()
    view.scene.addItem(item)
    assert is_locked(item)
    view.scene.set_items_locked(False)
    assert not is_locked(item)


def test_helper_items_stay_selectable_when_locked(view):
    view.scene.set_items_locked(True)
    assert not is_locked(view.scene.multi_select_item)
    view.scene.addItem(view.scene.rubberband_item)


def test_lock_ends_text_edit_mode(view):
    text = BeeTextItem('foo')
    view.scene.addItem(text)
    text.setSelected(True)
    text.enter_edit_mode()

    view.scene.set_items_locked(True)
    assert text.edit_mode is False
    assert view.scene.edit_item is None


def test_lock_cancels_crop_mode(view, item):
    view.scene.addItem(item)
    item.setSelected(True)
    item.enter_crop_mode()
    assert view.scene.crop_item is item

    view.scene.set_items_locked(True)
    assert view.scene.crop_item is None


def scene_mouse_event(button=LEFT, pos=(5, 5)):
    event = MagicMock()
    event.button.return_value = button
    event.scenePos.return_value = QtCore.QPointF(*pos)
    return event


def test_click_on_locked_item_does_nothing(view, item):
    view.scene.addItem(item)
    view.scene.set_items_locked(True)
    view.scene.mousePressEvent(scene_mouse_event(pos=(5, 5)))
    assert view.scene.active_mode is None
    assert item.isSelected() is False


@patch('PyQt6.QtWidgets.QGraphicsScene.mouseMoveEvent')
def test_no_rubberband_when_locked(move_mock, view, item):
    view.scene.addItem(item)
    view.scene.set_items_locked(True)
    view.scene.mousePressEvent(scene_mouse_event(pos=(500, 500)))
    assert view.scene.active_mode is None
    view.scene.mouseMoveEvent(scene_mouse_event(pos=(510, 510)))
    assert view.scene.rubberband_item.scene() is None


def test_locked_item_keeps_position_on_real_drag(view, item, qapp):
    item.setPos(0, 0)
    view.scene.addItem(item)
    view.fitInView(item, Qt.AspectRatioMode.KeepAspectRatio)
    lock_items()
    start = view.mapFromScene(item.center_scene_coords)
    viewport = view.viewport()
    QtTest.QTest.mousePress(viewport, LEFT, pos=start)
    QtTest.QTest.mouseMove(viewport, start + QtCore.QPoint(30, 30))
    QtTest.QTest.mouseRelease(viewport, LEFT,
                              pos=start + QtCore.QPoint(30, 30))
    qapp.processEvents()
    assert item.pos() == QtCore.QPointF(0, 0)
    assert view.scene.selectedItems() == []
    assert view.undo_stack.count() == 0


def test_double_click_on_locked_text_fits_instead_of_editing(view):
    text = BeeTextItem('foo')
    view.scene.addItem(text)
    view.scene.set_items_locked(True)
    view.fit_rect = MagicMock()
    event = scene_mouse_event(pos=(5, 5))
    view.scene.itemAt = MagicMock(return_value=text)
    view.scene.mouseDoubleClickEvent(event)
    assert text.edit_mode is False
    view.fit_rect.assert_called_once()


def test_double_click_on_locked_image_fits_item(view, item):
    view.scene.addItem(item)
    view.scene.set_items_locked(True)
    view.fit_rect = MagicMock()
    view.scene.mouseDoubleClickEvent(scene_mouse_event(pos=(5, 5)))
    view.fit_rect.assert_called_once()


# Locking: View

def test_undo_redo_disabled_while_locked(view):
    view.undo_stack.push(QtGui.QUndoCommand())
    view.undo_stack.push(QtGui.QUndoCommand())
    view.undo_stack.undo()
    assert actions['undo'].qaction.isEnabled()
    assert actions['redo'].qaction.isEnabled()

    lock_items()
    assert not actions['undo'].qaction.isEnabled()
    assert not actions['redo'].qaction.isEnabled()

    # New commands while locked don't reenable them
    view.undo_stack.push(QtGui.QUndoCommand())
    assert not actions['undo'].qaction.isEnabled()

    actions['lock_items'].qaction.setChecked(False)
    assert actions['undo'].qaction.isEnabled()


def test_pan_and_zoom_still_work_when_locked(tablet_view):
    lock_items()
    tablet_view.mousePressEvent(mouse_event())
    assert tablet_view.active_mode == tablet_view.PAN_MODE


def test_lock_state_is_stored(view, settings):
    lock_items()
    assert settings.value('View/lock_items', type=bool) is True


def test_lock_state_is_restored(settings, qtbot, qapp):
    from beeref.__main__ import BeeRefMainWindow
    settings.setValue('View/lock_items', True)
    main = BeeRefMainWindow(qapp)
    qtbot.addWidget(main)
    assert main.view.scene.items_locked is True
    assert main.view.lock_button.isChecked()


# Lock button

def test_lock_button_click_toggles_lock(view, qtbot):
    QtTest.QTest.mouseClick(view.lock_button, LEFT)
    assert actions['lock_items'].qaction.isChecked()
    assert view.scene.items_locked is True
    assert view.lock_button.isChecked()

    QtTest.QTest.mouseClick(view.lock_button, LEFT)
    assert not actions['lock_items'].qaction.isChecked()
    assert view.scene.items_locked is False


def test_lock_button_follows_action(view):
    lock_items()
    assert view.lock_button.isChecked()


def test_lock_button_default_appearance(view):
    assert view.lock_button.width() == 24
    assert view.lock_button.height() == 24
    assert view.lock_button.icon_opacity == pytest.approx(0.7)
    assert view.lock_button.isVisible()


@pytest.mark.parametrize('corner,x,y', [
    ('top_left', 10, 10),
    ('top_right', 400 - 24 - 10, 10),
    ('bottom_left', 10, 300 - 24 - 10),
    ('bottom_right', 400 - 24 - 10, 300 - 24 - 10),
])
def test_lock_button_corner(view, settings, corner, x, y):
    view.setFixedSize(400, 300)
    settings.setValue('LockIcon/corner', corner)
    assert (view.lock_button.x(), view.lock_button.y()) == (x, y)


def test_lock_button_stays_in_corner_on_resize(view, qapp):
    view.setFixedSize(400, 300)
    qapp.processEvents()
    view.setFixedSize(600, 500)
    qapp.processEvents()
    assert view.lock_button.y() == 500 - 24 - 10
    assert view.lock_button.x() == 10


def test_lock_button_avoids_scrollbars(view, settings, item, qapp):
    settings.setValue('LockIcon/corner', 'bottom_right')
    view.setFixedSize(400, 300)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    qapp.processEvents()
    viewport_width = view.viewport().width()
    assert viewport_width < 400
    assert view.lock_button.x() == viewport_width - 24 - 10


def test_lock_button_size_setting(view, settings):
    settings.setValue('LockIcon/size', 64)
    assert view.lock_button.width() == 64
    assert view.lock_button.height() == 64


def test_lock_button_transparency_setting(view, settings):
    settings.setValue('LockIcon/transparency', 75)
    assert view.lock_button.icon_opacity == pytest.approx(0.25)


def test_lock_button_invalid_settings_fall_back_to_defaults(view, settings):
    QtCore.QSettings.setValue(settings, 'LockIcon/size', 1000)
    QtCore.QSettings.setValue(settings, 'LockIcon/transparency', 100)
    QtCore.QSettings.setValue(settings, 'LockIcon/corner', 'foo')
    view.lock_button.apply_settings()
    assert view.lock_button.width() == 24
    assert view.lock_button.icon_opacity == pytest.approx(0.7)


def test_restore_defaults_resets_lock_button(view, settings):
    settings.setValue('LockIcon/size', 64)
    settings.restore_defaults()
    assert view.lock_button.width() == 24


def test_lock_button_tooltip_shows_state_and_is_translated(view, settings):
    assert 'unlocked' in view.lock_button.toolTip()
    lock_items()
    assert 'are locked' in view.lock_button.toolTip()
    settings.setValue('Interface/language', 'es')
    assert 'bloqueadas' in view.lock_button.toolTip()


def test_lock_button_is_above_welcome_overlay(view):
    siblings = [w for w in view.children() if isinstance(w, QtWidgets.QWidget)]
    assert (siblings.index(view.lock_button)
            > siblings.index(view.welcome_overlay))


@pytest.mark.parametrize('locked', [True, False])
def test_lock_button_paints_both_states(view, locked):
    view.lock_button.setChecked(locked)
    assert not view.lock_button.grab().isNull()


# Title bar button

class Bounds:
    left, top, right, bottom = (300, 8, 438, 40)


@pytest.fixture
def titlebar_button(main_window):
    button = TitleBarButton(main_window)
    yield button
    button.dispose()


def test_titlebar_button_not_created_when_unsupported(view):
    with patch.object(TitleBarButton, 'is_supported', return_value=False):
        view.update_titlebar_button()
    assert view.titlebar_button is None


def test_titlebar_button_created_when_supported(view):
    with patch.object(TitleBarButton, 'is_supported', return_value=True):
        view.update_titlebar_button()
        button = view.titlebar_button
        assert button is not None
        view.update_titlebar_button()
        assert view.titlebar_button is button
    view.titlebar_button.dispose()


def test_titlebar_button_created_at_startup(settings, qtbot, qapp):
    # The title bar action fires early on while the actions get created
    from beeref.__main__ import BeeRefMainWindow
    with patch.object(TitleBarButton, 'is_supported', return_value=True):
        main = BeeRefMainWindow(qapp)
        qtbot.addWidget(main)
        assert main.view.titlebar_button is not None
    main.view.titlebar_button.dispose()


def test_titlebar_button_removed_by_setting(view, settings):
    with patch.object(TitleBarButton, 'is_supported', return_value=True):
        view.update_titlebar_button()
        assert view.titlebar_button is not None
        settings.setValue('TabletMode/show_titlebar_button', False)
        assert view.titlebar_button is None
        settings.setValue('TabletMode/show_titlebar_button', True)
        assert view.titlebar_button is not None
    view.titlebar_button.dispose()


def test_titlebar_button_rebuild_replaces_it(view):
    with patch.object(TitleBarButton, 'is_supported', return_value=True):
        view.update_titlebar_button()
        old = view.titlebar_button
        view.rebuild_titlebar_button()
        assert view.titlebar_button is not old
        assert view.titlebar_button is not None
    view.titlebar_button.dispose()


def test_titlebar_button_rebuild_without_button_does_nothing(view):
    with patch.object(TitleBarButton, 'is_supported', return_value=True):
        view.rebuild_titlebar_button()
    assert view.titlebar_button is None


def test_titlebar_button_toggles_action_and_follows_it(view, qapp):
    with patch.object(TitleBarButton, 'is_supported', return_value=True):
        view.update_titlebar_button()
    button = view.titlebar_button
    button.click()
    assert view.tablet_mode is True
    assert actions['tablet_mode'].qaction.isChecked()

    actions['tablet_mode'].qaction.setChecked(False)
    assert button.isChecked() is False
    button.dispose()


def test_titlebar_button_new_instance_has_current_state(view):
    actions['tablet_mode'].qaction.setChecked(True)
    with patch.object(TitleBarButton, 'is_supported', return_value=True):
        view.update_titlebar_button()
    assert view.titlebar_button.isChecked() is True
    view.titlebar_button.dispose()


def test_titlebar_button_is_left_of_caption_buttons(
        titlebar_button, main_window):
    main_window.frameGeometry = MagicMock(
        return_value=QtCore.QRect(100, 50, 500, 300))
    main_window.devicePixelRatioF = MagicMock(return_value=1)
    titlebar_button.get_caption_buttons_bounds = MagicMock(
        return_value=Bounds)

    rect = titlebar_button.calculate_geometry()
    assert rect.right() < 100 + 300
    assert rect.right() == 100 + 300 - TitleBarButton.GAP - 1
    assert rect.center().y() == pytest.approx(50 + 8 + 16, abs=1)
    assert rect.height() == TitleBarButton.MAX_HEIGHT


def test_titlebar_button_stays_on_screen_when_maximized(
        titlebar_button, main_window):
    class MaximizedBounds:
        left, top, right, bottom = (300, 0, 438, 30)

    screen_top = main_window.screen().availableGeometry().y()
    main_window.frameGeometry = MagicMock(
        return_value=QtCore.QRect(0, screen_top - 8, 500, 300))
    main_window.devicePixelRatioF = MagicMock(return_value=1)
    titlebar_button.get_caption_buttons_bounds = MagicMock(
        return_value=MaximizedBounds)

    rect = titlebar_button.calculate_geometry()
    assert rect.top() >= screen_top
    assert rect.height() == 22 - 2 * TitleBarButton.MIN_MARGIN


def test_titlebar_button_geometry_respects_device_pixel_ratio(
        titlebar_button, main_window):
    main_window.frameGeometry = MagicMock(
        return_value=QtCore.QRect(100, 50, 500, 300))
    main_window.devicePixelRatioF = MagicMock(return_value=2)
    titlebar_button.get_caption_buttons_bounds = MagicMock(
        return_value=Bounds)

    caption = titlebar_button.get_caption_rect()
    assert caption == QtCore.QRectF(250, 54, 69, 16)


def test_titlebar_button_geometry_without_system_info(
        titlebar_button, main_window):
    main_window.frameGeometry = MagicMock(
        return_value=QtCore.QRect(100, 50, 500, 300))
    main_window.geometry = MagicMock(
        return_value=QtCore.QRect(108, 80, 484, 262))
    titlebar_button.get_caption_buttons_bounds = MagicMock(return_value=None)

    caption = titlebar_button.get_caption_rect()
    assert caption.right() == 600
    assert caption.top() == 50
    assert caption.height() == 30


def test_titlebar_button_visible_with_shown_main_window(
        titlebar_button, main_window):
    assert titlebar_button.should_be_visible() is True


def test_titlebar_button_hides_with_main_window(titlebar_button, main_window):
    assert titlebar_button.isVisible()
    main_window.hide()
    assert not titlebar_button.isVisible()
    main_window.show()
    assert titlebar_button.isVisible()


def test_titlebar_button_hidden_when_fullscreen(titlebar_button, main_window):
    main_window.isFullScreen = MagicMock(return_value=True)
    titlebar_button.follow_main_window()
    assert not titlebar_button.isVisible()


def test_titlebar_button_hidden_when_minimized(titlebar_button, main_window):
    main_window.isMinimized = MagicMock(return_value=True)
    titlebar_button.follow_main_window()
    assert not titlebar_button.isVisible()


def test_titlebar_button_hidden_without_title_bar(
        titlebar_button, main_window):
    main_window.windowFlags = MagicMock(
        return_value=Qt.WindowType.FramelessWindowHint)
    titlebar_button.follow_main_window()
    assert not titlebar_button.isVisible()


def test_titlebar_button_follows_main_window_move(
        titlebar_button, main_window, qapp):
    titlebar_button.calculate_geometry = MagicMock(
        return_value=QtCore.QRect(1, 2, 30, 20))
    titlebar_button.eventFilter(
        main_window, QtCore.QEvent(QtCore.QEvent.Type.Move))
    titlebar_button.calculate_geometry.assert_called_once()


def test_titlebar_button_ignores_other_events(titlebar_button, main_window):
    titlebar_button.follow_main_window = MagicMock()
    assert titlebar_button.eventFilter(
        main_window, QtCore.QEvent(QtCore.QEvent.Type.Paint)) is False
    titlebar_button.follow_main_window.assert_not_called()


@pytest.mark.parametrize('checked', [True, False])
def test_titlebar_button_paints_both_states(titlebar_button, checked):
    titlebar_button.setChecked(checked)
    assert not titlebar_button.grab().isNull()


def test_titlebar_button_tooltip_is_translated(titlebar_button, settings):
    assert titlebar_button.toolTip() == 'Tablet Mode'
    settings.setValue('Interface/language', 'es')
    assert titlebar_button.toolTip() == 'Modo tablet'


# Settings dialog

def test_settings_dialog_has_tablet_and_lock_tabs(view):
    dialog = SettingsDialog(view)
    assert dialog.tabs.count() == 7
    assert dialog.tabs.tabText(2) == '&Tablet Mode'
    assert dialog.tabs.tabText(3) == '&Lock Icon'
    assert dialog.tabs.tabText(4) == 'E&xport'
    assert isinstance(
        dialog.tabs.widget(4).findChild(ExportNameTemplateWidget),
        ExportNameTemplateWidget)
    dialog.close()


def test_settings_dialog_tabs_are_translated(view, settings):
    dialog = SettingsDialog(view)
    settings.setValue('Interface/language', 'es')
    assert dialog.tabs.tabText(2) == 'Modo &tablet'
    assert dialog.tabs.tabText(3) == '&Candado'
    dialog.close()


def test_binding_widget_shows_value(settings):
    settings.setValue('TabletMode/pan', 'Shift+Alt+Middle')
    widget = TabletPanWidget()
    assert widget.button_input.currentData() == 'Middle'
    assert widget.modifier_inputs['Shift'].isChecked()
    assert widget.modifier_inputs['Alt'].isChecked()
    assert not widget.modifier_inputs['Ctrl'].isChecked()


def test_binding_widget_saves_button(settings):
    widget = TabletPanWidget()
    widget.button_input.setCurrentIndex(
        widget.button_input.findData('Middle'))
    assert settings.valueOrDefault('TabletMode/pan') == 'Middle'


def test_binding_widget_saves_modifiers(settings):
    widget = TabletPanWidget()
    widget.modifier_inputs['Ctrl'].setChecked(True)
    assert settings.valueOrDefault('TabletMode/pan') == 'Ctrl+Right'
    widget.modifier_inputs['Shift'].setChecked(True)
    assert settings.valueOrDefault('TabletMode/pan') == 'Shift+Ctrl+Right'
    widget.modifier_inputs['Ctrl'].setChecked(False)
    assert settings.valueOrDefault('TabletMode/pan') == 'Shift+Right'


def test_binding_widget_not_configured_disables_modifiers(settings):
    settings.setValue('TabletMode/pan', 'Ctrl+Right')
    widget = TabletPanWidget()
    widget.button_input.setCurrentIndex(
        widget.button_input.findData('Not Configured'))
    assert settings.valueOrDefault('TabletMode/pan') == 'Not Configured'
    assert not widget.modifier_inputs['Ctrl'].isEnabled()

    widget.button_input.setCurrentIndex(widget.button_input.findData('Left'))
    assert widget.modifier_inputs['Ctrl'].isEnabled()
    assert settings.valueOrDefault('TabletMode/pan') == 'Ctrl+Left'


def test_binding_widget_marks_changed_value(settings):
    widget = TabletPanWidget()
    assert '✎' not in widget.title()
    widget.modifier_inputs['Ctrl'].setChecked(True)
    assert '✎' in widget.title()


def test_binding_widget_restore_defaults(settings):
    widget = TabletPanWidget()
    widget.modifier_inputs['Ctrl'].setChecked(True)
    settings.restore_defaults()
    assert widget.modifier_inputs['Ctrl'].isChecked() is False
    assert widget.button_input.currentData() == 'Right'
    assert settings.value('TabletMode/pan') is None


def test_binding_widget_retranslates(settings):
    widget = TabletPanWidget()
    settings.setValue('Interface/language', 'es')
    index = widget.button_input.findData('Right')
    assert widget.button_input.itemText(index) == 'Derecho'
    assert widget.modifier_inputs['Shift'].text() == 'Mayús'
    assert widget.button_label.text() == 'Botón del ratón:'


def test_zoom_inverted_widget_saves_value(settings):
    widget = TabletZoomInvertedWidget()
    widget.input.setChecked(True)
    assert settings.valueOrDefault('TabletMode/zoom_inverted') is True


def test_lock_corner_widget_updates_button_live(view, settings):
    widget = LockIconCornerWidget()
    assert widget.buttons['bottom_left'].isChecked()
    with_view_size = view.lock_button.y()
    widget.buttons['top_left'].setChecked(True)
    assert settings.valueOrDefault('LockIcon/corner') == 'top_left'
    assert view.lock_button.y() == 10
    assert with_view_size != 10


def test_lock_size_widget_updates_button_live(view):
    widget = LockIconSizeWidget()
    assert widget.input.suffix() == ' px'
    widget.input.setValue(48)
    assert view.lock_button.width() == 48


def test_lock_transparency_widget_updates_button_live(view):
    widget = LockIconTransparencyWidget()
    assert widget.input.suffix() == ' %'
    assert widget.input.value() == 30
    widget.input.setValue(50)
    assert view.lock_button.icon_opacity == pytest.approx(0.5)


def test_lock_transparency_widget_never_allows_invisible_icon():
    widget = LockIconTransparencyWidget()
    assert widget.input.maximum() < 100


def test_view_settings_changed_signal_on_lock_setting(settings, qtbot):
    with qtbot.waitSignal(settings_events.view_settings_changed):
        settings.setValue('LockIcon/size', 30)


# Menu

def test_actions_are_in_view_menu(view):
    view_menu = next(m for m in view.toplevel_menus
                     if m.title() == '&View')
    assert actions['tablet_mode'].qaction in view_menu.actions()
    assert actions['lock_items'].qaction in view_menu.actions()
