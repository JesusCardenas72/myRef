import ast
from collections import Counter
from pathlib import Path
import re
from string import Formatter
from unittest.mock import patch

from PyQt6 import QtCore, QtGui, QtWidgets
import pytest

import myRef
from myRef import constants, i18n
from myRef.actions.actions import actions, CONTEXT_LABELS
from myRef.actions.menu_structure import menu_structure
from myRef.config import KeyboardSettings
from myRef.config.controls import MouseConfigBase
from myRef.config.settings import MOUSE_BINDING_BUTTONS
from myRef.fileio.errors import IMG_LOADING_ERROR_MSG
from myRef.i18n import _, es
from myRef.widgets import settings as settings_widgets
from myRef.widgets.controls.common import MouseControlsModelBase
from myRef.widgets.controls.keyboard import KeyboardShortcutsModel


# conftest.py patches this during tests, so keep the original
real_detect_system_language = i18n.detect_system_language


def strings_in_function_calls():
    """All strings in the code that are directly passed to ``_()``."""
    strings = set()
    for path in Path(myRef.__file__).parent.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == '_'
                    and node.args
                    and isinstance(node.args[0], ast.Constant)):
                strings.add(node.args[0].value)
    return strings


def menu_titles(items):
    for item in items:
        if isinstance(item, dict):
            yield item['menu']
            if isinstance(item['items'], list):
                yield from menu_titles(item['items'])


def strings_in_definitions():
    """All strings defined somewhere else and translated when displayed."""
    strings = set(menu_titles(menu_structure))
    strings.update(action.text for action in actions.values())
    strings.update(f'File {i}' for i in range(1, 11))

    for action_list in (KeyboardSettings.MOUSE_ACTIONS,
                        KeyboardSettings.MOUSEWHEEL_ACTIONS):
        strings.update(action.text for action in action_list.values())
    strings.update(label for label in CONTEXT_LABELS.values() if label)
    strings.update(MouseConfigBase.MODIFIER_MAP)
    strings.update(MouseConfigBase.BUTTON_MAP)
    strings.update(MOUSE_BINDING_BUTTONS)

    # All concrete settings widgets (those that edit a settings key):
    groups = [
        cls for cls in vars(settings_widgets).values()
        if isinstance(cls, type)
        and issubclass(cls, settings_widgets.GroupBase)
        and getattr(cls, 'KEY', None)]
    assert groups
    for group in groups:
        strings.update((group.TITLE, group.HELPTEXT))
        strings.add(getattr(group, 'LABEL', None))
        strings.add(getattr(group, 'PLACEHOLDER', None))
        for (value, label, helptext) in getattr(group, 'OPTIONS', ()):
            strings.update((label, helptext))

    strings.update(MouseControlsModelBase.HEADERS.values())
    strings.update(KeyboardShortcutsModel.HEADER)
    strings.update((
        IMG_LOADING_ERROR_MSG,
        constants.APPNAME_FULL,
        'Skip this file',
        'Skip all existing files',
        'Overwrite this file',
        'Overwrite all existing files',
        'Mouse Controls for:',
        'MouseWheel Controls for:',
        'No image data or text in clipboard or image too big',
        'Attempted drop not an image or image too big',
        '<p>Paste or drop images here.</p>'
        '<p>Right-click for more options.</p>',
    ))

    strings -= {None, '', constants.CHANGED_SYMBOL}
    strings -= set(i18n.LANGUAGES.values())
    return strings


def test_translation_exists_for_all_strings():
    expected = strings_in_function_calls() | strings_in_definitions()
    missing = expected - set(es.TRANSLATIONS)
    assert not missing


def test_no_unused_translations():
    expected = strings_in_function_calls() | strings_in_definitions()
    unused = set(es.TRANSLATIONS) - expected
    assert not unused


@pytest.mark.parametrize('source,translation', es.TRANSLATIONS.items())
def test_translation_keeps_placeholders(source, translation):
    def fields(text):
        return sorted(f[1] for f in Formatter().parse(text) if f[1])

    assert fields(source) == fields(translation)
    assert source.count('%s') == translation.count('%s')
    assert re.findall('<[^>]+>', source) == re.findall('<[^>]+>', translation)


def test_menu_entries_with_mnemonic_keep_it_in_translation():
    texts = set(menu_titles(menu_structure))
    texts.update(action.text for action in actions.values())
    for text in texts:
        if re.search('&(?!&)', text):
            assert re.search('&(?!&)', es.TRANSLATIONS[text]), text


def mnemonics_per_menu(items):
    mnemonics = []
    for item in items:
        text = None
        if isinstance(item, dict):
            yield from mnemonics_per_menu(
                item['items'] if isinstance(item['items'], list) else [])
            text = item['menu']
        elif isinstance(item, str):
            text = actions[item].text
        match = re.search('&(?!&)(.)', _(text)) if text else None
        if match:
            mnemonics.append(match.group(1).lower())
    yield mnemonics


def test_mnemonics_unique_within_each_menu():
    i18n.set_language('es')
    for mnemonics in mnemonics_per_menu(menu_structure):
        duplicates = [k for k, v in Counter(mnemonics).items() if v > 1]
        assert not duplicates, mnemonics


def test_gettext_returns_source_for_english():
    assert _('&File') == '&File'


def test_gettext_returns_translation_for_spanish():
    i18n.set_language('es')
    assert i18n.current_language() == 'es'
    assert _('&File') == '&Archivo'


