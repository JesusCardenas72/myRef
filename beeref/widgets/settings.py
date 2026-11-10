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

from functools import partial
import logging

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt

from beeref import constants, i18n
from beeref.config import BeeSettings, settings_events
from beeref.config.settings import (
    format_mouse_binding,
    MOUSE_BINDING_BUTTONS,
    MOUSE_BINDING_MODIFIERS,
    MOUSE_BINDING_NOT_CONFIGURED,
    parse_mouse_binding,
)
from beeref.i18n import _


logger = logging.getLogger(__name__)


class GroupBase(QtWidgets.QGroupBox):
    TITLE = None
    HELPTEXT = None
    KEY = None

    def __init__(self):
        super().__init__()
        self.settings = BeeSettings()
        self.update_title()
        self.layout = QtWidgets.QVBoxLayout()
        self.setLayout(self.layout)
        settings_events.restore_defaults.connect(self.on_restore_defaults)
        settings_events.language_changed.connect(self.retranslate)

        if self.HELPTEXT:
            self.helptxt = QtWidgets.QLabel(_(self.HELPTEXT))
            self.helptxt.setWordWrap(True)
            self.layout.addWidget(self.helptxt)

    def update_title(self):
        title = [_(self.TITLE)]
        if self.settings.value_changed(self.KEY):
            title.append(constants.CHANGED_SYMBOL)
        self.setTitle(' '.join(title))

    def retranslate(self):
        self.update_title()
        if self.HELPTEXT:
            self.helptxt.setText(_(self.HELPTEXT))

    def on_value_changed(self, value):
        if self.ignore_value_changed:
            return

        value = self.convert_value_from_qt(value)
        if value != self.settings.valueOrDefault(self.KEY):
            logger.debug(f'Setting {self.KEY} changed to: {value}')
            self.settings.setValue(self.KEY, value)
            self.update_title()

    def convert_value_from_qt(self, value):
        return value

    def on_restore_defaults(self):
        new_value = self.settings.valueOrDefault(self.KEY)
        self.ignore_value_changed = True
        self.set_value(new_value)
        self.ignore_value_changed = False
        self.update_title()


class RadioGroup(GroupBase):
    OPTIONS = None

    def __init__(self):
        super().__init__()

        self.ignore_value_changed = True
        self.buttons = {}
        for (value, label, helptext) in self.OPTIONS:
            btn = QtWidgets.QRadioButton(_(label))
            self.buttons[value] = btn
            btn.setToolTip(_(helptext))
            btn.toggled.connect(partial(self.on_value_changed, value=value))
            if value == self.settings.valueOrDefault(self.KEY):
                btn.setChecked(True)
            self.layout.addWidget(btn)

        self.ignore_value_changed = False
        self.layout.addStretch(100)

    def set_value(self, value):
        for old_value, btn in self.buttons.items():
            btn.setChecked(old_value == value)

    def retranslate(self):
        super().retranslate()
        for (value, label, helptext) in self.OPTIONS:
            self.buttons[value].setText(_(label))
            self.buttons[value].setToolTip(_(helptext))


class IntegerGroup(GroupBase):
    MIN = None
    MAX = None
    SUFFIX = ''

    def __init__(self):
        super().__init__()
        self.input = QtWidgets.QSpinBox()
        self.input.setRange(self.MIN, self.MAX)
        self.input.setSuffix(self.SUFFIX)
        self.set_value(self.settings.valueOrDefault(self.KEY))
        self.input.valueChanged.connect(self.on_value_changed)
        self.layout.addWidget(self.input)
        self.layout.addStretch(100)
        self.ignore_value_changed = False

    def set_value(self, value):
        self.input.setValue(value)


class SingleCheckboxGroup(GroupBase):
    LABEL = None

    def __init__(self):
        super().__init__()
        self.input = QtWidgets.QCheckBox(_(self.LABEL))
        self.set_value(self.settings.valueOrDefault(self.KEY))
        self.input.checkStateChanged.connect(self.on_value_changed)
        self.layout.addWidget(self.input)
        self.layout.addStretch(100)
        self.ignore_value_changed = False

    def set_value(self, value):
        self.input.setChecked(value)

    def convert_value_from_qt(self, value):
        return value == Qt.CheckState.Checked

    def retranslate(self):
        super().retranslate()
        self.input.setText(_(self.LABEL))


