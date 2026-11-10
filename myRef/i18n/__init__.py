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

"""Translation of the user interface.

Strings are written in English in the source code and double as keys
into the catalog of the active language. Translate them when they are
displayed, not when they are defined: The language can change while
the application runs, and some of them (e.g. mouse buttons) are also
stored in the settings file and have to stay in English there.

To add a language, create a module with a ``TRANSLATIONS`` dict like
the one in ``es.py`` and add it to ``LANGUAGES`` and ``CATALOGS``.
"""

import logging

from PyQt6 import QtCore

from myRef.i18n import es


logger = logging.getLogger(__name__)


SYSTEM_LANGUAGE = 'system'
DEFAULT_LANGUAGE = 'en'

# Language codes and their names in the respective language
LANGUAGES = {
    'en': 'English',
    'es': 'Español',
}

CATALOGS = {
    'es': es.TRANSLATIONS,
}

_language = DEFAULT_LANGUAGE
_catalog = {}
_qt_translator = None


def _(text):
    """Returns the translation of ``text`` in the current language, or
    ``text`` itself if there is none.
    """

    return _catalog.get(text, text)


def current_language():
    """The code of the language currently in use."""

    return _language


def detect_system_language():
    """The first of the user's preferred languages that we support."""

    for name in QtCore.QLocale.system().uiLanguages():
        code = name.replace('_', '-').split('-')[0].lower()
        if code in LANGUAGES:
            return code
    return DEFAULT_LANGUAGE


def _install_qt_translator(language):
    """Translates the strings that come from Qt itself, like the
    standard dialog buttons and the names of keys in shortcuts.
    """

    global _qt_translator

    app = QtCore.QCoreApplication.instance()
    if app is None:
        return

    if _qt_translator:
        app.removeTranslator(_qt_translator)
        _qt_translator = None

    if language == DEFAULT_LANGUAGE:
        return

    translator = QtCore.QTranslator()
    path = QtCore.QLibraryInfo.path(
        QtCore.QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(f'qtbase_{language}', path):
        app.installTranslator(translator)
        _qt_translator = translator  # Qt doesn't take ownership
    else:
        logger.warning(f'No Qt translations for {language} in {path}')


def set_language(language):
    """Sets the language for all further translations.

    :param language: A key of ``LANGUAGES`` or ``SYSTEM_LANGUAGE``.
    """

    global _language, _catalog

    if language == SYSTEM_LANGUAGE:
        language = detect_system_language()
    if language not in LANGUAGES:
        logger.warning(f'Unknown language: {language}')
        language = DEFAULT_LANGUAGE

    logger.debug(f'Setting language to {language}')
    _language = language
    _catalog = CATALOGS.get(language, {})
    _install_qt_translator(language)
