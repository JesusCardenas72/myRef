from unittest.mock import patch

from PyQt6 import QtWidgets

from beeref import i18n
from beeref.widgets.settings import (
    ArrangeGapWidget,
    ConfirmCloseUnsavedWidget,
    ImageStorageFormatWidget,
    LanguageWidget,
    SettingsDialog,
)


def test_language_widget_initialises_from_settings(settings, view):
    settings.setValue('Interface/language', 'es')
    widget = LanguageWidget()
    assert widget.buttons['es'].isChecked() is True
    assert widget.buttons['en'].isChecked() is False
    assert widget.buttons['system'].isChecked() is False


def test_language_widget_defaults_to_system(settings, view):
    widget = LanguageWidget()
    assert widget.buttons['system'].isChecked() is True
    assert widget.title() == 'Language:'


def test_language_widget_saves_and_applies_change(settings, view):
    widget = LanguageWidget()
    widget.buttons['es'].click()
    assert settings.value('Interface/language') == 'es'
    assert i18n.current_language() == 'es'
    assert widget.title() == 'Idioma: ✎'


def test_language_widget_language_names_are_not_translated(settings, view):
    widget = LanguageWidget()
    widget.buttons['es'].click()
    assert widget.buttons['en'].text() == 'English'
    assert widget.buttons['es'].text() == 'Español'
    assert (widget.buttons['system'].text()
            == 'Automático (idioma del sistema)')


def test_settings_dialog_retranslates_on_language_change(settings, view):
    dialog = SettingsDialog(view)
    assert dialog.windowTitle() == 'BeeRef Settings'
    assert dialog.tabs.tabText(0) == '&Miscellaneous'
    assert dialog.reset_btn.text() == '&Restore Defaults'

    settings.setValue('Interface/language', 'es')
    assert dialog.windowTitle() == 'Configuración de BeeRef'
    assert dialog.tabs.tabText(0) == '&Varios'
    assert dialog.tabs.tabText(1) == '&Imágenes y elementos'
    assert dialog.reset_btn.text() == 'Restablecer valores &predeterminados'


def test_group_widgets_retranslate_on_language_change(settings, view):
    format_widget = ImageStorageFormatWidget()
    confirm_widget = ConfirmCloseUnsavedWidget()
    gap_widget = ArrangeGapWidget()

    settings.setValue('Interface/language', 'es')

    assert format_widget.title() == 'Formato de almacenamiento de imágenes:'
    assert format_widget.buttons['best'].text() == 'Elección automática'
    assert 'se guardan' in format_widget.helptxt.text()
    assert confirm_widget.input.text() == 'Confirmar al cerrar'
    assert gap_widget.title() == 'Separación al organizar:'


def test_image_storage_format_sets_title_when_not_edited(settings, view):
    widget = ImageStorageFormatWidget()
    assert widget.title() == 'Image Storage Format:'


def test_image_storage_format_sets_title_when_edited(settings, view):
    settings.setValue('Items/image_storage_format', 'jpg')
    widget = ImageStorageFormatWidget()
    assert widget.title() == 'Image Storage Format: ✎'


def test_image_storage_format_selects_radiobox(settings, view):
    settings.setValue('Items/image_storage_format', 'jpg')
    widget = ImageStorageFormatWidget()
    assert widget.buttons['best'].isChecked() is False
    assert widget.buttons['png'].isChecked() is False
    assert widget.buttons['jpg'].isChecked() is True


def test_image_storage_format_saves_change(settings, view):
    settings.setValue('Items/image_storage_format', 'best')
    widget = ImageStorageFormatWidget()
    widget.set_value('jpg')
    assert widget.buttons['best'].isChecked() is False
    assert widget.buttons['png'].isChecked() is False
    assert widget.buttons['jpg'].isChecked() is True
    assert settings.valueOrDefault('Items/image_storage_format') == 'jpg'
    assert widget.title() == 'Image Storage Format: ✎'


def test_image_storage_format_on_restore_defaults(settings, view):
    widget = ImageStorageFormatWidget()
    widget.set_value('jpg')
    settings.setValue('Items/image_storage_format', 'best')
    widget.on_restore_defaults()
    assert widget.buttons['best'].isChecked() is True
    assert widget.buttons['png'].isChecked() is False
    assert widget.buttons['jpg'].isChecked() is False
    assert widget.title() == 'Image Storage Format:'