class TextGroup(GroupBase):
    PLACEHOLDER = ''

    def __init__(self):
        super().__init__()
        self.input = QtWidgets.QLineEdit()
        self.input.setPlaceholderText(_(self.PLACEHOLDER))
        self.set_value(self.settings.valueOrDefault(self.KEY))
        self.input.textChanged.connect(self.on_value_changed)
        self.layout.addWidget(self.input)
        self.layout.addStretch(100)
        self.ignore_value_changed = False

    def set_value(self, value):
        self.input.setText(value)

    def retranslate(self):
        super().retranslate()
        self.input.setPlaceholderText(_(self.PLACEHOLDER))


class MouseBindingGroup(GroupBase):
    """A mouse button plus modifier keys, stored as e.g. ``Ctrl+Right``."""

    def __init__(self):
        super().__init__()
        self.ignore_value_changed = True

        self.button_label = QtWidgets.QLabel(_('Mouse Button:'))
        self.layout.addWidget(self.button_label)
        self.button_input = QtWidgets.QComboBox()
        for button in MOUSE_BINDING_BUTTONS:
            self.button_input.addItem(_(button), button)
        self.layout.addWidget(self.button_input)

        self.modifier_inputs = {}
        for modifier in MOUSE_BINDING_MODIFIERS:
            checkbox = QtWidgets.QCheckBox(_(modifier))
            self.modifier_inputs[modifier] = checkbox
            self.layout.addWidget(checkbox)

        self.set_value(self.settings.valueOrDefault(self.KEY))
        self.button_input.currentIndexChanged.connect(self.on_input_changed)
        for checkbox in self.modifier_inputs.values():
            checkbox.toggled.connect(self.on_input_changed)
        self.layout.addStretch(100)
        self.ignore_value_changed = False

    def set_value(self, value):
        button, modifiers = parse_mouse_binding(value)
        self.button_input.setCurrentIndex(self.button_input.findData(button))
        for modifier, checkbox in self.modifier_inputs.items():
            checkbox.setChecked(modifier in modifiers)
        self.update_modifiers_enabled()

    def get_value(self):
        button = self.button_input.currentData()
        if button == MOUSE_BINDING_NOT_CONFIGURED:
            return button
        modifiers = [modifier
                     for modifier, checkbox in self.modifier_inputs.items()
                     if checkbox.isChecked()]
        return format_mouse_binding(button, modifiers)

    def update_modifiers_enabled(self):
        enabled = (
            self.button_input.currentData() != MOUSE_BINDING_NOT_CONFIGURED)
        for checkbox in self.modifier_inputs.values():
            checkbox.setEnabled(enabled)

    def on_input_changed(self, *args):
        self.update_modifiers_enabled()
        self.on_value_changed(self.get_value())

    def retranslate(self):
        super().retranslate()
        self.button_label.setText(_('Mouse Button:'))
        for index, button in enumerate(MOUSE_BINDING_BUTTONS):
            self.button_input.setItemText(index, _(button))
        for modifier, checkbox in self.modifier_inputs.items():
            checkbox.setText(_(modifier))


class LanguageWidget(RadioGroup):
    TITLE = 'Language:'
    HELPTEXT = 'The language of the user interface.'
    KEY = 'Interface/language'
    OPTIONS = (
        (i18n.SYSTEM_LANGUAGE, 'Automatic (system language)',
         ('Use the language of the operating system if available, '
          'otherwise English')),
        *((code, name, '') for code, name in i18n.LANGUAGES.items()))


class ArrangeDefaultWidget(RadioGroup):
    TITLE = 'Default Arrange Method:'
    HELPTEXT = ('How images are arranged when inserted in batch')
    KEY = 'Items/arrange_default'
    OPTIONS = (
        ('optimal', 'Optimal', 'Arrange Optimal'),
        ('horizontal', 'Horizontal (by filename)',
         'Arrange Horizontal (by filename)'),
        ('vertical', 'Vertical (by filename)',
         'Arrange Vertical (by filename)'),
        ('square', 'Square (by filename)', 'Arrange Square (by filename)'))


