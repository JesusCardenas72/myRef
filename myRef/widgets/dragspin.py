"""Spin boxes whose value can be changed by click-and-drag.

Dragging to the right increases the value, to the left decreases it.
One pixel moved equals one single step; the value left at release stays.
"""

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt


class _DragMixin:
    DRAG_THRESHOLD = 3

    def _init_drag(self):
        self._drag_start = None
        self._drag_value = None
        self._dragging = False
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.lineEdit():
            t = event.type()
            E = QtCore.QEvent.Type
            if (t == E.MouseButtonPress
                    and event.button() == Qt.MouseButton.LeftButton):
                self._drag_start = event.globalPosition().x()
                self._drag_value = self.value()
                self._dragging = False
            elif (t == E.MouseMove and self._drag_start is not None
                    and event.buttons() & Qt.MouseButton.LeftButton):
                dx = event.globalPosition().x() - self._drag_start
                if not self._dragging and abs(dx) >= self.DRAG_THRESHOLD:
                    self._dragging = True
                    self.lineEdit().setCursor(Qt.CursorShape.SizeHorCursor)
                if self._dragging:
                    self.setValue(self._drag_value + dx * self.singleStep())
                    return True
            elif (t == E.MouseButtonRelease
                    and event.button() == Qt.MouseButton.LeftButton
                    and self._drag_start is not None):
                was_dragging = self._dragging
                self._drag_start = None
                self._dragging = False
                self.lineEdit().unsetCursor()
                if was_dragging:
                    return True
            elif t == E.MouseButtonDblClick and self._dragging:
                return True
        return super().eventFilter(obj, event)


class DragSpinBox(_DragMixin, QtWidgets.QSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_drag()

    def setValue(self, value):
        super().setValue(int(round(value)))


class DragDoubleSpinBox(_DragMixin, QtWidgets.QDoubleSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_drag()