def test_arrange_gap_initialises_input_from_settings(settings, view):
    settings.setValue('Items/arrange_gap', 6)
    widget = ArrangeGapWidget()
    assert widget.input.value() == 6


def test_arrange_gap_sets_title_when_not_edited(settings, view):
    widget = ArrangeGapWidget()
    assert widget.title() == 'Arrange Gap:'


def test_arrange_gap_sets_title_when_edited(settings, view):
    settings.setValue('Items/arrange_gap', 6)
    widget = ArrangeGapWidget()
    assert widget.title() == 'Arrange Gap: ✎'


def test_arrange_gap_saves_change(settings, view):
    settings.setValue('Items/arrange_gap', 6)
    widget = ArrangeGapWidget()
    widget.set_value(8)
    assert settings.valueOrDefault('Items/arrange_gap') == 8
    assert widget.title() == 'Arrange Gap: ✎'


def test_arrange_gap_on_restore_defaults(settings, view):
    widget = ArrangeGapWidget()
    widget.set_value(7)
    settings.setValue('Items/arrange_gap', 0)
    widget.on_restore_defaults()
    assert widget.input.value() == 0
    assert widget.title() == 'Arrange Gap:'


def test_confirm_closed_initialises_input_from_settings(settings, view):
    settings.setValue('Save/confirm_close_unsaved', False)
    widget = ConfirmCloseUnsavedWidget()
    assert widget.input.isChecked() is False


def test_confirm_closed_sets_title_when_not_edited(settings, view):
    widget = ConfirmCloseUnsavedWidget()
    assert widget.title() == 'Confirm when closing an unsaved file:'


def test_confirm_closed_sets_title_when_edited(settings, view):
    settings.setValue('Save/confirm_close_unsaved', False)
    widget = ConfirmCloseUnsavedWidget()
    assert widget.title() == 'Confirm when closing an unsaved file: ✎'


def test_confirm_closed_saves_change(settings, view):
    settings.setValue('Save/confirm_close_unsaved', True)
    widget = ConfirmCloseUnsavedWidget()
    widget.set_value(False)
    assert settings.valueOrDefault('Save/confirm_close_unsaved') is False
    assert widget.title() == 'Confirm when closing an unsaved file: ✎'


def test_confirm_closed_on_restore_defaults(settings, view):
    widget = ConfirmCloseUnsavedWidget()
    widget.set_value(False)
    settings.setValue('Save/confirm_close_unsaved', True)
    widget.on_restore_defaults()
    assert widget.input.isChecked() is True
    assert widget.title() == 'Confirm when closing an unsaved file:'


@patch('PyQt6.QtWidgets.QMessageBox.question',
       return_value=QtWidgets.QMessageBox.StandardButton.Yes)
def test_settings_dialog_on_restore_defaults(msg_mock, settings, view):
    dialog = SettingsDialog(view)
    settings.setValue('Items/image_storage_format', 'jpg')
    settings.setValue('Items/arrange_gap', 10)
    settings.setValue('Save/confirm_close_unsaved', False)
    dialog.on_restore_defaults()
    msg_mock.assert_called_once()
    assert settings.valueOrDefault('Items/image_storage_format') == 'best'
    assert settings.valueOrDefault('Items/arrange_gap') == 0
    assert settings.valueOrDefault('Save/confirm_close_unsaved') is True


def test_undo_limit_widget_initialises_input_from_settings(settings, view):
    from beeref.widgets.settings import UndoLimitWidget
    settings.setValue('Performance/undo_limit', 300)
    widget = UndoLimitWidget()
    assert widget.input.value() == 300
    assert widget.input.minimum() == 1
    assert widget.input.maximum() == 1000


def test_undo_limit_widget_saves_value(settings, view):
    from beeref.widgets.settings import UndoLimitWidget
    widget = UndoLimitWidget()
    widget.input.setValue(42)
    assert settings.valueOrDefault('Performance/undo_limit') == 42
