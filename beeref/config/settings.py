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

import argparse
import logging
import os
import os.path

from PyQt6 import QtCore, QtGui

from beeref import constants, i18n


logger = logging.getLogger(__name__)


parser = argparse.ArgumentParser(
    description=f'{constants.APPNAME_FULL} {constants.VERSION}')
parser.add_argument(
    'filenames',
    nargs='*',
    default=None,
    help=('Bee file or images to open. '
          'If the first file is a bee file, it will be opened and all '
          'further files will be ignored. If the first argument isn\'t a '
          'bee file, all files will be treated as images and inserted as '
          'if opened with "Insert -> Images".'))
parser.add_argument(
    '--settings-dir',
    help='settings directory to use instead of default location')
parser.add_argument(
    '-l', '--loglevel',
    default='INFO',
    choices=list(logging._nameToLevel.keys()),
    help='log level for console output')
parser.add_argument(
    '--debug-boundingrects',
    default=False,
    action='store_true',
    help='draw item\'s bounding rects for debugging')
parser.add_argument(
    '--debug-shapes',
    default=False,
    action='store_true',
    help='draw item\'s mouse event shapes for debugging')
parser.add_argument(
    '--debug-handles',
    default=False,
    action='store_true',
    help='draw item\'s transform handle areas for debugging')
parser.add_argument(
    '--debug-raise-error',
    default='',
    help='immediately exit with given error message')


