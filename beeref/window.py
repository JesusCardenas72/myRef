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

"""Helpers for the window modes: native Windows functions, system wide
shortcuts, the title bar shown on hover, resize borders of frameless
windows and the tray icon."""

from functools import partial
import logging
import sys

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref import constants
from beeref.assets import BeeAssets
from beeref.i18n import _


logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:  # pragma: no cover
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [
        wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.RegisterHotKey.argtypes = [
        wintypes.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]

    class WINDOWPOS(ctypes.Structure):
        _fields_ = [
            ('hwnd', wintypes.HWND),
            ('hwndInsertAfter', wintypes.HWND),
            ('x', ctypes.c_int),
            ('y', ctypes.c_int),
            ('cx', ctypes.c_int),
            ('cy', ctypes.c_int),
            ('flags', ctypes.c_uint),
        ]


GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_LAYERED = 0x80000
LWA_ALPHA = 0x2
WM_HOTKEY = 0x0312
WM_WINDOWPOSCHANGING = 0x0046
SWP_NOSIZE = 0x1
SWP_NOMOVE = 0x2
SWP_NOACTIVATE = 0x10
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
GA_ROOTOWNER = 3
MINIMIZED_POS = -32000

MOD_ALT = 0x1
MOD_CONTROL = 0x2
MOD_SHIFT = 0x4
MOD_WIN = 0x8
MOD_NOREPEAT = 0x4000

NATIVE_MODIFIERS = {
    Qt.KeyboardModifier.ControlModifier: MOD_CONTROL,
    Qt.KeyboardModifier.AltModifier: MOD_ALT,
    Qt.KeyboardModifier.ShiftModifier: MOD_SHIFT,
    Qt.KeyboardModifier.MetaModifier: MOD_WIN,
}

NATIVE_KEYS = {
    Qt.Key.Key_Left: 0x25,
    Qt.Key.Key_Up: 0x26,
    Qt.Key.Key_Right: 0x27,
    Qt.Key.Key_Down: 0x28,
    Qt.Key.Key_PageUp: 0x21,
    Qt.Key.Key_PageDown: 0x22,
    Qt.Key.Key_End: 0x23,
    Qt.Key.Key_Home: 0x24,
    Qt.Key.Key_Insert: 0x2D,
    Qt.Key.Key_Delete: 0x2E,
    Qt.Key.Key_Space: 0x20,
    Qt.Key.Key_Backspace: 0x08,
    Qt.Key.Key_Tab: 0x09,
    Qt.Key.Key_Return: 0x0D,
    Qt.Key.Key_Enter: 0x0D,
    Qt.Key.Key_Escape: 0x1B,
    Qt.Key.Key_Plus: 0xBB,
    Qt.Key.Key_Equal: 0xBB,
    Qt.Key.Key_Minus: 0xBD,
    Qt.Key.Key_Comma: 0xBC,
    Qt.Key.Key_Period: 0xBE,
}


def keysequence_to_native(shortcut):
    """Convert a shortcut like ``'Ctrl+Alt+T'`` to the modifiers and
    virtual key code expected by the Windows function ``RegisterHotKey``.

    Returns ``None`` if the shortcut can't be used as a global shortcut.
    """

    seq = QtGui.QKeySequence(shortcut)
    if seq.count() != 1:
        return None
    combo = seq[0]
    key = combo.key()
    code = key.value
    if (0x30 <= code <= 0x39) or (0x41 <= code <= 0x5A):
        vk = code
    elif Qt.Key.Key_F1.value <= code <= Qt.Key.Key_F24.value:
        vk = 0x70 + code - Qt.Key.Key_F1.value
    else:
        vk = NATIVE_KEYS.get(key)
    if vk is None:
        return None

    mods = 0
    for qt_mod, native_mod in NATIVE_MODIFIERS.items():
        if combo.keyboardModifiers() & qt_mod:
            mods |= native_mod
    return (mods, vk)


def native_message(message):  # pragma: no cover
    return wintypes.MSG.from_address(int(message))


class NativeEventFilter(QtCore.QAbstractNativeEventFilter):
    """Handles native Windows messages:

    * System wide shortcuts. They also work while another application
      has the focus or while the window ignores mouse and keyboard input
      (click-through).
    * Keeping a locked window from being moved via its title bar.

    Does nothing on other platforms.

    (Overriding ``nativeEvent`` of the main window instead crashes
    PyQt6.)
    """

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.registered = {}
        self.locked_hwnd = None
        self.installed = False

    @staticmethod
    def is_supported():
        return IS_WINDOWS

    def install(self):
        if not self.installed:
            QtCore.QCoreApplication.instance().installNativeEventFilter(self)
            self.installed = True

    def set_locked_window(self, hwnd):
        """Keep the window with the given handle from moving, or allow
        moving again if ``hwnd`` is ``None``."""
        self.locked_hwnd = hwnd
        if hwnd and self.is_supported():
            self.install()

    def register(self, bindings):
        """Register the given shortcuts.

        :param bindings: Dictionary of action ids to lists of shortcuts
        :returns: The shortcuts that couldn't be registered
        """

        self.unregister_all()
        if not bindings or not self.is_supported():
            return []
        self.install()

        failed = []
        hotkey_id = 1
        for action_id, shortcuts in bindings.items():
            for shortcut in shortcuts:
                native = keysequence_to_native(shortcut)
                if native and self._register_native(hotkey_id, *native):
                    logger.debug(f'Registered global shortcut {shortcut} '
                                 f'for {action_id}')
                    self.registered[hotkey_id] = action_id
                    hotkey_id += 1
                else:
                    logger.warning(
                        f'Could not register global shortcut {shortcut}')
                    failed.append(shortcut)
        return failed

    def _register_native(self, hotkey_id, mods, vk):  # pragma: no cover
        return bool(user32.RegisterHotKey(
            None, hotkey_id, mods | MOD_NOREPEAT, vk))

    def _unregister_native(self, hotkey_id):  # pragma: no cover
        user32.UnregisterHotKey(None, hotkey_id)

    def unregister_all(self):
        for hotkey_id in self.registered:
            self._unregister_native(hotkey_id)
        self.registered = {}

    def handle_hotkey(self, hotkey_id):
        action_id = self.registered.get(hotkey_id)
        if action_id:
            # Don't run the action inside the native event handler
            QtCore.QTimer.singleShot(0, partial(self.callback, action_id))
            return True
        return False

    def nativeEventFilter(self, event_type, message):  # pragma: no cover
        if not (self.registered or self.locked_hwnd):
            return False, 0
        if bytes(event_type) != b'windows_generic_MSG':
            return False, 0
        msg = native_message(message)
        if msg.message == WM_HOTKEY and self.handle_hotkey(msg.wParam):
            return True, 0
        if (msg.message == WM_WINDOWPOSCHANGING
                and self.locked_hwnd and msg.hWnd == self.locked_hwnd):
            block_window_move(msg)
        return False, 0


def set_click_through(widget, value, opacity):  # pragma: no cover
    """Make a window ignore mouse input natively on Windows. Qt's
    ``WindowTransparentForInput`` flag needs to recreate the window,
    which doesn't keep the layered window attributes."""

    hwnd = int(widget.winId())
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    if value:
        style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
    else:
        style &= ~WS_EX_TRANSPARENT
        if opacity >= 1:
            style &= ~WS_EX_LAYERED
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
    if style & WS_EX_LAYERED:
        user32.SetLayeredWindowAttributes(
            hwnd, 0, int(round(opacity * 255)), LWA_ALPHA)


def block_window_move(msg):  # pragma: no cover
    """Keep a window from being moved (e.g. by dragging the title bar)
    while still allowing to minimize and restore it."""

    pos = WINDOWPOS.from_address(msg.lParam)
    if user32.IsIconic(msg.hWnd) or pos.x == MINIMIZED_POS:
        return
    pos.flags |= SWP_NOMOVE | SWP_NOSIZE


def window_process_id(hwnd):  # pragma: no cover
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def list_app_windows(exclude_pid=None):  # pragma: no cover
    """Visible top level windows with a title, as (title, process id)."""

    windows = []

    def callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        pid = window_process_id(hwnd)
        if pid != exclude_pid:
            windows.append((buffer.value, pid))
        return True

    proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(callback)
    user32.EnumWindows(proc, 0)
    return windows


class AppOnTopTracker(QtCore.QObject):
    """Keeps the window on top of the windows of another application,
    but not on top of any other applications (Windows only).

    Instead of making the other application the owner of our window
    (which would destroy our window when the other application closes),
    we watch which application is in the foreground."""

    INTERVAL = 250

    def __init__(self, widget, pid, on_app_closed):
        super().__init__(widget)
        self.widget = widget
        self.pid = pid
        self.on_app_closed = on_app_closed
        self.on_top = None
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(self.INTERVAL)

    def stop(self):
        self.timer.stop()
        if self.on_top:
            self._set_topmost(False, None)
        self.on_top = None

    def check(self):  # pragma: no cover
        own_pid = window_process_id(int(self.widget.winId()))
        if not any(pid == self.pid for (title, pid) in list_app_windows()):
            logger.debug('Tracked application has been closed')
            self.stop()
            self.on_app_closed()
            return
        fg = user32.GetForegroundWindow()
        if not fg:
            return
        fg_pid = window_process_id(user32.GetAncestor(fg, GA_ROOTOWNER))
        want_on_top = fg_pid in (self.pid, own_pid)
        if want_on_top != self.on_top:
            self._set_topmost(want_on_top, fg)
            self.on_top = want_on_top

    def _set_topmost(self, value, foreground):  # pragma: no cover
        hwnd = int(self.widget.winId())
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        if value:
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        else:
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
            if foreground:
                # Put our window right behind the active window
                user32.SetWindowPos(hwnd, foreground, 0, 0, 0, 0, flags)


class HoverTitleBar(QtWidgets.QWidget):
    """A title bar for frameless windows which is shown while the mouse
    is near the top of the window."""

    HEIGHT = 28

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Window,
                         QtGui.QColor(*constants.COLORS['Active:Window']))
        self.setPalette(palette)
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        self.title = QtWidgets.QLabel()
        self.title.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.title, 100)
        self.buttons = {}
        for name, text, slot in (
                ('minimize', '–', self.main_window.showMinimized),
                ('maximize', '□', self.toggle_maximized),
                ('close', '✕', self.main_window.close)):
            btn = QtWidgets.QToolButton()
            btn.setText(text)
            btn.setAutoRaise(True)
            btn.setFixedSize(self.HEIGHT + 12, self.HEIGHT)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
            self.buttons[name] = btn
        self.hide()

    def toggle_maximized(self):
        if self.main_window.isMaximized():
            self.main_window.showNormal()
        else:
            self.main_window.showMaximized()

    def show_bar(self):
        if self.isVisible():
            return
        self.title.setText(self.main_window.windowTitle())
        self.update_position()
        self.show()
        self.raise_()

    def update_position(self):
        self.setGeometry(0, 0, self.main_window.width(), self.HEIGHT)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.main_window.windowHandle()
            if handle:
                handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.toggle_maximized()
        event.accept()


