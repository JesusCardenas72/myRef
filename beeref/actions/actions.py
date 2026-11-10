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

from functools import cached_property
import logging

from PyQt6 import QtGui

from beeref.actions.menu_structure import menu_structure
from beeref.config import KeyboardSettings, settings_events
from beeref.utils import ActionList


logger = logging.getLogger(__name__)


# Shortcut contexts. Actions in the global context are always available.
# Actions in another context only have working shortcuts while that
# context is active (e.g. while editing a text item), and then take
# precedence over global actions with the same shortcut.
CONTEXT_GLOBAL = 'global'
CONTEXT_TEXT_EDIT = 'text_edit'
CONTEXT_DRAW = 'draw'

CONTEXT_LABELS = {
    CONTEXT_GLOBAL: None,
    CONTEXT_TEXT_EDIT: 'Text Editing',
    CONTEXT_DRAW: 'Drawing',
}


class Action:
    SETTINGS_GROUP = 'Actions'

    def __init__(self, id, text, callback=None, shortcuts=None,
                 checkable=False, checked=False, group=None, settings=None,
                 enabled=True, menu_item=None, menu_id=None,
                 context=CONTEXT_GLOBAL):
        if context not in CONTEXT_LABELS:
            raise ValueError(f'Unknown shortcut context: {context}')
        self.id = id
        self.text = text
        self.callback = callback
        self.shortcuts = shortcuts or []
        self.checkable = checkable
        self.checked = checked
        self.group = group
        self.settings = settings
        self.enabled = enabled
        self.menu_item = menu_item
        self.menu_id = menu_id
        self.context = context
        self.qaction = None
        self.kb_settings = KeyboardSettings()
        settings_events.restore_keyboard_defaults.connect(
            self.on_restore_defaults)

    def __eq__(self, other):
        return self.id == other.id

    def __str__(self):
        return self.id

    def on_restore_defaults(self):
        if self.qaction:
            self.qaction.setShortcuts(actions.effective_shortcuts(self))

    @cached_property
    def menu_path(self):
        path = []

        def _get_path(menu_item):
            if isinstance(menu_item['items'], list):
                # This is a normal menu
                for item in menu_item['items']:
                    if item == self.id:
                        path.append(menu_item['menu'])
                        return True
                    if isinstance(item, dict):
                        # This is a submenu
                        if _get_path(item):
                            path.append(menu_item['menu'])
                            return True
            elif menu_item['items'] == self.menu_id:
                # This is a dynamic submenu (e.g. Recent Files)
                path.append(menu_item['menu'])
                return True

        for menu_item in menu_structure:
            _get_path(menu_item)

        return path[::-1]

    def get_shortcuts(self):
        return self.kb_settings.get_list(
            self.SETTINGS_GROUP, self.id, self.shortcuts)

    def set_shortcuts(self, value):
        logger.debug(f'Setting shortcut "{self.id}" to: {value}')
        self.kb_settings.set_list(
            self.SETTINGS_GROUP, self.id, value, self.shortcuts)
        if self.qaction:
            self.qaction.setShortcuts(actions.effective_shortcuts(self))
        # Other actions may be shadowed by this one in the active context:
        actions.apply_shortcuts()
        settings_events.shortcuts_changed.emit()

    def get_qkeysequence(self, index):
        """Current shortcuts as QKeySequence"""
        try:
            return QtGui.QKeySequence(self.get_shortcuts()[index])
        except IndexError:
            return QtGui.QKeySequence()

    def shortcuts_changed(self):
        """Whether shortcuts have changed from their defaults."""
        return self.get_shortcuts() != self.shortcuts

    def get_default_shortcut(self, index):
        try:
            return self.shortcuts[index]
        except IndexError:
            return None

    def conflicts_with(self, other):
        """Whether this action can't share a shortcut with ``other``.

        Actions of different contexts may share shortcuts: Either they
        are never active at the same time, or the non-global action
        takes precedence while its context is active.
        """
        return self != other and self.context == other.context