class CommandlineArgs:
    """Wrapper around argument parsing.

    Checking for unknown arguments is configurable so that it can be
    deliberately enabled from the main() function while ignored for
    other imports so that unit tests won't fail.

    This is a singleton so that arguments are only parsed once, unless
    ``with_check`` is ``True``.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance or kwargs.get('with_check'):
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, with_check=False):
        if not hasattr(self, '_args'):
            if with_check:
                self._args = parser.parse_args()
            else:
                self._args = parser.parse_known_args()[0]

    def __getattribute__(self, name):
        if name == '_args':
            return super().__getattribute__(name)
        else:
            return getattr(self._args, name)


class BeeSettingsEvents(QtCore.QObject):
    restore_defaults = QtCore.pyqtSignal()
    restore_keyboard_defaults = QtCore.pyqtSignal()
    language_changed = QtCore.pyqtSignal()
    view_settings_changed = QtCore.pyqtSignal()
    shortcuts_changed = QtCore.pyqtSignal()


# We want to send and receive settings events globally, not per
# BeeSettings instance. Since we can't instantiate BeeSettings
# globally on module level (because the Qt app doesn't exist yet), we
# use this events proxy
settings_events = BeeSettingsEvents()


def apply_language(language):
    i18n.set_language(language)
    settings_events.language_changed.emit()


def notify_view_settings_changed(value):
    settings_events.view_settings_changed.emit()


def cast_bool(value):
    """Booleans come back from the settings file as strings."""

    if isinstance(value, str):
        return value.lower() == 'true'
    return bool(value)


MOUSE_BINDING_NOT_CONFIGURED = 'Not Configured'
MOUSE_BINDING_BUTTONS = (
    MOUSE_BINDING_NOT_CONFIGURED, 'Left', 'Middle', 'Right')
MOUSE_BINDING_MODIFIERS = ('Shift', 'Ctrl', 'Alt')
LOCK_ICON_CORNERS = ('top_left', 'top_right', 'bottom_left', 'bottom_right')


def parse_mouse_binding(value):
    """Splits a mouse binding like ``Ctrl+Right``.

    :returns: The button and a list of the modifier keys.
    """

    *modifiers, button = value.split('+')
    return button, modifiers


def format_mouse_binding(button, modifiers):
    """The inverse of ``parse_mouse_binding``."""

    return '+'.join((*modifiers, button))


def is_valid_mouse_binding(value):
    button, modifiers = parse_mouse_binding(value)
    return (button in MOUSE_BINDING_BUTTONS
            and all(mod in MOUSE_BINDING_MODIFIERS for mod in modifiers))


class BeeSettings(QtCore.QSettings):

    FIELDS = {
        'Interface/language': {
            'default': i18n.SYSTEM_LANGUAGE,
            'validate': lambda x: (
                x == i18n.SYSTEM_LANGUAGE or x in i18n.LANGUAGES),
            'post_save_callback': apply_language,
        },
        'Save/confirm_close_unsaved': {
            'default': True,
            'cast': cast_bool,
        },
        'Performance/undo_limit': {
            'default': 100,
            'cast': int,
            'validate': lambda x: 1 <= x <= 1000,
        },
        'Items/image_storage_format': {
            'default': 'best',
            'validate': lambda x: x in ('png', 'jpg', 'best'),
        },
        'Items/drag_into_groups': {
            'default': True,
            'cast': cast_bool,
        },
        'Items/arrange_gap': {
            'default': 0,
            'cast': int,
            'validate': lambda x: 0 <= x <= 200,
        },
        'Export/name_template': {
            'default': '',
            'cast': str,
        },
        'Export/cropped': {
            'default': False,
            'cast': cast_bool,
        },
        'Items/normalize_source': {
            'default': 'average',
            'validate': lambda x: x in ('average', 'first'),
        },
        'Items/arrange_default': {
            'default': 'optimal',
            'validate': lambda x: x in (
                'optimal', 'horizontal', 'vertical', 'square'),
        },
        'Items/image_allocation_limit': {
            'default': 256,
            'cast': int,
            'validate': lambda x: x >= 0,
            'post_save_callback': QtGui.QImageReader.setAllocationLimit,
        },
        'TabletMode/pan': {
            'default': 'Right',
            'cast': str,
            'validate': is_valid_mouse_binding,
        },
        'TabletMode/zoom': {
            'default': 'Ctrl+Right',
            'cast': str,
            'validate': is_valid_mouse_binding,
        },
        'TabletMode/zoom_inverted': {
            'default': False,
            'cast': cast_bool,
        },
        'TabletMode/show_titlebar_button': {
            'default': True,
            'cast': cast_bool,
            'post_save_callback': notify_view_settings_changed,
        },
        'Window/opacity': {
            'default': 100,
            'cast': int,
            'validate': lambda x: 10 <= x <= 100,
            'post_save_callback': notify_view_settings_changed,
        },
        'Window/startup_mode': {
            'default': 'normal',
            'validate': lambda x: x in (
                'normal', 'last', 'always_on_top', 'click_through'),
        },
        'Window/notify_mode_change': {
            'default': True,
            'cast': cast_bool,
        },
        'Window/tray_icon': {
            'default': False,
            'cast': cast_bool,
            'post_save_callback': notify_view_settings_changed,
        },
        'Window/global_hotkeys': {
            'default': False,
            'cast': cast_bool,
            'post_save_callback': notify_view_settings_changed,
        },
        'Window/scale_on_resize': {
            'default': False,
            'cast': cast_bool,
        },
        'Window/maximize_over_taskbar': {
            'default': False,
            'cast': cast_bool,
        },
        'Window/lock_when_maximized': {
            'default': False,
            'cast': cast_bool,
            'post_save_callback': notify_view_settings_changed,
        },
        'Window/resize_border': {
            'default': 8,
            'cast': int,
            'validate': lambda x: 2 <= x <= 40,
        },
        'Canvas/grid_size': {
            'default': 50,
            'cast': int,
            'validate': lambda x: 5 <= x <= 1000,
            'post_save_callback': notify_view_settings_changed,
        },
        'Canvas/grid_style': {
            'default': 'lines',
            'validate': lambda x: x in ('lines', 'dots'),
            'post_save_callback': notify_view_settings_changed,
        },
        'Canvas/snap_distance': {
            'default': 10,
            'cast': int,
            'validate': lambda x: 1 <= x <= 50,
        },
        'Canvas/highlight_canvas': {
            'default': False,
            'cast': cast_bool,
            'post_save_callback': notify_view_settings_changed,
        },
        'Canvas/margin': {
            'default': 50,
            'cast': int,
            'validate': lambda x: 0 <= x <= 1000,
            'post_save_callback': notify_view_settings_changed,
        },
        'LockIcon/corner': {
            'default': 'bottom_left',
            'validate': lambda x: x in LOCK_ICON_CORNERS,
            'post_save_callback': notify_view_settings_changed,
        },
        'LockIcon/size': {
            'default': 24,
            'cast': int,
            'validate': lambda x: 12 <= x <= 128,
            'post_save_callback': notify_view_settings_changed,
        },
        'LockIcon/transparency': {
            'default': 30,
            'cast': int,
            'validate': lambda x: 0 <= x <= 90,
            'post_save_callback': notify_view_settings_changed,
        },
    }

    def __init__(self):
        settings_format = QtCore.QSettings.Format.IniFormat
        settings_scope = QtCore.QSettings.Scope.UserScope
        settings_dir = self.get_settings_dir()
        if settings_dir:
            QtCore.QSettings.setPath(
                settings_format, settings_scope, settings_dir)
        super().__init__(
            settings_format,
            settings_scope,
            constants.APPNAME,
            constants.APPNAME)

    def on_startup(self):
        """Settings to be applied on application startup."""

        if os.environ.get('QT_IMAGEIO_MAXALLOC'):
            alloc = int(os.environ['QT_IMAGEIO_MAXALLOC'])
        else:
            alloc = self.valueOrDefault('Items/image_allocation_limit')
        QtGui.QImageReader.setAllocationLimit(alloc)

    def setValue(self, key, value):
        super().setValue(key, value)
        if key in self.FIELDS and 'post_save_callback' in self.FIELDS[key]:
            self.FIELDS[key]['post_save_callback'](value)

    def remove(self, key):
        super().remove(key)
        if key in self.FIELDS and 'post_save_callback' in self.FIELDS[key]:
            value = self.valueOrDefault(key)
            self.FIELDS[key]['post_save_callback'](value)

    def valueOrDefault(self, key):
        """Get the value for key, or the default value specified in FIELDS.

        This is the method to be used for configurable settings (as
        opposed to settings that BeeRef stores on its own.)

        This will validate and type cast the given value if 'cast' and
        'validate' are specified in the FIELDS entry for the given
        key. The default value will be returned if validation or type
        casting fails.
        """

        val = self.value(key)
        conf = self.FIELDS[key]
        if val is None:
            val = conf['default']
        if 'cast' in conf:
            try:
                val = conf['cast'](val)
            except (ValueError, TypeError):
                val = conf['default']
        if 'validate' in conf:
            if not conf['validate'](val):
                val = conf['default']
        return val

    def value_changed(self, key):
        """Whether the value for given key has changed from its default."""

        return self.valueOrDefault(key) != self.FIELDS[key]['default']

    def restore_defaults(self):
        """Restore all the values specified in FILEDS to their default values
        by removing them from the settings file.
        """

        logger.debug('Restoring settings to defaults')
        for key in self.FIELDS.keys():
            self.remove(key)
        settings_events.restore_defaults.emit()

    def fileName(self):
        return os.path.normpath(super().fileName())

    def get_settings_dir(self):  # pragma: no cover
        args = CommandlineArgs()
        return args.settings_dir

    def update_recent_files(self, filename):
        filename = os.path.abspath(filename)
        values = self.get_recent_files()
        if filename in values:
            values.remove(filename)
        values.insert(0, filename)

        self.beginWriteArray('RecentFiles')
        for i, filename in enumerate(values[:10]):
            self.setArrayIndex(i)
            self.setValue('path', filename)
        self.endArray()

    def get_recent_files(self, existing_only=False):
        values = []
        size = self.beginReadArray('RecentFiles')
        for i in range(size):
            self.setArrayIndex(i)
            values.append(self.value('path'))
        self.endArray()

        if existing_only:
            values = [f for f in values if os.path.exists(f)]
        return values