def test_gettext_returns_source_when_translation_missing():
    i18n.set_language('es')
    assert _('Some unknown string') == 'Some unknown string'


def test_set_language_falls_back_to_default_on_unknown_language():
    i18n.set_language('es')
    i18n.set_language('xx')
    assert i18n.current_language() == 'en'


def test_set_language_system_uses_detected_language():
    with patch('myRef.i18n.detect_system_language', return_value='es'):
        i18n.set_language('system')
    assert i18n.current_language() == 'es'


@pytest.mark.parametrize('languages,expected',
                         [(['es-MX', 'en-US'], 'es'),
                          (['es_ES'], 'es'),
                          (['en-GB', 'es-ES'], 'en'),
                          (['fr-FR', 'es-ES'], 'es'),
                          (['fr-FR'], 'en'),
                          ([], 'en')])
def test_detect_system_language(languages, expected):
    with patch('PyQt6.QtCore.QLocale.system') as system_mock:
        system_mock.return_value.uiLanguages.return_value = languages
        assert real_detect_system_language() == expected


def test_set_language_translates_qt_strings(qapp):
    i18n.set_language('es')
    assert QtCore.QCoreApplication.translate(
        'QPlatformTheme', 'Close') == 'Cerrar'
    i18n.set_language('en')
    assert QtCore.QCoreApplication.translate(
        'QPlatformTheme', 'Close') == 'Close'


def test_shortcuts_stay_portable_with_spanish_qt_translation(qapp):
    i18n.set_language('es')
    for action in actions.values():
        for shortcut in action.shortcuts:
            assert QtGui.QKeySequence(shortcut).toString() == shortcut


def test_spanish_controls_documentation_exists():
    docs = Path(myRef.__file__).parent / 'documentation'
    original = (docs / 'controls.html').read_text(encoding='utf-8')
    translated = (docs / 'controls.es.html').read_text(encoding='utf-8')
    assert translated.count('<h4>') == original.count('<h4>')
    assert 'Desplazar el lienzo' in translated


def test_help_dialog_shows_controls_in_current_language(view):
    from myRef.widgets import HelpDialog

    def shown_text(dialog):
        return dialog.findChild(QtWidgets.QScrollArea).widget().text()

    assert 'Pan Canvas' in shown_text(HelpDialog(view))
    i18n.set_language('es')
    assert 'Desplazar el lienzo' in shown_text(HelpDialog(view))


def test_language_setting_defaults_to_system(settings):
    assert settings.valueOrDefault('Interface/language') == 'system'


def test_language_setting_ignores_invalid_value(settings):
    QtCore.QSettings.setValue(settings, 'Interface/language', 'xx')
    assert settings.valueOrDefault('Interface/language') == 'system'


def test_changing_setting_applies_language_and_emits_signal(settings, qtbot):
    from myRef.config import settings_events
    with qtbot.waitSignal(settings_events.language_changed):
        settings.setValue('Interface/language', 'es')
    assert i18n.current_language() == 'es'


def test_restore_defaults_resets_language(settings):
    settings.setValue('Interface/language', 'es')
    settings.restore_defaults()
    assert settings.value('Interface/language') is None
    assert i18n.current_language() == 'en'


def test_language_change_retranslates_menus_and_actions(settings, view):
    settings.setValue('Interface/language', 'es')
    assert view.toplevel_menus[0].title() == '&Archivo'
    assert actions['open'].qaction.text() == '&Abrir'
    settings.setValue('Interface/language', 'en')
    assert view.toplevel_menus[0].title() == '&File'
    assert actions['open'].qaction.text() == '&Open'


def test_language_change_keeps_recent_file_names(
        settings, view, imgfilename3x3):
    settings.update_recent_files(imgfilename3x3)
    view.update_menu_and_actions()
    settings.setValue('Interface/language', 'es')
    assert (actions['recent_files_0'].qaction.text()
            == Path(imgfilename3x3).name)


def test_language_change_retranslates_welcome_overlay(settings, view):
    settings.setValue('Interface/language', 'es')
    assert 'Pega o suelta' in view.welcome_overlay.label.text()
    assert 'Archivos recientes' in view.welcome_overlay.files_label.text()


def test_language_change_retranslates_window_title(settings, view):
    view.undo_stack.push(QtGui.QUndoCommand())
    assert view.parent.windowTitle() == '[Untitled]* - myRef'
    settings.setValue('Interface/language', 'es')
    assert view.parent.windowTitle() == '[Sin título]* - myRef'


def test_keyboard_shortcuts_table_is_translated(view):
    i18n.set_language('es')
    model = KeyboardShortcutsModel()
    index = model.index(list(actions.keys()).index('save_as'), 0)
    assert (model.data(index, QtCore.Qt.ItemDataRole.DisplayRole)
            == 'Archivo: Guardar como')
    assert (model.headerData(2, QtCore.Qt.Orientation.Horizontal,
                             QtCore.Qt.ItemDataRole.DisplayRole)
            == 'Atajo')


def test_translated_mouse_controls_are_not_stored_translated(kbsettings, qapp):
    i18n.set_language('es')
    action = KeyboardSettings.MOUSE_ACTIONS['zoom1']
    assert action.get_button() == 'Middle'
    assert action.get_modifiers() == ['Ctrl']
    assert action.is_configured() is True