class BeeActionList(ActionList):
    """All actions, plus the currently active shortcut context."""

    def __init__(self, actions):
        super().__init__(actions)
        self.active_context = CONTEXT_GLOBAL

    def effective_shortcuts(self, action):
        """The shortcuts that should currently trigger ``action``."""

        if action.context == self.active_context:
            return action.get_shortcuts()
        if action.context != CONTEXT_GLOBAL:
            return []
        # Global action while another context is active: Shortcuts used
        # by the active context take precedence.
        taken = set()
        for other in self.values():
            if other.context == self.active_context:
                taken.update(other.get_shortcuts())
        return [s for s in action.get_shortcuts() if s not in taken]

    def apply_shortcuts(self):
        """Update the shortcuts of all QActions for the active context."""

        for action in self.values():
            if action.qaction:
                action.qaction.setShortcuts(self.effective_shortcuts(action))

    def set_context(self, context):
        if context not in CONTEXT_LABELS:
            raise ValueError(f'Unknown shortcut context: {context}')
        if context == self.active_context:
            return
        logger.debug(f'Switching shortcut context to: {context}')
        self.active_context = context
        self.apply_shortcuts()


actions = BeeActionList([
    Action(
        id='open',
        text='&Open',
        shortcuts=['Ctrl+O'],
        callback='on_action_open',
    ),
    Action(
        id='open_last_scene',
        text='Open &Last Scene',
        shortcuts=['Ctrl+Shift+L'],
        callback='on_action_open_last_scene',
    ),
    Action(
        id='show_in_file_browser',
        text='Show in File &Browser',
        shortcuts=['Ctrl+Alt+L'],
        callback='on_action_show_in_file_browser',
    ),
    Action(
        id='save',
        text='&Save',
        shortcuts=['Ctrl+S'],
        callback='on_action_save',
        group='active_when_items_in_scene',
    ),
    Action(
        id='save_as',
        text='Save &As...',
        shortcuts=['Ctrl+Shift+S'],
        callback='on_action_save_as',
        group='active_when_items_in_scene',
    ),
    Action(
        id='export_scene',
        text='E&xport Scene...',
        shortcuts=['Ctrl+Shift+E'],
        callback='on_action_export_scene',
        group='active_when_items_in_scene',
    ),
    Action(
        id='export_images',
        text='Export &Images...',
        callback='on_action_export_images',
        group='active_when_items_in_scene',
    ),
    Action(
        id='export_selection_as_scene',
        text='Export S&election as Scene...',
        callback='on_action_export_selection_as_scene',
        group='active_when_selection',
    ),
    Action(
        id='export_selected_images',
        text='Export Selected Ima&ges...',
        callback='on_action_export_selected_images',
        group='active_when_selection',
    ),
    Action(
        id='copy_as_file',
        text='Copy as &File',
        callback='on_action_copy_as_file',
        group='active_when_selection',
    ),
    Action(
        id='quit',
        text='&Quit',
        shortcuts=['Ctrl+Q'],
        callback='on_action_quit',
    ),
    Action(
        id='insert_images',
        text='&Images...',
        shortcuts=['Ctrl+I'],
        callback='on_action_insert_images',
    ),
    Action(
        id='insert_text',
        text='&Text',
        shortcuts=['Ctrl+T'],
        callback='on_action_insert_text',
    ),
    Action(
        id='undo',
        text='&Undo',
        shortcuts=['Ctrl+Z'],
        callback='on_action_undo',
        group='active_when_can_undo',
    ),
    Action(
        id='redo',
        text='&Redo',
        shortcuts=['Ctrl+Shift+Z'],
        callback='on_action_redo',
        group='active_when_can_redo',
    ),
    Action(
        id='copy',
        text='&Copy',
        shortcuts=['Ctrl+C'],
        callback='on_action_copy',
        group='active_when_selection',
    ),
    Action(
        id='cut',
        text='Cu&t',
        shortcuts=['Ctrl+X'],
        callback='on_action_cut',
        group='active_when_selection',
    ),
    Action(
        id='paste',
        text='&Paste',
        shortcuts=['Ctrl+V'],
        callback='on_action_paste',
    ),
    Action(
        id='delete',
        text='&Delete',
        shortcuts=['Del'],
        callback='on_action_delete_items',
        group='active_when_selection',
    ),
    Action(
        id='raise_to_top',
        text='&Raise to Top',
        shortcuts=['PgUp'],
        callback='on_action_raise_to_top',
        group='active_when_selection',
    ),
    Action(
        id='lower_to_bottom',
        text='Lower to Bottom',
        shortcuts=['PgDown'],
        callback='on_action_lower_to_bottom',
        group='active_when_selection',
    ),
    Action(
        id='normalize_height',
        text='&Height',
        shortcuts=['Shift+H'],
        callback='on_action_normalize_height',
        group='active_when_items_in_scene',
    ),
    Action(
        id='normalize_width',
        text='&Width',
        shortcuts=['Shift+W'],
        callback='on_action_normalize_width',
        group='active_when_items_in_scene',
    ),
    Action(
        id='normalize_size',
        text='&Size',
        shortcuts=['Shift+S'],
        callback='on_action_normalize_size',
        group='active_when_items_in_scene',
    ),
    Action(
        id='arrange_optimal',
        text='&Optimal',
        shortcuts=['Shift+O'],
        callback='on_action_arrange_optimal',
        group='active_when_items_in_scene',
    ),
    Action(
        id='arrange_horizontal',
        text='&Horizontal (by filename)',
        callback='on_action_arrange_horizontal',
        group='active_when_items_in_scene',
    ),
    Action(
        id='arrange_vertical',
        text='&Vertical (by filename)',
        callback='on_action_arrange_vertical',
        group='active_when_items_in_scene',
    ),
    Action(
        id='arrange_square',
        text='&Square (by filename)',
        callback='on_action_arrange_square',
        group='active_when_items_in_scene',
    ),
    Action(
        id='duplicate',
        text='Dup&licate',
        shortcuts=['Ctrl+D'],
        callback='on_action_duplicate',
        group='active_when_selection',
    ),
    Action(
        id='normalize_longest_side',
        text='&Longest Side',
        shortcuts=['Shift+L'],
        callback='on_action_normalize_longest_side',
        group='active_when_items_in_scene',
    ),
    Action(
        id='normalize_scale',
        text='S&cale',
        callback='on_action_normalize_scale',
        group='active_when_items_in_scene',
    ),
    Action(
        id='arrange_square_addition',
        text='Square (by &time added)',
        callback='on_action_arrange_square_addition',
        group='active_when_items_in_scene',
    ),
    Action(
        id='arrange_square_random',
        text='Square (ran&dom)',
        callback='on_action_arrange_square_random',
        group='active_when_items_in_scene',
    ),
    Action(
        id='align_left',
        text='Align &Left',
        shortcuts=['Ctrl+Left'],
        callback='on_action_align_left',
        group='active_when_items_in_scene',
    ),
    Action(
        id='align_right',
        text='Align R&ight',
        shortcuts=['Ctrl+Right'],
        callback='on_action_align_right',
        group='active_when_items_in_scene',
    ),
    Action(
        id='align_top',
        text='Align To&p',
        shortcuts=['Ctrl+Up'],
        callback='on_action_align_top',
        group='active_when_items_in_scene',
    ),
    Action(
        id='align_bottom',
        text='Align &Bottom',
        shortcuts=['Ctrl+Down'],
        callback='on_action_align_bottom',
        group='active_when_items_in_scene',
    ),
    Action(
        id='distribute_horizontal',
        text='Distribute Hori&zontally',
        shortcuts=['Ctrl+Alt+Shift+Right'],
        callback='on_action_distribute_horizontal',
        group='active_when_items_in_scene',
    ),
    Action(
        id='distribute_vertical',
        text='Distribute V&ertically',
        shortcuts=['Ctrl+Alt+Shift+Down'],
        callback='on_action_distribute_vertical',
        group='active_when_items_in_scene',
    ),
    Action(
        id='stack',
        text='St&ack',
        shortcuts=['Ctrl+Alt+S'],
        callback='on_action_stack',
        group='active_when_items_in_scene',
    ),
    Action(
        id='zoom_in',
        text='Zoom &In',
        shortcuts=['Ctrl++', 'Ctrl+='],
        callback='on_action_zoom_in',
        group='active_when_items_in_scene',
    ),
    Action(
        id='zoom_out',
        text='Zoom &Out',
        shortcuts=['Ctrl+-'],
        callback='on_action_zoom_out',
        group='active_when_items_in_scene',
    ),
    Action(
        id='zoom_actual',
        text='Act&ual Size',
        shortcuts=['0'],
        callback='on_action_zoom_actual',
        group='active_when_items_in_scene',
    ),
    Action(
        id='center_origin',
        text='&Center on Origin',
        callback='on_action_center_origin',
        group='active_when_items_in_scene',
    ),
    Action(
        id='change_opacity',
        text='Change &Opacity...',
        callback='on_action_change_opacity',
        group='active_when_selection',
    ),
    Action(
        id='grayscale',
        text='&Grayscale',
        shortcuts=['G'],
        checkable=True,
        callback='on_action_grayscale',
        group='active_when_selection',
    ),
    Action(
        id='nearest_neighbor',
        text='&Pixelated (No Smoothing)',
        shortcuts=['Alt+T'],
        checkable=True,
        callback='on_action_nearest_neighbor',
        group='active_when_selection',
    ),
    Action(
        id='grayscale_canvas',
        text='&Grayscale Canvas',
        shortcuts=['Ctrl+Alt+G'],
        checkable=True,
        callback='on_action_grayscale_canvas',
    ),
    Action(
        id='show_color_gamut',
        text='Show &Color Gamut',
        callback='on_action_show_color_gamut',
        group='active_when_single_image',
    ),
    Action(
        id='sample_color',
        text='Sample Color',
        shortcuts=['S'],
        callback='on_action_sample_color',
        group='active_when_items_in_scene',
    ),
    Action(
        id='crop',
        text='&Crop',
        shortcuts=['Shift+C'],
        callback='on_action_crop',
        group='active_when_single_image',
    ),
    Action(
        id='flip_horizontally',
        text='Flip &Horizontally',
        shortcuts=['H'],
        callback='on_action_flip_horizontally',
        group='active_when_selection',
    ),
    Action(
        id='flip_vertically',
        text='Flip &Vertically',
        shortcuts=['V'],
        callback='on_action_flip_vertically',
        group='active_when_selection',
    ),
    Action(
        id='new_scene',
        text='&New Scene',
        shortcuts=['Ctrl+N'],
        callback='on_action_new_scene',
    ),
    Action(
        id='fit_scene',
        text='&Fit Scene',
        shortcuts=['1'],
        callback='on_action_fit_scene',
    ),
    Action(
        id='fit_selection',
        text='Fit &Selection',
        shortcuts=['2'],
        callback='on_action_fit_selection',
        group='active_when_selection',
    ),
    Action(
        id='reset_scale',
        text='Reset &Scale',
        callback='on_action_reset_scale',
        group='active_when_selection',
    ),
    Action(
        id='reset_rotation',
        text='Reset &Rotation',
        callback='on_action_reset_rotation',
        group='active_when_selection',
    ),
    Action(
        id='reset_flip',
        text='Reset &Flip',
        callback='on_action_reset_flip',
        group='active_when_selection',
    ),
    Action(
        id='reset_crop',
        text='Reset Cro&p',
        callback='on_action_reset_crop',
        group='active_when_selection',
    ),
    Action(
        id='reset_transforms',
        text='Reset &All',
        shortcuts=['R'],
        callback='on_action_reset_transforms',
        group='active_when_selection',
    ),
    Action(
        id='select_all',
        text='&Select All',
        shortcuts=['Ctrl+A'],
        callback='on_action_select_all',
    ),
    Action(
        id='deselect_all',
        text='Deselect &All',
        shortcuts=['Ctrl+Shift+A'],
        callback='on_action_deselect_all',
    ),
    Action(
        id='help',
        text='&Help',
        shortcuts=['F1', 'Ctrl+H'],
        callback='on_action_help',
    ),
    Action(
        id='about',
        text='&About',
        callback='on_action_about',
    ),
    Action(
        id='debuglog',
        text='Show &Debug Log',
        callback='on_action_debuglog',
    ),
    Action(
        id='show_scrollbars',
        text='Show &Scrollbars',
        checkable=True,
        settings='View/show_scrollbars',
        callback='on_action_show_scrollbars',
    ),
    Action(
        id='show_menubar',
        text='Show &Menu Bar',
        checkable=True,
        settings='View/show_menubar',
        callback='on_action_show_menubar',
    ),
    Action(
        id='show_titlebar',
        text='Show &Title Bar',
        checkable=True,
        checked=True,
        callback='on_action_show_titlebar',
    ),
    Action(
        id='tablet_mode',
        text='Ta&blet Mode',
        checkable=True,
        settings='TabletMode/enabled',
        callback='on_action_tablet_mode',
    ),
    Action(
        id='lock_items',
        text='&Lock Images',
        checkable=True,
        settings='View/lock_items',
        callback='on_action_lock_items',
    ),
    Action(
        id='always_on_bottom',
        text='Always On &Bottom',
        checkable=True,
        callback='on_action_always_on_bottom',
    ),
    Action(
        id='always_on_top_of_app',
        text='Always On Top of A&pplication...',
        callback='on_action_always_on_top_of_app',
    ),
    Action(
        id='click_through',
        text='&Click-Through',
        shortcuts=['Ctrl+Alt+T'],
        checkable=True,
        callback='on_action_click_through',
    ),
    Action(
        id='lock_window',
        text='&Lock Window',
        checkable=True,
        callback='on_action_lock_window',
    ),
    Action(
        id='opacity_increase',
        text='&Increase Opacity',
        shortcuts=['Ctrl+Alt+Up'],
        callback='on_action_opacity_increase',
    ),
    Action(
        id='opacity_decrease',
        text='&Decrease Opacity',
        shortcuts=['Ctrl+Alt+Down'],
        callback='on_action_opacity_decrease',
    ),
    Action(
        id='opacity_reset',
        text='&Full Opacity',
        callback='on_action_opacity_reset',
    ),
    Action(
        id='fit_window_to_selection',
        text='Fit Window to &Selection',
        callback='on_action_fit_window_to_selection',
        group='active_when_items_in_scene',
    ),
    Action(
        id='maximize_window',
        text='&Maximize',
        checkable=True,
        callback='on_action_maximize_window',
    ),
    Action(
        id='titlebar_on_hover',
        text='Show Title Bar on &Hover',
        checkable=True,
        callback='on_action_titlebar_on_hover',
    ),
    Action(
        id='move_window',
        text='Move &Window',
        shortcuts=['Ctrl+M'],
        callback='on_action_move_window',
    ),
    Action(
        id='fullscreen',
        text='&Fullscreen',
        shortcuts=['F11'],
        checkable=True,
        callback='on_action_fullscreen',
    ),
    Action(
        id='always_on_top',
        text='&Always On Top',
        checkable=True,
        callback='on_action_always_on_top',
    ),
    Action(
        id='show_grid',
        text='&Show Grid',
        shortcuts=["Ctrl+'"],
        checkable=True,
        settings='Canvas/show_grid',
        callback='on_action_show_grid',
    ),
    Action(
        id='snap_to_grid',
        text='Snap to &Grid',
        shortcuts=["Ctrl+Shift+'"],
        checkable=True,
        settings='Canvas/snap_to_grid',
        callback='on_action_snap_to_grid',
    ),
    Action(
        id='snap_to_items',
        text='Snap to &Items',
        shortcuts=['Shift+Space'],
        checkable=True,
        settings='Canvas/snap_to_items',
        callback='on_action_snap_to_items',
    ),
    Action(
        id='focus_canvas',
        text='&Focus Canvas',
        callback='on_action_focus_canvas',
        group='active_when_items_in_scene',
    ),
    Action(
        id='optimize_canvas',
        text='&Optimize Canvas',
        callback='on_action_optimize_canvas',
        group='active_when_items_in_scene',
    ),
    Action(
        id='group_items',
        text='&Group',
        shortcuts=['Ctrl+G'],
        callback='on_action_group_items',
        group='active_when_selection',
    ),
    Action(
        id='ungroup_items',
        text='&Ungroup',
        shortcuts=['Ctrl+Shift+G'],
        callback='on_action_ungroup_items',
        group='active_when_selection',
    ),
    Action(
        id='group_color',
        text='Group &Color...',
        callback='on_action_group_color',
        group='active_when_selection',
    ),
    Action(
        id='parent_items',
        text='&Parent to First Selected',
        shortcuts=['P'],
        callback='on_action_parent_items',
        group='active_when_selection',
    ),
    Action(
        id='unparent_items',
        text='U&nparent',
        shortcuts=['Shift+P'],
        callback='on_action_unparent_items',
        group='active_when_selection',
    ),
    Action(
        id='lock_selected',
        text='&Lock',
        shortcuts=['Alt+L'],
        callback='on_action_lock_selected',
        group='active_when_selection',
    ),
    Action(
        id='unlock_all',
        text='Unloc&k All',
        shortcuts=['Alt+Shift+L'],
        callback='on_action_unlock_all',
        group='active_when_items_in_scene',
    ),
    Action(
        id='edit_comment',
        text='Co&mment...',
        shortcuts=['Alt+C'],
        callback='on_action_edit_comment',
        group='active_when_selection',
    ),
    Action(
        id='rename_item',
        text='&Rename...',
        shortcuts=['F2'],
        callback='on_action_rename_item',
        group='active_when_selection',
    ),
    Action(
        id='show_hierarchy',
        text='&Hierarchy',
        shortcuts=['Ctrl+J'],
        checkable=True,
        callback='on_action_show_hierarchy',
    ),
    Action(
        id='text_bold',
        text='&Bold',
        shortcuts=['Ctrl+B'],
        callback='on_action_text_bold',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_italic',
        text='&Italic',
        shortcuts=['Ctrl+I'],
        callback='on_action_text_italic',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_underline',
        text='&Underline',
        shortcuts=['Ctrl+U'],
        callback='on_action_text_underline',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_strikeout',
        text='&Strikethrough',
        shortcuts=['Ctrl+Shift+X'],
        callback='on_action_text_strikeout',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_color',
        text='Text &Color...',
        callback='on_action_text_color',
        group='active_when_text_selected',
    ),
    Action(
        id='text_highlight',
        text='&Highlight Color...',
        callback='on_action_text_highlight',
        group='active_when_text_selected',
    ),
    Action(
        id='note_background',
        text='Note Back&ground...',
        callback='on_action_note_background',
        group='active_when_text_selected',
    ),
    Action(
        id='text_align_left',
        text='Align Le&ft',
        shortcuts=['Ctrl+Shift+L'],
        callback='on_action_text_align_left',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_align_center',
        text='Align C&enter',
        shortcuts=['Ctrl+Shift+E'],
        callback='on_action_text_align_center',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_align_right',
        text='Align &Right',
        shortcuts=['Ctrl+Shift+R'],
        callback='on_action_text_align_right',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_bullet_list',
        text='Bulle&t List',
        shortcuts=['Ctrl+Shift+8'],
        callback='on_action_text_bullet_list',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_numbered_list',
        text='&Numbered List',
        shortcuts=['Ctrl+Shift+7'],
        callback='on_action_text_numbered_list',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_checklist',
        text='Chec&klist',
        shortcuts=['Ctrl+Shift+9'],
        callback='on_action_text_checklist',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_indent',
        text='Increase In&dent',
        shortcuts=['Ctrl+]'],
        callback='on_action_text_indent',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_dedent',
        text='Decre&ase Indent',
        shortcuts=['Ctrl+['],
        callback='on_action_text_dedent',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_link',
        text='&Link...',
        shortcuts=['Ctrl+K'],
        callback='on_action_text_link',
        group='active_when_text_selected',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_paste_plain',
        text='&Paste as Plain Text',
        shortcuts=['Ctrl+Shift+V'],
        callback='on_action_text_paste_plain',
        context=CONTEXT_TEXT_EDIT,
    ),
    Action(
        id='text_copy_format',
        text='C&opy Format',
        shortcuts=['Ctrl+Alt+C'],
        callback='on_action_text_copy_format',
        group='active_when_text_selected',
    ),
    Action(
        id='text_paste_format',
        text='Paste For&mat',
        shortcuts=['Ctrl+Alt+V'],
        callback='on_action_text_paste_format',
        group='active_when_text_selected',
    ),
    Action(
        id='text_clear_format',
        text='Clear Formatting',
        shortcuts=['Ctrl+\\'],
        callback='on_action_text_clear_format',
        group='active_when_text_selected',
    ),
    Action(
        id='text_fixed_width',
        text='Fi&xed Width',
        callback='on_action_text_fixed_width',
        group='active_when_text_selected',
    ),
    Action(
        id='settings',
        text='&Settings',
        callback='on_action_settings',
    ),
    Action(
        id='keyboard_settings',
        text='&Keyboard && Mouse',
        callback='on_action_keyboard_settings',
    ),
    Action(
        id='open_settings_dir',
        text='&Open Settings Folder',
        callback='on_action_open_settings_dir',
    ),
])
