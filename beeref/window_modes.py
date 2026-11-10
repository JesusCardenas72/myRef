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

"""Window modes of the main window: opacity, click-through, always on
top/bottom, locking, resizing to the selection etc."""

import logging

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from beeref.actions.actions import actions
from beeref.i18n import _
from beeref import widgets
from beeref import window


logger = logging.getLogger(__name__)


# Actions whose shortcuts can work system wide
GLOBAL_HOTKEY_ACTIONS = (
    'click_through',
    'always_on_top',
    'always_on_bottom',
    'opacity_increase',
    'opacity_decrease',
    'opacity_reset',
    'lock_window',
)

# Window modes that are restored on startup if the startup mode is "last"
REMEMBERED_MODES = ('always_on_top', 'always_on_bottom', 'click_through')

QWIDGETSIZE_MAX = 16777215
OPACITY_STEP = 10
OPACITY_MIN = 10


class WindowModesMixin:

    def init_window_mode_state(self):
        """Called before the actions are created, since their callbacks
        may run while they are created."""
        self.window_locked = False
        self.click_through = False
        self.titlebar_on_hover = False
        self.normal_geometry = None
        self.app_on_top = None
        self.tray_icon = None
        self.scale_on_resize_paused = False
        self.notify_window_modes = False
        self.window_mode_notice = None
        self.native_filter = window.NativeEventFilter(self.on_global_hotkey)

    def init_window_modes(self):
        self.frame_controller = window.FrameController(self)
        self.apply_window_opacity()
        self.register_global_hotkeys()
        self.update_tray_icon()

    def get_qaction(self, action_id):
        return actions[action_id].qaction

    def set_checked_silently(self, action_id, value):
        """Check/uncheck an action without running its callback."""
        qaction = self.get_qaction(action_id)
        blocked = qaction.blockSignals(True)
        qaction.setChecked(value)
        qaction.blockSignals(blocked)

    def notify_window_mode(self, msg):
        if (self.notify_window_modes
                and self.settings.valueOrDefault('Window/notify_mode_change')):
            # A new notice replaces the previous one instead of being
            # drawn on top of it
            if self.window_mode_notice:
                try:
                    self.window_mode_notice.deleteLater()
                except RuntimeError:
                    pass  # Already deleted by its timer
            self.window_mode_notice = widgets.BeeNotification(self, msg)

    def remember_window_mode(self, mode, value):
        if mode in REMEMBERED_MODES:
            self.settings.setValue(f'Window/last_{mode}', value)

    def recreate_window(self, flags):
        """Set window flags. The native window has to be recreated for
        them to take effect."""

        for flag, value in flags.items():
            self.parent.setWindowFlag(flag, on=value)
        self.parent.destroy()
        self.parent.create()
        self.parent.show()
        self.rebuild_titlebar_button()
        self.reapply_native_window_modes()

    def reapply_native_window_modes(self):
        """Native modes that are lost when the window is recreated."""
        if self.click_through and window.IS_WINDOWS:
            window.set_click_through(
                self.parent, True, self.parent.windowOpacity())
        self.update_locked_native_window()

    def update_locked_native_window(self):
        self.native_filter.set_locked_window(
            int(self.parent.winId()) if self.window_locked else None)

    # Startup

    def apply_startup_window_mode(self):
        """Called once the main window is shown."""

        mode = self.settings.valueOrDefault('Window/startup_mode')
        logger.debug(f'Startup window mode: {mode}')
        states = {}
        if mode == 'last':
            for name in REMEMBERED_MODES:
                states[name] = self.settings.value(
                    f'Window/last_{name}', False, type=bool)
        elif mode == 'always_on_top':
            states['always_on_top'] = True
        elif mode == 'click_through':
            states['always_on_top'] = True
            states['click_through'] = True
        for name, value in states.items():
            if value:
                self.get_qaction(name).setChecked(True)
        if self.settings.value('Window/titlebar_on_hover', False, type=bool):
            self.get_qaction('titlebar_on_hover').setChecked(True)
        self.notify_window_modes = True

    # Opacity

    def window_opacity_percent(self):
        return self.settings.valueOrDefault('Window/opacity')

    def apply_window_opacity(self):
        opacity = self.window_opacity_percent() / 100
        self.parent.setWindowOpacity(opacity)
        if self.click_through and window.IS_WINDOWS:
            window.set_click_through(self.parent, True, opacity)

    def set_window_opacity(self, percent):
        percent = max(OPACITY_MIN, min(100, percent))
        self.settings.setValue('Window/opacity', percent)
        self.apply_window_opacity()
        self.notify_window_mode(
            _('Opacity: {percent} %').format(percent=percent))

    def on_action_opacity_increase(self):
        self.set_window_opacity(self.window_opacity_percent() + OPACITY_STEP)

    def on_action_opacity_decrease(self):
        self.set_window_opacity(self.window_opacity_percent() - OPACITY_STEP)

    def on_action_opacity_reset(self):
        self.set_window_opacity(100)

    # Stacking order

    def on_action_always_on_bottom(self, checked):
        flags = {Qt.WindowType.WindowStaysOnBottomHint: checked}
        if checked:
            flags[Qt.WindowType.WindowStaysOnTopHint] = False
            self.set_checked_silently('always_on_top', False)
            self.remember_window_mode('always_on_top', False)
            self.stop_app_on_top()
        self.recreate_window(flags)
        self.remember_window_mode('always_on_bottom', checked)
        self.notify_window_mode(
            _('Always on bottom') if checked else _('Normal window'))

    def on_action_always_on_top_of_app(self):
        if not window.IS_WINDOWS:
            widgets.BeeNotification(
                self, _('This is only available on Windows'))
            return
        own_pid = QtCore.QCoreApplication.applicationPid()
        apps = {}
        for title, pid in window.list_app_windows(exclude_pid=own_pid):
            apps.setdefault(title, pid)
        none_label = _('(None)')
        titles = [none_label] + sorted(apps, key=str.lower)
        title, ok = QtWidgets.QInputDialog.getItem(
            self, _('Always On Top of Application'),
            _('Keep the window on top of this application:'),
            titles, 0, False)
        if not ok:
            return
        if title == none_label:
            self.stop_app_on_top()
            self.notify_window_mode(_('Normal window'))
            return
        self.start_app_on_top(apps[title], title)

    def start_app_on_top(self, pid, title):
        self.stop_app_on_top()
        for action_id in ('always_on_top', 'always_on_bottom'):
            if self.get_qaction(action_id).isChecked():
                self.get_qaction(action_id).setChecked(False)
        logger.debug(f'Keeping window on top of {title} ({pid})')
        self.app_on_top = window.AppOnTopTracker(
            self.parent, pid, self.on_app_on_top_closed)
        self.notify_window_mode(
            _('Always on top of: {app}').format(app=title))

    def stop_app_on_top(self):
        if self.app_on_top:
            self.app_on_top.stop()
            self.app_on_top.deleteLater()
            self.app_on_top = None

    def on_app_on_top_closed(self):
        self.app_on_top = None
        self.notify_window_mode(_('Normal window'))

    # Click-through

    def on_action_click_through(self, checked):
        self.click_through = checked
        if window.IS_WINDOWS:
            window.set_click_through(
                self.parent, checked, self.parent.windowOpacity())
        else:
            self.recreate_window(
                {Qt.WindowType.WindowTransparentForInput: checked})
        self.remember_window_mode('click_through', checked)
        self.update_tray_icon()
        if checked:
            msg = _('Click-through on. Use the tray icon to turn it off')
            if self.native_filter.registered:
                msg = _('Click-through on. Use the tray icon or a global '
                        'shortcut to turn it off')
            self.notify_window_mode(msg)
        else:
            self.notify_window_mode(_('Click-through off'))

    # Locking and size

    def on_action_lock_window(self, checked):
        self.window_locked = checked
        self.apply_window_size_constraints()
        self.update_locked_native_window()
        self.notify_window_mode(
            _('Window locked') if checked else _('Window unlocked'))

    def is_window_size_locked(self):
        return self.window_locked or (
            self.get_qaction('maximize_window').isChecked()
            and self.settings.valueOrDefault('Window/lock_when_maximized'))

    def apply_window_size_constraints(self):
        if self.is_window_size_locked():
            self.parent.setFixedSize(self.parent.size())
        else:
            self.unlock_window_size()

    def notify_window_locked(self):
        widgets.BeeNotification(self, _('The window is locked'))

    def client_geometry_for(self, outer):
        """The geometry to set to make the window including its frame
        cover the given rect."""

        frame = self.parent.frameGeometry()
        geom = self.parent.geometry()
        return outer.adjusted(
            geom.left() - frame.left(),
            geom.top() - frame.top(),
            geom.right() - frame.right(),
            geom.bottom() - frame.bottom())

    def on_action_maximize_window(self, checked):
        if self.window_locked:
            self.set_checked_silently('maximize_window', not checked)
            self.notify_window_locked()
            return
        if checked:
            self.normal_geometry = self.parent.geometry()
            screen = self.parent.screen()
            if self.settings.valueOrDefault('Window/maximize_over_taskbar'):
                rect = screen.geometry()
            else:
                rect = screen.availableGeometry()
            if self.parent.isFullScreen() or self.parent.isMaximized():
                self.parent.showNormal()
            self.unlock_window_size()
            self.parent.setGeometry(self.client_geometry_for(rect))
        else:
            self.unlock_window_size()
            if self.normal_geometry:
                self.parent.setGeometry(self.normal_geometry)
            self.normal_geometry = None
        self.apply_window_size_constraints()

    def unlock_window_size(self):
        self.parent.setMinimumSize(0, 0)
        self.parent.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)

    def on_action_fit_window_to_selection(self):
        if self.is_window_size_locked():
            self.notify_window_locked()
            return
        selection_only = bool(self.scene.selectedItems(user_only=True))
        rect = self.scene.itemsBoundingRect(selection_only=selection_only)
        if rect.isEmpty():
            return

        if self.parent.isFullScreen() or self.parent.isMaximized():
            self.parent.showNormal()
            self.set_checked_silently('fullscreen', False)
        if self.get_qaction('maximize_window').isChecked():
            self.set_checked_silently('maximize_window', False)
            self.normal_geometry = None

        # The items should stay where they are on screen
        view_rect = self.mapFromScene(rect).boundingRect()
        top_left = self.viewport().mapToGlobal(view_rect.topLeft())
        offset = self.viewport().mapTo(self.parent, QtCore.QPoint(0, 0))
        chrome = self.parent.size() - self.viewport().size()
        size = view_rect.size() + chrome
        available = self.parent.screen().availableGeometry()
        size = size.boundedTo(available.size())
        size = size.expandedTo(QtCore.QSize(100, 100))
        geom = QtCore.QRect(top_left - offset, size)
        # Keep the window on screen
        geom.moveLeft(max(available.left(),
                          min(geom.left(), available.right() - size.width())))
        geom.moveTop(max(available.top(),
                         min(geom.top(), available.bottom() - size.height())))
        logger.debug(f'Fit window to {rect}: {geom}')
        self.scale_on_resize_paused = True
        self.parent.setGeometry(geom)
        QtCore.QTimer.singleShot(
            50, lambda: self.finish_fit_window_to_selection(rect))

    def finish_fit_window_to_selection(self, rect):
        self.fit_rect(rect)
        self.scale_on_resize_paused = False

    # Title bar and frame

    def on_action_titlebar_on_hover(self, checked):
        self.titlebar_on_hover = checked
        self.settings.setValue('Window/titlebar_on_hover', checked)
        if checked:
            if self.get_qaction('show_titlebar').isChecked():
                # Triggers on_action_show_titlebar
                self.get_qaction('show_titlebar').setChecked(False)
        else:
            self.frame_controller.titlebar.hide()

    # Scaling the scene on resize

    def scale_scene_on_resize(self, old_size, new_size, old_center):
        if (self.scale_on_resize_paused
                or not self.settings.valueOrDefault('Window/scale_on_resize')
                or not self.scene.items()
                or old_size.width() <= 0 or old_size.height() <= 0):
            return
        factor = min(new_size.width() / old_size.width(),
                     new_size.height() / old_size.height())
        if factor <= 0 or abs(factor - 1) < 0.001:
            return
        self.scale(factor, factor)
        self.centerOn(old_center)

    # Tray icon and global shortcuts

    def update_tray_icon(self):
        wanted = (self.click_through
                  or not self.parent.isVisible() and self.tray_icon
                  or self.settings.valueOrDefault('Window/tray_icon'))
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            wanted = False
        if wanted and not self.tray_icon:
            self.tray_icon = window.BeeTrayIcon(self)
        if self.tray_icon:
            self.tray_icon.setVisible(bool(wanted))

    def global_hotkey_bindings(self):
        if not self.settings.valueOrDefault('Window/global_hotkeys'):
            return {}
        bindings = {}
        for action_id in GLOBAL_HOTKEY_ACTIONS:
            shortcuts = actions[action_id].get_shortcuts()
            if shortcuts:
                bindings[action_id] = shortcuts
        return bindings

    def register_global_hotkeys(self):
        failed = self.native_filter.register(self.global_hotkey_bindings())
        if failed:
            widgets.BeeNotification(
                self,
                _('Could not use these shortcuts system wide: {keys}').format(
                    keys=', '.join(failed)))

    def on_global_hotkey(self, action_id):
        logger.debug(f'Global shortcut for {action_id}')
        self.get_qaction(action_id).trigger()

    def on_window_settings_changed(self):
        self.apply_window_opacity()
        self.update_tray_icon()
        self.register_global_hotkeys()
        self.apply_window_size_constraints()

    def close_window_modes(self):
        self.native_filter.unregister_all()
        self.stop_app_on_top()
        if self.tray_icon:
            self.tray_icon.hide()