class NormalizeSourceWidget(RadioGroup):
    TITLE = 'Normalize To:'
    HELPTEXT = 'Which size the normalize actions use as reference'
    KEY = 'Items/normalize_source'
    OPTIONS = (
        ('average', 'Average', 'The average of all affected items'),
        ('first', 'First Item', 'The first item in hierarchy order'))


class ImageStorageFormatWidget(RadioGroup):
    TITLE = 'Image Storage Format:'
    HELPTEXT = ('How images are stored inside bee files.'
                ' Changes will only take effect on newly saved images.')
    KEY = 'Items/image_storage_format'
    OPTIONS = (
        ('best', 'Best Guess',
         ('Small images and images with alpha channel are stored as png,'
          ' everything else as jpg')),
        ('png', 'Always PNG', 'Lossless, but large bee file'),
        ('jpg', 'Always JPG',
         'Small bee file, but lossy and no transparency support'))


class ArrangeGapWidget(IntegerGroup):
    TITLE = 'Arrange Gap:'
    HELPTEXT = ('The gap between images when using arrange actions.')
    KEY = 'Items/arrange_gap'
    MIN = 0
    MAX = 200


class AllocationLimitWidget(IntegerGroup):
    TITLE = 'Maximum Image Size:'
    HELPTEXT = ('The maximum image size that can be loaded (in megabytes). '
                'Set to 0 for no limitation.')
    KEY = 'Items/image_allocation_limit'
    MIN = 0
    MAX = 10000


class ExportNameTemplateWidget(TextGroup):
    TITLE = 'Image File Names:'
    HELPTEXT = ('Template for file names when exporting images. '
                '%0: original name, %1: number, %2: zero-padded number, '
                '%3: scene name. Leave empty for the default names.')
    PLACEHOLDER = 'e.g. %2 - %0'
    KEY = 'Export/name_template'


class ExportCroppedWidget(SingleCheckboxGroup):
    TITLE = 'Cropped Images:'
    HELPTEXT = ('When exporting images, export only the visible area of '
                'cropped images instead of the whole image.')
    LABEL = 'Export cropped area only'
    KEY = 'Export/cropped'


class UndoLimitWidget(IntegerGroup):
    TITLE = 'Undo History Size:'
    HELPTEXT = ('How many steps can be undone. Takes effect with the next '
                'new or opened scene. More steps use more memory.')
    KEY = 'Performance/undo_limit'
    MIN = 1
    MAX = 1000


class ConfirmCloseUnsavedWidget(SingleCheckboxGroup):
    TITLE = 'Confirm when closing an unsaved file:'
    HELPTEXT = (
        'When about to close an unsaved file, should BeeRef ask for '
        'confirmation?')
    LABEL = 'Confirm when closing'
    KEY = 'Save/confirm_close_unsaved'


class TabletPanWidget(MouseBindingGroup):
    TITLE = 'Pan:'
    HELPTEXT = 'The mouse controls for panning while tablet mode is on.'
    KEY = 'TabletMode/pan'


class TabletZoomWidget(MouseBindingGroup):
    TITLE = 'Zoom:'
    HELPTEXT = ('The mouse controls for zooming while tablet mode is on. '
                'Drag up or down to zoom.')
    KEY = 'TabletMode/zoom'


class TabletZoomInvertedWidget(SingleCheckboxGroup):
    TITLE = 'Zoom Direction:'
    HELPTEXT = ('Swap dragging up and down when zooming while tablet mode '
                'is on.')
    LABEL = 'Inverted'
    KEY = 'TabletMode/zoom_inverted'


class TabletTitlebarButtonWidget(SingleCheckboxGroup):
    TITLE = 'Title Bar Button:'
    HELPTEXT = ('Show a button in the title bar to turn tablet mode on and '
                'off (Windows only). It is also available in the View menu.')
    LABEL = 'Show button'
    KEY = 'TabletMode/show_titlebar_button'


class LockIconCornerWidget(RadioGroup):
    TITLE = 'Position:'
    HELPTEXT = 'The corner of the window in which the padlock is shown.'
    KEY = 'LockIcon/corner'
    OPTIONS = (
        ('top_left', 'Top left', ''),
        ('top_right', 'Top right', ''),
        ('bottom_left', 'Bottom left', ''),
        ('bottom_right', 'Bottom right', ''))