EDGE_CURSORS = {
    Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
    Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
    Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
    Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
    Qt.Edge.LeftEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.RightEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.RightEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeBDiagCursor,
    Qt.Edge.LeftEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeBDiagCursor,
}


class FrameController(QtCore.QObject):
    """Resize borders and the title bar on hover for frameless windows.

    Watches mouse movements over the widgets that cover the window."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.main_window = view.parent
        self.titlebar = HoverTitleBar(self.main_window)
        self.cursor_overridden = set()
        self.main_window.installEventFilter(self)
        for widget in self.watched_widgets():
            widget.installEventFilter(self)

    def watched_widgets(self):
        return (self.view.viewport(), self.view.welcome_overlay)

    def is_frameless(self):
        return bool(self.main_window.windowFlags()
                    & Qt.WindowType.FramelessWindowHint)

    def can_resize(self):
        return (self.is_frameless()
                and not self.view.window_locked
                and not self.main_window.isMaximized()
                and not self.main_window.isFullScreen())

    def edges_at(self, pos):
        """The window edges at the given position in window coordinates."""

        if not self.can_resize():
            return Qt.Edge(0)
        border = self.view.settings.valueOrDefault('Window/resize_border')
        edges = Qt.Edge(0)
        if pos.x() < border:
            edges |= Qt.Edge.LeftEdge
        if pos.x() >= self.main_window.width() - border:
            edges |= Qt.Edge.RightEdge
        if pos.y() < border:
            edges |= Qt.Edge.TopEdge
        if pos.y() >= self.main_window.height() - border:
            edges |= Qt.Edge.BottomEdge
        return edges

    def update_titlebar(self, pos):
        if not (self.view.titlebar_on_hover and self.is_frameless()):
            self.titlebar.hide()
            return
        if pos.y() < self.titlebar.HEIGHT:
            self.titlebar.show_bar()
        elif pos.y() > self.titlebar.HEIGHT + 20:
            self.titlebar.hide()

    def update_cursor(self, widget, edges):
        if edges and not self.view_is_busy():
            widget.setCursor(EDGE_CURSORS[edges])
            self.cursor_overridden.add(widget)
        elif widget in self.cursor_overridden:
            widget.unsetCursor()
            self.cursor_overridden.discard(widget)

    def view_is_busy(self):
        return bool(self.view.active_mode
                    or self.view.movewin_active
                    or self.view.welcome_overlay.movewin_active)

    def eventFilter(self, obj, event):
        etype = event.type()
        if obj is self.main_window:
            if etype == QtCore.QEvent.Type.Resize:
                self.titlebar.update_position()
            elif etype == QtCore.QEvent.Type.Leave:
                self.titlebar.hide()
            return False

        if etype == QtCore.QEvent.Type.Enter and self.is_frameless():
            # Mouse tracking may have been switched off by the move
            # window mode
            obj.setMouseTracking(True)
        elif (etype == QtCore.QEvent.Type.MouseMove
                and not event.buttons()):
            pos = self.main_window.mapFromGlobal(
                event.globalPosition().toPoint())
            self.update_titlebar(pos)
            self.update_cursor(obj, self.edges_at(pos))
        elif (etype == QtCore.QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and not self.view_is_busy()):
            pos = self.main_window.mapFromGlobal(
                event.globalPosition().toPoint())
            edges = self.edges_at(pos)
            handle = self.main_window.windowHandle()
            if edges and handle:
                handle.startSystemResize(edges)
                return True
        return False


class BeeTrayIcon(QtWidgets.QSystemTrayIcon):
    """Icon in the system tray. Needed to turn off click-through mode,
    since the window doesn't get any mouse clicks then."""

    def __init__(self, view):
        super().__init__(BeeAssets().logo, view)
        self.view = view
        self.menu = QtWidgets.QMenu()
        self.show_action = self.menu.addAction('')
        self.show_action.triggered.connect(self.toggle_window)
        for action_id in ('click_through', 'always_on_top'):
            self.menu.addAction(view.get_qaction(action_id))
        self.menu.addSeparator()
        self.menu.addAction(view.get_qaction('quit'))
        self.setContextMenu(self.menu)
        self.activated.connect(self.on_activated)
        self.retranslate()

    def retranslate(self):
        self.setToolTip(constants.APPNAME)
        self.show_action.setText(_('Show / Hide Window'))

    def toggle_window(self):
        window = self.view.parent
        if window.isVisible() and not window.isMinimized():
            window.hide()
        else:
            window.showNormal()
            window.raise_()
            window.activateWindow()
        self.view.update_tray_icon()

    def on_activated(self, reason):
        if reason != QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            return
        if self.view.click_through:
            self.view.get_qaction('click_through').setChecked(False)
        else:
            self.toggle_window()
