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

"""Buttons that stay on top of the view: The padlock for locking the
images and the tablet mode button in the title bar.
"""

import ctypes
import ctypes.wintypes
import logging

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref.config import BeeSettings, settings_events
from beeref.constants import COLORS
from beeref.i18n import _


logger = logging.getLogger(__name__)


class LockButton(QtWidgets.QAbstractButton):
    """A padlock in one of the corners of the view.

    Its position, size and transparency are configurable.
    """

    MARGIN = 10  # Distance from the edges of the view
    # The size the padlock is designed in. It's large because Qt approximates
    # curves with straight lines, which would show up at a small scale.
    ICON_SIZE = 1000
    BACKDROP_COLOR = QtGui.QColor(0, 0, 0, 130)
    LOCKED_COLOR = QtGui.QColor(*COLORS['Scene:Selection'])
    UNLOCKED_COLOR = QtGui.QColor(230, 230, 230)

    def __init__(self, parent):
        super().__init__(parent)
        self.settings = BeeSettings()
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(self.update_tooltip)
        settings_events.language_changed.connect(self.update_tooltip)
        self.update_tooltip()
        self.apply_settings()

    @property
    def icon_opacity(self):
        transparency = self.settings.valueOrDefault('LockIcon/transparency')
        return 1 - transparency / 100

    def apply_settings(self):
        size = self.settings.valueOrDefault('LockIcon/size')
        self.setFixedSize(size, size)
        self.update_position()
        self.update()

    def update_position(self):
        """Moves the button into its corner of the view's visible area."""

        area = self.parent().viewport().geometry()
        corner = self.settings.valueOrDefault('LockIcon/corner')
        if corner.endswith('left'):
            x = area.left() + self.MARGIN
        else:
            x = area.left() + area.width() - self.width() - self.MARGIN
        if corner.startswith('top'):
            y = area.top() + self.MARGIN
        else:
            y = area.top() + area.height() - self.height() - self.MARGIN
        self.move(x, y)

    def update_tooltip(self, *args, **kwargs):
        if self.isChecked():
            self.setToolTip(_('Images are locked. Click to unlock.'))
        else:
            self.setToolTip(_('Images are unlocked. Click to lock.'))

    def shackle_path(self):
        """The bow of the padlock in icon coordinates (see ``ICON_SIZE``).

        When open, it's lifted out of the padlock's body on one side.
        """

        path = QtGui.QPainterPath()
        if self.isChecked():
            path.moveTo(340, 500)
            path.arcTo(QtCore.QRectF(340, 180, 320, 320), 180, -180)
            path.lineTo(660, 500)
        else:
            path.moveTo(340, 500)
            path.lineTo(340, 300)
            path.arcTo(QtCore.QRectF(340, 140, 320, 320), 180, -180)
            path.lineTo(660, 360)
        return path

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.icon_opacity)
        size = self.width()

        # The backdrop keeps the icon visible on top of any kind of image
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.BACKDROP_COLOR)
        painter.drawRoundedRect(self.rect(), 0.2 * size, 0.2 * size)

        # Merged into one shape since overlapping parts would show through
        # when the icon is transparent
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(80)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        body = QtGui.QPainterPath()
        body.addRoundedRect(QtCore.QRectF(240, 460, 520, 380), 60, 60)
        padlock = stroker.createStroke(self.shackle_path()).united(body)

        painter.scale(size / self.ICON_SIZE, size / self.ICON_SIZE)
        painter.setBrush(
            self.LOCKED_COLOR if self.isChecked() else self.UNLOCKED_COLOR)
        painter.drawPath(padlock)