class LockIconSizeWidget(IntegerGroup):
    TITLE = 'Size:'
    HELPTEXT = 'The width and height of the padlock.'
    KEY = 'LockIcon/size'
    MIN = 12
    MAX = 128
    SUFFIX = ' px'


class LockIconTransparencyWidget(IntegerGroup):
    TITLE = 'Transparency:'
    HELPTEXT = 'How see-through the padlock is. 0 % is fully opaque.'
    KEY = 'LockIcon/transparency'
    MIN = 0
    MAX = 90
    SUFFIX = ' %'


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.tabs = tabs = QtWidgets.QTabWidget()

        # Miscellaneous
        misc = QtWidgets.QWidget()
        misc_layout = QtWidgets.QGridLayout()
        misc.setLayout(misc_layout)
        misc_layout.addWidget(LanguageWidget(), 0, 0)
        misc_layout.addWidget(ConfirmCloseUnsavedWidget(), 0, 1)
        misc_layout.addWidget(UndoLimitWidget(), 1, 0)
        tabs.addTab(misc, '')

        # Images & Items
        items = QtWidgets.QWidget()
        items_layout = QtWidgets.QGridLayout()
        items.setLayout(items_layout)
        items_layout.addWidget(ImageStorageFormatWidget(), 0, 0)
        items_layout.addWidget(AllocationLimitWidget(), 0, 1)
        items_layout.addWidget(ArrangeGapWidget(), 1, 0)
        items_layout.addWidget(ArrangeDefaultWidget(), 1, 1)
        items_layout.addWidget(NormalizeSourceWidget(), 2, 0)
        tabs.addTab(items, '')

        # Export
        export = QtWidgets.QWidget()
        export_layout = QtWidgets.QGridLayout()
        export.setLayout(export_layout)
        export_layout.addWidget(ExportNameTemplateWidget(), 0, 0)
        export_layout.addWidget(ExportCroppedWidget(), 0, 1)

        # Tablet Mode
        tablet = QtWidgets.QWidget()
        tablet_layout = QtWidgets.QGridLayout()
        tablet.setLayout(tablet_layout)
        tablet_layout.addWidget(TabletPanWidget(), 0, 0)
        tablet_layout.addWidget(TabletZoomWidget(), 0, 1)
        tablet_layout.addWidget(TabletZoomInvertedWidget(), 1, 0)
        tablet_layout.addWidget(TabletTitlebarButtonWidget(), 1, 1)
        tabs.addTab(tablet, '')
        tabs.addTab(export, '')

        # Lock Icon
        lock_icon = QtWidgets.QWidget()
        lock_icon_layout = QtWidgets.QGridLayout()
        lock_icon.setLayout(lock_icon_layout)
        lock_icon_layout.addWidget(LockIconCornerWidget(), 0, 0, 2, 1)
        lock_icon_layout.addWidget(LockIconSizeWidget(), 0, 1)
        lock_icon_layout.addWidget(LockIconTransparencyWidget(), 1, 1)
        tabs.addTab(lock_icon, '')

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(tabs)

        # Bottom row of buttons
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self.reset_btn = QtWidgets.QPushButton()
        self.reset_btn.setAutoDefault(False)
        self.reset_btn.clicked.connect(self.on_restore_defaults)
        buttons.addButton(self.reset_btn,
                          QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)

        layout.addWidget(buttons)
        self.retranslate()
        settings_events.language_changed.connect(self.retranslate)
        self.show()

    def retranslate(self):
        self.setWindowTitle(_('{app} Settings').format(app=constants.APPNAME))
        self.tabs.setTabText(0, _('&Miscellaneous'))
        self.tabs.setTabText(1, _('&Images && Items'))
        self.tabs.setTabText(2, _('&Tablet Mode'))
        self.tabs.setTabText(3, _('&Lock Icon'))
        self.tabs.setTabText(4, _('E&xport'))
        self.reset_btn.setText(_('&Restore Defaults'))

    def on_restore_defaults(self, *args, **kwargs):
        reply = QtWidgets.QMessageBox.question(
            self,
            _('Restore defaults?'),
            _('Do you want to restore all settings to their default values?'))

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            BeeSettings().restore_defaults()
