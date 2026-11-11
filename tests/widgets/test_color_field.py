from unittest.mock import MagicMock, patch

from PyQt6 import QtGui

from myRef.widgets.color_field import (
    ColorField,
    alpha_to_transparency,
    transparency_to_alpha,
)


def test_transparency_conversion():
    assert alpha_to_transparency(255) == 0
    assert alpha_to_transparency(0) == 100
    assert transparency_to_alpha(0) == 255
    assert transparency_to_alpha(100) == 0
    assert transparency_to_alpha(50) == 128


def test_color_field_shows_transparency(qtbot):
    field = ColorField(QtGui.QColor('#40ff0000'), 'Title')
    qtbot.addWidget(field)
    assert field.transparency_input.value() == 75


def test_color_field_transparency_changes_alpha(qtbot):
    field = ColorField(QtGui.QColor('#ffff0000'), 'Title')
    qtbot.addWidget(field)
    field.callback = MagicMock()
    field.set_transparency(50)
    assert field.color.alpha() == 128
    assert field.color.red() == 255
    field.callback.assert_called_once_with('#80ff0000')


def test_color_field_set_color_updates_transparency(qtbot):
    field = ColorField(QtGui.QColor('#ffff0000'), 'Title')
    qtbot.addWidget(field)
    field.callback = MagicMock()
    field.set_color(QtGui.QColor('#00ff0000'))
    assert field.transparency_input.value() == 100
    field.callback.assert_called_once_with('#00ff0000')


def test_color_field_choose_color(qtbot):
    field = ColorField(QtGui.QColor('#ffff0000'), 'Title')
    qtbot.addWidget(field)
    with patch('PyQt6.QtWidgets.QColorDialog.getColor',
               return_value=QtGui.QColor(0, 255, 0, 51)):
        field.button.click()
    assert field.color == QtGui.QColor(0, 255, 0, 51)
    assert field.transparency_input.value() == 80


def test_color_field_cancelled_dialog_keeps_color(qtbot):
    field = ColorField(QtGui.QColor('#ffff0000'), 'Title')
    qtbot.addWidget(field)
    with patch('PyQt6.QtWidgets.QColorDialog.getColor',
               return_value=QtGui.QColor()):
        field.choose_color()
    assert field.color == QtGui.QColor('#ffff0000')