class TitleBarButton(QtWidgets.QAbstractButton):
    """The button for turning tablet mode on and off.

    The title bar is drawn by the operating system, so it can't contain
    any Qt widgets. This button is a separate small window instead, which
    floats over the title bar right next to the system's window
    buttons. The operating system keeps it directly above the main
    window since the main window owns it, and this class takes care of
    following the main window around.

    This relies on being able to place windows freely and to ask for the
    position of the window buttons, so it's only available on Windows.
    """

    DWMWA_CAPTION_BUTTON_BOUNDS = 5
    DEFAULT_CAPTION_WIDTH = 138  # If the system won't give us the real one
    MIN_CAPTION_HEIGHT = 20
    GAP = 6  # Distance from the system's window buttons
    MIN_MARGIN = 1  # Distance from the top and bottom of the title bar
    MAX_HEIGHT = 22
    HIGHLIGHT_COLOR = QtGui.QColor(*COLORS['Active:Highlight'])
    # Fully transparent parts of a window don't receive any mouse events
    HIT_AREA_COLOR = QtGui.QColor(128, 128, 128, 1)
    WATCHED_EVENTS = (QtCore.QEvent.Type.Move,
                      QtCore.QEvent.Type.Resize,
                      QtCore.QEvent.Type.Show,
                      QtCore.QEvent.Type.Hide,
                      QtCore.QEvent.Type.WindowStateChange)

    @staticmethod
    def is_supported():
        return QtGui.QGuiApplication.platformName() == 'windows'

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowFlags(Qt.WindowType.Tool
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.NoDropShadowWindowHint
                            | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCheckable(True)
        settings_events.language_changed.connect(self.retranslate)
        self.retranslate()
        main_window.installEventFilter(self)
        self.follow_main_window()

    def retranslate(self):
        self.setToolTip(_('Tablet Mode'))

    def dispose(self):
        """Removes the button for good."""

        self.main_window.removeEventFilter(self)
        self.hide()
        self.deleteLater()

    def eventFilter(self, obj, event):
        if event.type() in self.WATCHED_EVENTS:
            self.follow_main_window()
        return False

    def should_be_visible(self):
        """Whether the main window currently shows a title bar."""

        return (self.main_window.isVisible()
                and not self.main_window.isMinimized()
                and not self.main_window.isFullScreen()
                and not (self.main_window.windowFlags()
                         & Qt.WindowType.FramelessWindowHint))

    def follow_main_window(self):
        if self.should_be_visible():
            self.setGeometry(self.calculate_geometry())
            self.show()
        else:
            self.hide()

    def get_caption_buttons_bounds(self):  # pragma: no cover
        """The system's window buttons relative to the main window's frame.

        :returns: Bounds in device pixels as ``ctypes.wintypes.RECT`` or
            ``None`` if not available.
        """

        rect = ctypes.wintypes.RECT()
        try:
            result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
                ctypes.wintypes.HWND(int(self.main_window.winId())),
                self.DWMWA_CAPTION_BUTTON_BOUNDS,
                ctypes.byref(rect),
                ctypes.sizeof(rect))
        except (AttributeError, OSError):
            logger.exception('Could not get position of window buttons')
            return None
        return rect if result == 0 and rect.right > rect.left else None

    def get_caption_rect(self):
        """The area of the system's window buttons in global coordinates."""

        frame = self.main_window.frameGeometry()
        bounds = self.get_caption_buttons_bounds()
        if bounds:
            ratio = self.main_window.devicePixelRatioF()
            return QtCore.QRectF(
                frame.x() + bounds.left / ratio,
                frame.y() + bounds.top / ratio,
                (bounds.right - bounds.left) / ratio,
                (bounds.bottom - bounds.top) / ratio)

        title_height = self.main_window.geometry().y() - frame.y()
        return QtCore.QRectF(
            frame.x() + frame.width() - self.DEFAULT_CAPTION_WIDTH,
            frame.y(),
            self.DEFAULT_CAPTION_WIDTH,
            max(title_height, self.MIN_CAPTION_HEIGHT))

    def calculate_geometry(self):
        caption = self.get_caption_rect()
        # The frame of a maximized window extends beyond the screen
        screen = self.main_window.screen().availableGeometry()
        caption.setTop(max(caption.top(), screen.y()))

        height = min(round(caption.height()) - 2 * self.MIN_MARGIN,
                     self.MAX_HEIGHT)
        width = round(height * 1.3)
        return QtCore.QRect(
            round(caption.left()) - width - self.GAP,
            round(caption.center().y() - height / 2),
            width,
            height)

    def get_icon_color(self):
        scheme = QtGui.QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return QtGui.QColor(240, 240, 240)
        return QtGui.QColor(30, 30, 30)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect())
        painter.fillRect(rect, self.HIT_AREA_COLOR)

        color = self.get_icon_color()
        background = None
        if self.isChecked():
            background = self.HIGHLIGHT_COLOR
            color = QtGui.QColor(255, 255, 255)
        elif self.isDown() or self.underMouse():
            background = QtGui.QColor(color)
            background.setAlpha(70 if self.isDown() else 35)
        if background:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(rect, 4, 4)

        # A tablet standing upright
        height = 0.7 * rect.height()
        width = 0.74 * height
        tablet = QtCore.QRectF(0, 0, width, height)
        tablet.moveCenter(rect.center())
        pen = QtGui.QPen(color, 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(tablet, 2, 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(
            QtCore.QPointF(tablet.center().x(), tablet.bottom() - 2.6),
            0.9, 0.9)
