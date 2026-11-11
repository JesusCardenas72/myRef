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
import os
import os.path
import shutil

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef.actions import ActionsMixin, actions
from myRef.actions.actions import CONTEXT_DRAW, CONTEXT_GLOBAL
from myRef.canvas import CanvasMixin
from myRef.drag_tools import DragToolsMixin
from myRef import commands
from myRef.config import (
    BeeSettings,
    CommandlineArgs,
    KeyboardSettings,
    mouse_binding_matches_event,
    settings_events,
)
from myRef import constants
from myRef import fileio
from myRef.fileio.errors import IMG_LOADING_ERROR_MSG
from myRef.fileio.export import exporter_registry, ImagesToDirectoryExporter
from myRef.i18n import _
from myRef import hierarchy
from myRef.image_tools import (
    ImageToolsMixin,
    is_web_url,
    reveal_in_file_browser,
)
from myRef import textformat
from myRef import widgets
from myRef.items import (
    BeePixmapItem, BeeTextItem, BeeDrawingItem,
    items_in_order)
from myRef.main_controls import MainControlsMixin
from myRef.scene import BeeGraphicsScene
from myRef.utils import get_file_extension_from_format, qcolor_to_hex
from myRef.window_modes import WindowModesMixin


commandline_args = CommandlineArgs()
logger = logging.getLogger(__name__)


class BeeGraphicsView(MainControlsMixin,
                      CanvasMixin,
                      ImageToolsMixin,
                      DragToolsMixin,
                      QtWidgets.QGraphicsView,
                      ActionsMixin,
                      WindowModesMixin):

    PAN_MODE = 1
    ZOOM_MODE = 2
    SAMPLE_COLOR_MODE = 3

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.parent = parent
        self.settings = BeeSettings()
        self.keyboard_settings = KeyboardSettings()
        self.welcome_overlay = widgets.welcome_overlay.WelcomeOverlay(self)

        self.setBackgroundBrush(
            QtGui.QBrush(QtGui.QColor(*constants.COLORS['Scene:Canvas'])))
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.undo_stack = QtGui.QUndoStack(self)
        self.apply_undo_limit()
        self.undo_stack.canRedoChanged.connect(self.on_can_redo_changed)
        self.undo_stack.canUndoChanged.connect(self.on_can_undo_changed)
        self.undo_stack.cleanChanged.connect(self.on_undo_clean_changed)

        self.filename = None
        self.previous_transform = None
        self.active_mode = None
        self.tablet_mode = False
        self.titlebar_button = None
        self.context_menu_blocked = False
        self.right_gesture_start = None
        self.right_gesture_moved = False
        self.hierarchy_dock = None
        self.title_editor = None
        self.title_panel = None
        self.text_toolbar = None
        self.draw_session = None
        self.draw_toolbar = None

        self.scene = BeeGraphicsScene(self.undo_stack)
        self.scene.changed.connect(self.on_scene_changed)
        self.scene.selectionChanged.connect(self.on_selection_changed)
        self.scene.cursor_changed.connect(self.on_cursor_changed)
        self.scene.cursor_cleared.connect(self.on_cursor_cleared)
        self.setScene(self.scene)
        self.lock_button = widgets.view_buttons.LockButton(self)

        # Context menu and actions
        self.init_image_tools()
        self.init_drag_tools()
        self.init_window_mode_state()
        self.init_canvas_state()
        self.build_menu_and_actions()
        self.update_text_actions()
        self.lock_button.clicked.connect(
            actions.actions['lock_items'].qaction.setChecked)
        self.control_target = self
        self.init_main_controls(main_window=parent)
        settings_events.language_changed.connect(self.on_language_changed)
        settings_events.view_settings_changed.connect(
            self.on_view_settings_changed)
        self.init_window_modes()
        settings_events.shortcuts_changed.connect(
            self.register_global_hotkeys)
        settings_events.restore_keyboard_defaults.connect(
            self.register_global_hotkeys)

        # Load files given via command line
        if commandline_args.filenames:
            fn = commandline_args.filenames[0]
            if os.path.splitext(fn)[1] == '.bee':
                self.open_from_file(fn)
            else:
                self.do_insert_images(commandline_args.filenames)

        self.update_window_title()

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        self._filename = value
        self.update_window_title()
        if value:
            self.settings.update_recent_files(value)
            self.update_menu_and_actions()

    def cancel_active_modes(self):
        self.cancel_drag_tools()
        self.scene.cancel_active_modes()
        self.cancel_sample_color_mode()
        self.active_mode = None

    def cancel_sample_color_mode(self):
        logger.debug('Cancel sample color mode')
        self.active_mode = None
        self.viewport().unsetCursor()
        if hasattr(self, 'sample_color_widget'):
            self.sample_color_widget.hide()
            del self.sample_color_widget
        if self.scene.has_multi_selection():
            self.scene.multi_select_item.bring_to_front()

    def update_window_title(self):
        clean = self.undo_stack.isClean()
        if clean and not self.filename:
            title = constants.APPNAME
        else:
            name = os.path.basename(self.filename or _('[Untitled]'))
            clean = '' if clean else '*'
            title = f'{name}{clean} - {constants.APPNAME}'
        self.parent.setWindowTitle(title)

    def on_language_changed(self):
        self.retranslate_menu_and_actions()
        if self.hierarchy_dock:
            self.hierarchy_dock.retranslate()
        if self.text_toolbar:
            self.text_toolbar.retranslate()
        if self.draw_toolbar:
            self.draw_toolbar.retranslate()
        self.welcome_overlay.retranslate()
        self.update_window_title()

    def on_scene_changed(self, region):
        if not self.scene.items():
            logger.debug('No items in scene')
            self.setTransform(QtGui.QTransform())
            self.welcome_overlay.setFocus()
            self.clearFocus()
            self.welcome_overlay.show()
            self.actiongroup_set_enabled('active_when_items_in_scene', False)
        else:
            if self.title_editor is None:
                # Don't take the focus from the title being edited
                self.setFocus()
            self.welcome_overlay.clearFocus()
            self.welcome_overlay.hide()
            self.actiongroup_set_enabled('active_when_items_in_scene', True)
        self.recalc_scene_rect()

    def on_can_redo_changed(self, can_redo):
        self.actiongroup_set_enabled(
            'active_when_can_redo', can_redo and not self.scene.items_locked)

    def on_can_undo_changed(self, can_undo):
        self.actiongroup_set_enabled(
            'active_when_can_undo', can_undo and not self.scene.items_locked)

    def on_undo_clean_changed(self, clean):
        self.update_window_title()

    def on_context_menu(self, point):
        if self.context_menu_blocked:
            logger.debug('Ignoring context menu request during mouse gesture')
            return
        self.context_menu.exec(self.mapToGlobal(point))

    def on_view_settings_changed(self):
        self.lock_button.apply_settings()
        self.update_titlebar_button()
        self.on_window_settings_changed()
        self.on_canvas_settings_changed()

    def rebuild_titlebar_button(self):
        """Replaces an existing tablet mode button of the title bar. It
        doesn't survive the native main window getting recreated.
        """

        if self.titlebar_button:
            self.titlebar_button.dispose()
            self.titlebar_button = None
            self.update_titlebar_button()

    def update_titlebar_button(self):
        """Creates or removes the tablet mode button of the title bar
        according to the settings.
        """

        wanted = (widgets.view_buttons.TitleBarButton.is_supported()
                  and self.settings.valueOrDefault(
                      'TabletMode/show_titlebar_button'))
        if self.titlebar_button and not wanted:
            self.titlebar_button.dispose()
            self.titlebar_button = None
        if wanted and not self.titlebar_button:
            self.titlebar_button = widgets.view_buttons.TitleBarButton(
                self.parent)
            self.titlebar_button.setChecked(self.tablet_mode)
            self.titlebar_button.clicked.connect(
                actions.actions['tablet_mode'].qaction.setChecked)

    def get_supported_image_formats(self, cls):
        formats = []

        for f in cls.supportedImageFormats():
            string = f'*.{f.data().decode()}'
            formats.extend((string, string.upper()))
        return ' '.join(formats)

    def get_view_center(self):
        return QtCore.QPoint(round(self.size().width() / 2),
                             round(self.size().height() / 2))

    def apply_undo_limit(self):
        """Apply the undo limit from the settings.

        Qt only allows changing the limit while the undo stack is empty,
        so a changed setting takes effect with the next new or opened
        scene.
        """
        if self.undo_stack.count() == 0:
            self.undo_stack.setUndoLimit(
                self.settings.valueOrDefault('Performance/undo_limit'))

    def clear_scene(self):
        logging.debug('Clearing scene...')
        self.stop_slideshow()
        self.focus_item = None
        self.exit_draw_mode(finish=False)
        self.cancel_active_modes()
        self.scene.clear()
        self.undo_stack.clear()
        self.apply_undo_limit()
        actions.actions.set_context(CONTEXT_GLOBAL)
        self.filename = None
        self.setTransform(QtGui.QTransform())

    def reset_previous_transform(self, toggle_item=None):
        if (self.previous_transform
                and self.previous_transform['toggle_item'] != toggle_item):
            self.previous_transform = None

    def fit_rect(self, rect, toggle_item=None):
        if toggle_item and self.previous_transform:
            logger.debug('Fit view: Reset to previous')
            self.setTransform(self.previous_transform['transform'])
            self.centerOn(self.previous_transform['center'])
            self.previous_transform = None
            return
        if toggle_item:
            self.previous_transform = {
                'toggle_item': toggle_item,
                'transform': QtGui.QTransform(self.transform()),
                'center': self.mapToScene(self.get_view_center()),
            }
        else:
            self.previous_transform = None

        logger.debug(f'Fit view: {rect}')
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.recalc_scene_rect()
        # It seems to be more reliable when we fit a second time
        # Sometimes a changing scene rect can mess up the fitting
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        logger.trace('Fit view done')

    def get_confirmation_unsaved_changes(self, msg):
        confirm = self.settings.valueOrDefault('Save/confirm_close_unsaved')
        if confirm and not self.undo_stack.isClean():
            answer = QtWidgets.QMessageBox.question(
                self,
                _('Discard unsaved changes?'),
                msg,
                QtWidgets.QMessageBox.StandardButton.Yes |
                QtWidgets.QMessageBox.StandardButton.Cancel)
            return answer == QtWidgets.QMessageBox.StandardButton.Yes

        return True

    def on_action_new_scene(self):
        confirm = self.get_confirmation_unsaved_changes(
            _('There are unsaved changes. '
              'Are you sure you want to open a new scene?'))
        if confirm:
            self.clear_scene()

    def on_action_fit_scene(self):
        self.fit_rect(self.scene.itemsBoundingRect())

    def on_action_fit_selection(self):
        self.fit_rect(self.scene.itemsBoundingRect(selection_only=True))

    def on_action_fullscreen(self, checked):
        if checked and self.window_locked:
            self.set_checked_silently('fullscreen', False)
            self.notify_window_locked()
            return
        if self.get_qaction('maximize_window').isChecked():
            self.set_checked_silently('maximize_window', False)
            self.normal_geometry = None
            self.apply_window_size_constraints()
        if checked:
            self.parent.showFullScreen()
        else:
            self.parent.showNormal()

    def on_action_always_on_top(self, checked):
        flags = {Qt.WindowType.WindowStaysOnTopHint: checked}
        if checked:
            self.stop_app_on_top()
            if self.get_qaction('always_on_bottom').isChecked():
                flags[Qt.WindowType.WindowStaysOnBottomHint] = False
                self.set_checked_silently('always_on_bottom', False)
                self.remember_window_mode('always_on_bottom', False)
        self.recreate_window(flags)
        self.remember_window_mode('always_on_top', checked)
        self.notify_window_mode(
            _('Always on top') if checked else _('Normal window'))

    def on_action_show_scrollbars(self, checked):
        if checked:
            self.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def on_action_show_menubar(self, checked):
        if checked:
            self.parent.setMenuBar(self.create_menubar())
        else:
            self.parent.setMenuBar(None)

    def on_action_show_titlebar(self, checked):
        if checked and self.titlebar_on_hover:
            self.titlebar_on_hover = False
            self.set_checked_silently('titlebar_on_hover', False)
            self.settings.setValue('Window/titlebar_on_hover', False)
            self.frame_controller.titlebar.hide()
        self.recreate_window(
            {Qt.WindowType.FramelessWindowHint: not checked})

    def on_action_tablet_mode(self, checked):
        logger.debug(f'Setting tablet mode to {checked}')
        self.tablet_mode = checked
        if self.titlebar_button:
            self.titlebar_button.setChecked(checked)

    def on_action_lock_items(self, checked):
        if checked:
            self.exit_draw_mode()
        self.scene.set_items_locked(checked)
        self.lock_button.setChecked(checked)
        # Undoing would change the locked items
        self.on_can_undo_changed(self.undo_stack.canUndo())
        self.on_can_redo_changed(self.undo_stack.canRedo())

    def on_action_move_window(self):
        if self.welcome_overlay.isHidden():
            self.on_action_movewin_mode()
        else:
            self.welcome_overlay.on_action_movewin_mode()

    def on_action_undo(self):
        logger.debug('Undo: %s' % self.undo_stack.undoText())
        self.cancel_active_modes()
        self.undo_stack.undo()

    def on_action_redo(self):
        logger.debug('Redo: %s' % self.undo_stack.redoText())
        self.cancel_active_modes()
        self.undo_stack.redo()

    def on_action_select_all(self):
        self.scene.select_all_items()

    def on_action_deselect_all(self):
        if self.is_slideshow_running():
            # Esc first ends the slideshow
            self.stop_slideshow()
            return
        self.scene.deselect_all_items()

    def on_action_delete_items(self):
        logger.debug('Deleting items...')
        self.cancel_active_modes()
        self.undo_stack.push(
            commands.DeleteItems(
                self.scene, self.scene.selectedItems(user_only=True)))

    def on_action_cut(self):
        logger.debug('Cutting items...')
        self.on_action_copy()
        self.undo_stack.push(
            commands.DeleteItems(
                self.scene, self.scene.selectedItems(user_only=True)))

    def on_action_raise_to_top(self):
        self.scene.raise_to_top()

    def on_action_lower_to_bottom(self):
        self.scene.lower_to_bottom()

    def on_action_normalize_height(self):
        self.scene.normalize_height()

    def on_action_normalize_width(self):
        self.scene.normalize_width()

    def on_action_normalize_size(self):
        self.scene.normalize_size()

    def on_action_arrange_horizontal(self):
        self.scene.arrange()

    def on_action_arrange_vertical(self):
        self.scene.arrange(vertical=True)

    def on_action_arrange_optimal(self):
        self.scene.arrange_optimal()

    def on_action_arrange_square(self):
        self.scene.arrange_square()

    def on_action_normalize_longest_side(self):
        self.scene.normalize_longest_side()

    def on_action_normalize_scale(self):
        self.scene.normalize_scale()

    def on_action_arrange_square_name(self):
        self.scene.arrange_square(order='name')

    def on_action_arrange_square_order(self):
        self.scene.arrange_square(order='order')

    def on_action_arrange_square_addition(self):
        self.scene.arrange_square(order='addition')

    def on_action_arrange_square_random(self):
        self.scene.arrange_square(order='random')

    def on_action_align_left(self):
        self.scene.align('left')

    def on_action_align_right(self):
        self.scene.align('right')

    def on_action_align_top(self):
        self.scene.align('top')

    def on_action_align_bottom(self):
        self.scene.align('bottom')

    def on_action_distribute_horizontal(self):
        self.scene.distribute()

    def on_action_distribute_vertical(self):
        self.scene.distribute(vertical=True)

    def on_action_stack(self):
        self.scene.stack()

    def on_action_duplicate(self):
        # Offset copies by a fixed distance on screen, regardless of zoom
        offset = QtCore.QPointF(20, 20) / self.get_scale()
        self.scene.duplicate_selection(offset)

    ZOOM_STEP = 250  # Corresponds to a zoom factor of 1.25

    def on_action_zoom_in(self):
        self.zoom(self.ZOOM_STEP, self.viewport().rect().center())

    def on_action_zoom_out(self):
        self.zoom(-self.ZOOM_STEP, self.viewport().rect().center())

    def on_action_zoom_actual(self):
        """Zoom to 100%, keeping the view's center."""
        center = self.mapToScene(self.viewport().rect().center())
        self.setTransform(QtGui.QTransform())
        self.scene.on_view_scale_change()
        self.recalc_scene_rect()
        self.centerOn(center)
        self.reset_previous_transform()

    def on_action_center_origin(self):
        self.centerOn(QtCore.QPointF(0, 0))
        self.reset_previous_transform()

    def on_action_change_opacity(self):
        images = list(filter(
            lambda item: item.is_image,
            self.scene.selectedItems(user_only=True)))
        widgets.ChangeOpacityDialog(self, images, self.undo_stack)

    def on_action_grayscale(self, checked):
        images = list(filter(
            lambda item: item.is_image,
            self.scene.selectedItems(user_only=True)))
        if images:
            self.undo_stack.push(
                commands.ToggleGrayscale(images, checked))

    def on_action_nearest_neighbor(self, checked):
        images = [item for item in self.scene.selectedItems(user_only=True)
                  if item.is_image]
        if images and any(i.nearest_neighbor != checked for i in images):
            self.undo_stack.push(
                commands.ToggleNearestNeighbor(images, checked))

    def on_action_grayscale_canvas(self, checked):
        self.scene.set_grayscale_canvas(checked)

    def on_action_group_items(self):
        if self.scene.group_selection():
            widgets.BeeNotification(
                self, _('Items in other groups have been left out'))

    def on_action_ungroup_items(self):
        self.scene.ungroup_selection()

    def on_action_add_to_group(self):
        if not self.scene.add_selection_to_group():
            widgets.BeeNotification(
                self, _('Select one group and the items to add to it'))

    def on_action_remove_from_group(self):
        self.scene.remove_selection_from_group()

    def on_action_group_enter(self):
        self.scene.enter_group()

    def on_action_group_exit(self):
        self.scene.exit_group()

    def on_action_group_title(self):
        group = self.scene.target_group()
        if group is not None:
            self.rename_item(group)

    def on_action_group_style(self):
        self.edit_group_style(self.scene.target_groups())

    def edit_group_style(self, groups):
        """Open the settings of the given groups; changes show up in
        the scene right away."""

        if groups:
            widgets.groups.GroupStyleDialog(self, groups, self.undo_stack)

    def edit_group_title_style(self, group):
        """Show the text options of a group's title."""

        self.close_title_panel()
        self.title_panel = widgets.groups.GroupTitlePanel(
            self, group, self.undo_stack)

    def close_title_editing(self):
        """Apply the edited title and close the text options."""

        if self.title_editor is not None:
            self.title_editor.finish()
        self.close_title_panel()

    def close_title_panel(self):
        panel, self.title_panel = self.title_panel, None
        if panel is not None:
            panel.close()

    def flush_title_panel(self):
        if self.title_panel is not None:
            self.title_panel.flush()

    def refresh_title_panel(self):
        if self.title_panel is not None:
            self.title_panel.refresh()
        if self.title_editor is not None:
            self.title_editor.update_geometry()

    def edit_group_title(self, group, scene_pos=None):
        """Edit the title of a group in place; the cursor goes to
        the given scene position, if any."""

        if self.title_editor is not None:
            self.title_editor.finish()
        if group.title_height() <= 0:
            return
        click = None
        if scene_pos is not None:
            click = self.mapFromScene(scene_pos)
        self.title_editor = widgets.groups.GroupTitleEditor(
            self, group, click)

    def apply_to_group_contents(self, method, **kwargs):
        """Call the given scene method with the contents of each
        target group, in one undo step."""

        groups = self.scene.target_groups()
        if len(groups) > 1:
            self.undo_stack.beginMacro('Organize group contents')
        for group in groups:
            getattr(self.scene, method)(
                items=self.scene.group_contents(group), **kwargs)
        if len(groups) > 1:
            self.undo_stack.endMacro()

    def on_action_group_focus(self):
        groups = self.scene.target_groups()
        if groups:
            self.fit_rect(self.scene.itemsBoundingRect(items=groups))

    def on_action_group_opacity(self):
        groups = self.scene.target_groups()
        if groups:
            widgets.ChangeOpacityDialog(self, groups, self.undo_stack)

    def on_action_group_color(self):
        groups = self.scene.target_groups()
        if not groups:
            return
        color = QtWidgets.QColorDialog.getColor(
            groups[0].background_color(), self, _('Group Color'),
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self.undo_stack.push(commands.ChangeGroupColor(
                groups, color.name(QtGui.QColor.NameFormat.HexArgb)))

    def on_action_parent_items(self):
        self.scene.parent_selection()

    def on_action_unparent_items(self):
        self.scene.unparent_selection()

    def on_action_lock_selected(self):
        items = self.scene.selectedItems(user_only=True)
        if items:
            self.scene.clearSelection()
            self.undo_stack.push(commands.SetItemsLocked(items, True))

    def on_action_unlock_all(self):
        items = [item for item in self.scene.items_for_save()
                 if item.locked]
        if items:
            self.undo_stack.push(commands.SetItemsLocked(items, False))

    def edit_comment(self, items):
        """Open the comment dialog for the given items."""

        if not items:
            return
        dialog = widgets.hierarchy.CommentDialog(self, items[0].comment)
        if dialog.exec():
            comment = dialog.comment()
            if any(item.comment != comment for item in items):
                self.undo_stack.push(commands.ChangeComment(items, comment))

    def on_action_edit_comment(self):
        self.edit_comment(self.scene.selectedItems(user_only=True))

    def on_action_rename_item(self):
        items = self.scene.selectedItems(user_only=True)
        if items:
            self.rename_item(items[0])

    def rename_item(self, item):
        name, ok = QtWidgets.QInputDialog.getText(
            self, _('Rename'), _('Name:'), text=item.display_name())
        if ok:
            name = name.strip()
            if name == item.default_name():
                name = ''
            if name != item.name:
                self.undo_stack.push(commands.RenameItem(item, name))

    def on_action_show_hierarchy(self, checked):
        if checked and self.hierarchy_dock is None:
            main = self.parent
            self.hierarchy_dock = widgets.hierarchy.HierarchyDock(self, main)
            if isinstance(main, QtWidgets.QMainWindow):
                main.addDockWidget(
                    Qt.DockWidgetArea.RightDockWidgetArea,
                    self.hierarchy_dock)
                main.resizeDocks([self.hierarchy_dock], [220],
                                 Qt.Orientation.Horizontal)
        if self.hierarchy_dock is not None:
            self.hierarchy_dock.setVisible(checked)

    def on_hierarchy_closed(self):
        self.set_checked_silently('show_hierarchy', False)

    # Text formatting

    def selected_text_items(self):
        """The text notes formatting applies to when not editing: All
        selected notes, including the ones inside selected groups."""

        result = []
        for item in self.scene.selected_top_items():
            for candidate in [item] + hierarchy.descendants(item):
                if (isinstance(candidate, BeeTextItem)
                        and candidate not in result):
                    result.append(candidate)
        return result

    def text_format_cursor(self):
        """The cursor the current formatting is read from."""

        item = self.scene.edit_item
        if item is not None:
            return item.textCursor()
        items = self.selected_text_items()
        if items:
            cursor = QtGui.QTextCursor(items[0].document())
            cursor.select(QtGui.QTextCursor.SelectionType.Document)
            return cursor
        return None

    def text_reference_format(self):
        cursor = self.text_format_cursor()
        if cursor is None:
            return None
        return textformat.reference_format(cursor)

    def refocus_edit_item(self):
        item = self.scene.edit_item
        if item is not None:
            self.setFocus()
            item.setFocus()

    def apply_text_format(self, operation, text='Format text'):
        """Apply a formatting operation (see myRef.textformat) to the
        note being edited, or to all selected notes."""

        item = self.scene.edit_item
        if item is not None:
            # Gets committed to the undo stack when leaving edit mode
            cursor = item.textCursor()
            operation(cursor)
            item.setTextCursor(cursor)
            self.refocus_edit_item()
            return
        items = self.selected_text_items()
        if not items:
            return
        self.undo_stack.beginMacro(text)
        for item in items:
            old = item.html()
            cursor = QtGui.QTextCursor(item.document())
            cursor.select(QtGui.QTextCursor.SelectionType.Document)
            operation(cursor)
            new = item.html()
            if new != old:
                self.undo_stack.push(commands.ChangeText(item, new, old))
        self.undo_stack.endMacro()

    def apply_toggle(self, factory):
        ref = self.text_reference_format()
        if ref is not None:
            self.apply_text_format(factory(ref))

    def ask_color(self, title, initial):
        color = QtWidgets.QColorDialog.getColor(
            initial, self, title,
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        self.refocus_edit_item()
        return color

    def ask_link(self):
        item = self.scene.edit_item
        current = ''
        if item is not None:
            current = item.textCursor().charFormat().anchorHref()
        url, ok = QtWidgets.QInputDialog.getText(
            self, _('Insert Link'), _('URL:'), text=current)
        self.refocus_edit_item()
        return url if ok else None

    def update_text_actions(self):
        self.actiongroup_set_enabled(
            'active_when_text_selected',
            self.scene.edit_item is not None
            or bool(self.selected_text_items()))

    def on_text_edit_mode_changed(self):
        self.update_text_actions()
        if self.scene.edit_item is not None:
            if self.text_toolbar is None:
                self.text_toolbar = widgets.textformat.NoteFormatToolbar(self)
            self.text_toolbar.show_for_item()
        elif self.text_toolbar is not None:
            self.text_toolbar.hide_toolbar()

    def on_action_text_bold(self):
        self.apply_toggle(textformat.bold)

    def on_action_text_italic(self):
        self.apply_toggle(textformat.italic)

    def on_action_text_underline(self):
        self.apply_toggle(textformat.underline)

    def on_action_text_strikeout(self):
        self.apply_toggle(textformat.strikeout)

    def on_action_text_color(self):
        ref = self.text_reference_format()
        if ref is None:
            return
        color = self.ask_color(_('Text Color'), ref.foreground().color())
        if color.isValid():
            self.apply_text_format(textformat.foreground(color))

    def on_action_text_highlight(self):
        ref = self.text_reference_format()
        if ref is None:
            return
        color = self.ask_color(_('Highlight Color'),
                               ref.background().color())
        if color.isValid():
            self.apply_text_format(textformat.highlight(color))

    def on_action_note_background(self):
        item = self.scene.edit_item
        items = [item] if item is not None else self.selected_text_items()
        if not items:
            return
        color = self.ask_color(_('Note Background'),
                               items[0].background_color())
        if color.isValid():
            self.undo_stack.push(commands.ChangeNoteBackground(
                items, color.name(QtGui.QColor.NameFormat.HexArgb)))

    def on_action_text_align_left(self):
        self.apply_text_format(textformat.align(Qt.AlignmentFlag.AlignLeft))

    def on_action_text_align_center(self):
        self.apply_text_format(
            textformat.align(Qt.AlignmentFlag.AlignHCenter))

    def on_action_text_align_right(self):
        self.apply_text_format(textformat.align(Qt.AlignmentFlag.AlignRight))

    def on_action_text_bullet_list(self):
        self.apply_text_format(textformat.bullet_list())

    def on_action_text_numbered_list(self):
        self.apply_text_format(textformat.numbered_list())

    def on_action_text_checklist(self):
        self.apply_text_format(textformat.checklist())

    def on_action_text_indent(self):
        self.apply_text_format(textformat.indent(1))

    def on_action_text_dedent(self):
        self.apply_text_format(textformat.indent(-1))

    def on_action_text_link(self):
        url = self.ask_link()
        if url:
            self.apply_text_format(textformat.link(url))

    def on_action_text_paste_plain(self):
        item = self.scene.edit_item
        if item is None:
            return
        text = QtWidgets.QApplication.clipboard().text()
        if text:
            cursor = item.textCursor()
            cursor.insertText(text)
            item.setTextCursor(cursor)

    def on_action_text_copy_format(self):
        cursor = self.text_format_cursor()
        if cursor is not None:
            textformat.copy_format(cursor)

    def on_action_text_paste_format(self):
        if textformat.copied_format is not None:
            self.apply_text_format(textformat.paste_format())

    def on_action_text_clear_format(self):
        self.apply_text_format(textformat.clear_format())

    def on_action_text_fixed_width(self):
        item = self.scene.edit_item
        items = [item] if item is not None else self.selected_text_items()
        if not items:
            return
        fixed = not items[0].has_fixed_width()
        if item is not None:
            # Gets committed to the undo stack when leaving edit mode
            item.set_text_width(
                QtWidgets.QGraphicsTextItem.boundingRect(item).width()
                if fixed else None)
            self.refocus_edit_item()
            return
        self.undo_stack.beginMacro('Change text width')
        for note in items:
            width = (QtWidgets.QGraphicsTextItem.boundingRect(note).width()
                     if fixed else -1)
            self.undo_stack.push(commands.ChangeText(
                note, note.html(), note.html(), width, note.textWidth()))
        self.undo_stack.endMacro()

    # Drawing

    def enter_draw_mode(self, item=None):
        """Start drawing; shapes go into ``item`` or into a new drawing
        item."""

        if self.scene.items_locked:
            return
        if self.draw_session:
            self.exit_draw_mode()
        logger.debug(f'Entering draw mode on {item}')
        if self.scene.edit_item:
            self.scene.edit_item.exit_edit_mode()
        self.cancel_active_modes()
        self.scene.clearSelection()
        self.draw_session = widgets.drawing.DrawSession(self, item)
        actions.actions.set_context(CONTEXT_DRAW)
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        if self.draw_toolbar is None:
            self.draw_toolbar = widgets.drawing.DrawToolbar(self)
        self.draw_toolbar.show_toolbar()

    def exit_draw_mode(self, finish=True):
        session = self.draw_session
        if session is None:
            return
        logger.debug('Exiting draw mode')
        self.draw_session = None
        item = session.finish() if finish else None
        actions.actions.set_context(CONTEXT_GLOBAL)
        self.viewport().unsetCursor()
        if self.draw_toolbar:
            self.draw_toolbar.hide()
        if item is not None:
            self.scene.select_items([item])

    def on_action_draw_mode(self):
        if self.draw_session:
            self.exit_draw_mode()
            return
        selected = self.scene.selectedItems(user_only=True)
        item = None
        if (len(selected) == 1
                and isinstance(selected[0], BeeDrawingItem)):
            item = selected[0]
        self.enter_draw_mode(item)

    def set_draw_tool(self, tool):
        if self.draw_session:
            self.draw_session.set_tool(tool)
            self.draw_toolbar.update_state()

    def on_action_draw_tool_pen(self):
        self.set_draw_tool('pen')

    def on_action_draw_tool_line(self):
        self.set_draw_tool('line')

    def on_action_draw_tool_arrow(self):
        self.set_draw_tool('arrow')

    def on_action_draw_tool_rect(self):
        self.set_draw_tool('rect')

    def on_action_draw_tool_ellipse(self):
        self.set_draw_tool('ellipse')

    def on_action_draw_tool_eraser(self):
        self.set_draw_tool('eraser')

    def open_link(self, url):
        """Open a link from a text note. Links to bee files are opened
        in myRef."""

        qurl = QtCore.QUrl(url)
        if qurl.isRelative():
            qurl = QtCore.QUrl.fromUserInput(url)
        if qurl.isLocalFile() and qurl.toLocalFile().lower().endswith(
                '.bee'):
            self.on_action_open_recent_file(qurl.toLocalFile())
            return
        logger.info(f'Opening link: {qurl.toString()}')
        QtGui.QDesktopServices.openUrl(qurl)

    def on_action_crop(self):
        self.scene.crop_items()

    def on_action_flip_horizontally(self):
        self.scene.flip_items(vertical=False)

    def on_action_flip_vertically(self):
        self.scene.flip_items(vertical=True)

    def on_action_reset_scale(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetScale(
            self.scene.selectedItems(user_only=True)))

    def on_action_reset_rotation(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetRotation(
            self.scene.selectedItems(user_only=True)))

    def on_action_reset_flip(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetFlip(
            self.scene.selectedItems(user_only=True)))

    def on_action_reset_crop(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetCrop(
            self.scene.selectedItems(user_only=True)))

    def on_action_reset_transforms(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetTransforms(
            self.scene.selectedItems(user_only=True)))

    def on_action_show_color_gamut(self):
        widgets.color_gamut.GamutDialog(self, self.scene.selectedItems()[0])

    def on_action_sample_color(self):
        self.cancel_active_modes()
        logger.debug('Entering sample color mode')
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.active_mode = self.SAMPLE_COLOR_MODE

        if self.scene.has_multi_selection():
            # We don't want to sample the multi select item, so
            # temporarily send it to the back:
            self.scene.multi_select_item.lower_behind_selection()

        pos = self.mapFromGlobal(self.cursor().pos())
        self.sample_color_widget = widgets.SampleColorWidget(
            self,
            pos,
            self.scene.sample_color_at(self.mapToScene(pos)))

    def on_items_loaded(self, value):
        logger.debug('On items loaded: add queued items')
        self.scene.add_queued_items()

    def on_loading_finished(self, filename, errors):
        if errors:
            QtWidgets.QMessageBox.warning(
                self,
                _('Problem loading file'),
                _('<p>Problem loading file %s</p>'
                  '<p>Not accessible or not a proper bee file</p>') % filename)
        else:
            self.filename = filename
            self.scene.add_queued_items()
            self.on_action_fit_scene()

    def on_action_open_recent_file(self, filename):
        confirm = self.get_confirmation_unsaved_changes(
            _('There are unsaved changes. '
              'Are you sure you want to open a new scene?'))
        if confirm:
            self.open_from_file(filename)

    def on_action_open_last_scene(self):
        files = self.settings.get_recent_files(existing_only=True)
        if not files:
            widgets.BeeNotification(self, _('No recently opened scenes'))
            return
        self.on_action_open_recent_file(files[0])

    def on_action_show_in_file_browser(self):
        if not self.filename:
            widgets.BeeNotification(
                self, _('The scene has not been saved yet'))
            return
        reveal_in_file_browser(self.filename)

    def open_from_file(self, filename):
        logger.info(f'Opening file {filename}')
        self.clear_scene()
        self.worker = fileio.ThreadedIO(
            fileio.load_bee, filename, self.scene)
        self.worker.progress.connect(self.on_items_loaded)
        self.worker.finished.connect(self.on_loading_finished)
        self.progress = widgets.BeeProgressDialog(
            _('Loading {filename}').format(filename=filename),
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_action_open(self):
        confirm = self.get_confirmation_unsaved_changes(
            _('There are unsaved changes. '
              'Are you sure you want to open a new scene?'))
        if not confirm:
            return

        self.cancel_active_modes()
        filename, f = QtWidgets.QFileDialog.getOpenFileName(
            parent=self,
            caption=_('Open file'),
            filter=_('{app} File (*.bee)').format(app=constants.APPNAME))
        if filename:
            filename = os.path.normpath(filename)
            self.open_from_file(filename)
            self.filename = filename

    def on_saving_finished(self, filename, errors):
        if errors:
            QtWidgets.QMessageBox.warning(
                self,
                _('Problem saving file'),
                _('<p>Problem saving file %s</p>'
                  '<p>File/directory not accessible</p>') % filename)
        else:
            self.filename = filename
            self.undo_stack.setClean()

    def do_save(self, filename, create_new):
        if not fileio.is_bee_file(filename):
            filename = f'{filename}.bee'
        self.worker = fileio.ThreadedIO(
            fileio.save_bee, filename, self.scene, create_new=create_new)
        self.worker.finished.connect(self.on_saving_finished)
        self.progress = widgets.BeeProgressDialog(
            _('Saving {filename}').format(filename=filename),
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_action_save_as(self):
        self.cancel_active_modes()
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, f = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption=_('Save file'),
            directory=directory,
            filter=_('{app} File (*.bee)').format(app=constants.APPNAME))
        if filename:
            self.do_save(filename, create_new=True)

    def on_action_save(self):
        self.cancel_active_modes()
        if not self.filename:
            self.on_action_save_as()
        else:
            self.do_save(self.filename, create_new=False)

    def on_action_export_scene(self):
        self.do_export_scene()

    def on_action_export_selection_as_scene(self):
        self.do_export_scene(items=self.scene.selectedItems(user_only=True))

    def do_export_scene(self, items=None):
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, formatstr = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption=_('Export Scene to Image'),
            directory=directory,
            filter=';;'.join((_('Image Files (*.png *.jpg *.jpeg *.svg)'),
                              'PNG (*.png)',
                              'JPEG (*.jpg *.jpeg)',
                              'SVG (*.svg)')))

        if not filename:
            return

        name, ext = os.path.splitext(filename)
        if not ext:
            ext = get_file_extension_from_format(formatstr)
            filename = f'{filename}.{ext}'
        logger.debug(f'Got export filename {filename}')

        exporter_cls = exporter_registry[ext]
        exporter = exporter_cls(self.scene, items=items)
        if not exporter.get_user_input(self):
            self.reselect(items)
            return
        exporter.prepare()
        self.reselect(items)

        self.worker = fileio.ThreadedIO(exporter.export, filename)
        self.worker.finished.connect(self.on_export_finished)
        self.progress = widgets.BeeProgressDialog(
            _('Exporting {filename}').format(filename=filename),
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_export_finished(self, filename, errors):
        if errors:
            err_msg = '</br>'.join(str(errors))
            QtWidgets.QMessageBox.warning(
                self,
                _('Problem writing file'),
                _('<p>Problem writing file {filename}</p><p>{errors}</p>')
                .format(filename=filename, errors=err_msg))

    def reselect(self, items):
        """Restore a selection that exporting has cleared."""
        for item in items or []:
            item.setSelected(True)

    def on_action_export_images(self):
        self.do_export_images()

    def on_action_export_selected_images(self):
        self.do_export_images(
            items=self.scene.selectedItems(user_only=True))

    def do_export_images(self, items=None):
        directory = os.path.dirname(self.filename) if self.filename else None
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            parent=self,
            caption=_('Export Images'),
            directory=directory)

        if not directory:
            return

        logger.debug(f'Got export directory {directory}')
        scene_name = (os.path.splitext(os.path.basename(self.filename))[0]
                      if self.filename else '')
        self.exporter = ImagesToDirectoryExporter(
            self.scene,
            directory,
            items=items,
            name_template=self.settings.valueOrDefault(
                'Export/name_template'),
            export_cropped=self.settings.valueOrDefault('Export/cropped'),
            scene_name=scene_name)
        self.worker = fileio.ThreadedIO(self.exporter.export)
        self.worker.user_input_required.connect(
            self.on_export_images_file_exists)
        self.worker.finished.connect(self.on_export_finished)
        self.progress = widgets.BeeProgressDialog(
            _('Exporting to {directory}').format(directory=directory),
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_export_images_file_exists(self, filename):
        dlg = widgets.ExportImagesFileExistsDialog(self, filename)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.exporter.handle_existing = dlg.get_answer()
            directory = self.exporter.dirname
            self.progress = widgets.BeeProgressDialog(
                _('Exporting to {directory}').format(directory=directory),
                worker=self.worker,
                parent=self)
            self.worker.start()

    def on_action_quit(self):
        confirm = self.get_confirmation_unsaved_changes(
            _('There are unsaved changes. Are you sure you want to quit?'))
        if confirm:
            logger.info('User quit. Exiting...')
            self.app.quit()

    def on_action_settings(self):
        widgets.settings.SettingsDialog(self)

    def on_action_keyboard_settings(self):
        widgets.controls.ControlsDialog(self)

    def on_action_help(self):
        widgets.HelpDialog(self)

    def on_action_about(self):
        website_txt = _('Visit the {app} website').format(
            app=constants.APPNAME)
        QtWidgets.QMessageBox.about(
            self,
            _('About {app}').format(app=constants.APPNAME),
            (f'<h2>{constants.APPNAME} {constants.VERSION}</h2>'
             f'<p>{_(constants.APPNAME_FULL)}</p>'
             f'<p>{constants.COPYRIGHT}</p>'
             f'<p><a href="{constants.WEBSITE}">'
             f'{website_txt}</a></p>'))

    def on_action_debuglog(self):
        widgets.DebugLogDialog(self)

    def on_insert_images_finished(self, new_scene, filename, errors):
        """Callback for when loading of images is finished.

        :param new_scene: True if the scene was empty before, else False
        :param filename: Not used, for compatibility only
        :param errors: List of filenames that couldn't be loaded
        """

        logger.debug('Insert images finished')
        if errors:
            errornames = [
                f'<li>{fn}</li>' for fn in errors]
            errornames = '<ul>%s</ul>' % '\n'.join(errornames)
            num = len(errors)
            msg = _('{num} image(s) could not be opened.<br/>').format(num=num)
            QtWidgets.QMessageBox.warning(
                self,
                _('Problem loading images'),
                msg + _(IMG_LOADING_ERROR_MSG) + errornames)
        self.scene.add_queued_items()
        self.scene.arrange_default()
        self.undo_stack.endMacro()
        if new_scene:
            self.on_action_fit_scene()

    def do_insert_images(self, filenames, pos=None):
        if not pos:
            pos = self.get_view_center()
        self.scene.deselect_all_items()
        self.undo_stack.beginMacro('Insert Images')
        self.worker = fileio.ThreadedIO(
            fileio.load_images,
            filenames,
            self.mapToScene(pos),
            self.scene)
        self.worker.progress.connect(self.on_items_loaded)
        self.worker.finished.connect(
            partial(self.on_insert_images_finished,
                    not self.scene.items()))
        self.progress = widgets.BeeProgressDialog(
            _('Loading images'),
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_action_insert_images(self):
        self.cancel_active_modes()
        formats = self.get_supported_image_formats(QtGui.QImageReader)
        logger.debug(f'Supported image types for reading: {formats}')
        filenames, f = QtWidgets.QFileDialog.getOpenFileNames(
            parent=self,
            caption=_('Select one or more images to open'),
            filter=_('Images ({formats})').format(formats=formats))
        self.do_insert_images(filenames)

    def on_action_insert_text(self):
        self.cancel_active_modes()
        # A note created while an image is selected gets attached to it:
        images = [i for i in self.scene.selection_history
                  if i.isSelected() and getattr(i, 'is_image', False)
                  and i.scene() is self.scene]
        item = BeeTextItem()
        pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))
        item.setScale(1 / self.get_scale())
        if not images:
            self.undo_stack.push(
                commands.InsertItems(self.scene, [item], pos))
            return
        self.undo_stack.beginMacro('Insert text')
        self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
        self.scene.move_in_hierarchy([item], images[0], text='Insert text')
        self.undo_stack.endMacro()

    def on_action_copy(self):
        logger.debug('Copying to clipboard...')
        self.cancel_active_modes()
        clipboard = QtWidgets.QApplication.clipboard()
        items = self.scene.selectedItems(user_only=True)

        # At the moment, we can only copy one image to the global
        # clipboard. (Later, we might create an image of the whole
        # selection for external copying.)
        items[0].copy_to_clipboard(clipboard)

        # However, we can copy all items to the internal clipboard:
        self.scene.copy_selection_to_internal_clipboard()

        # We set a marker for ourselves in the global clipboard so
        # that we know to look up the internal clipboard when pasting:
        mimedata = clipboard.mimeData()
        if mimedata is not None:
            mimedata.setData(
                'myRef/items', QtCore.QByteArray.number(len(items)))

    def on_action_copy_as_file(self):
        """Copy the selected images as temporary PNG files, for pasting
        into applications that only accept files (e.g. file browsers)."""

        images = [item for item in self.scene.selectedItems(user_only=True)
                  if item.is_image]
        if not images:
            return
        directory = os.path.join(
            QtCore.QStandardPaths.writableLocation(
                QtCore.QStandardPaths.StandardLocation.TempLocation),
            f'{constants.APPNAME}-clipboard')
        shutil.rmtree(directory, ignore_errors=True)
        os.makedirs(directory, exist_ok=True)

        urls = []
        used_names = set()
        for i, item in enumerate(items_in_order(images)):
            pixmap = item.pixmap()
            if item.grayscale:
                pixmap = item.get_grayscale_pixmap()
            pixmap = pixmap.copy(item.crop.toRect())
            if item.filename:
                name = os.path.splitext(os.path.basename(item.filename))[0]
            else:
                name = 'image'
            if name in used_names:
                name = f'{name}-{i + 1}'
            used_names.add(name)
            path = os.path.join(directory, f'{name}.png')
            pixmap.save(path, 'PNG')
            urls.append(QtCore.QUrl.fromLocalFile(path))
        logger.debug(f'Copied as files: {urls}')

        mimedata = QtCore.QMimeData()
        mimedata.setUrls(urls)
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setMimeData(mimedata)

    def on_action_paste(self):
        self.cancel_active_modes()
        logger.debug('Pasting from clipboard...')
        clipboard = QtWidgets.QApplication.clipboard()
        pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))

        # See if we need to look up the internal clipboard:
        # mimeData() is None if the clipboard is empty or unavailable
        # (e.g. another application holds it on Windows)
        mimedata = clipboard.mimeData()
        data = mimedata.data('myRef/items') if mimedata else None
        logger.debug(f'Custom data in clipboard: {data}')
        if data and self.scene.internal_clipboard:
            # Checking that internal clipboard exists since the user
            # may have opened a new scene since copying.
            self.scene.paste_from_internal_clipboard(pos)
            return

        img = clipboard.image()
        if not img.isNull():
            item = BeePixmapItem(img)
            self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
            if len(self.scene.items()) == 1:
                # This is the first image in the scene
                self.on_action_fit_scene()
            return
        if mimedata and mimedata.hasUrls():
            # Files copied in the file browser, or links
            self.do_insert_images(mimedata.urls(), self.mapFromScene(pos))
            return
        text = clipboard.text()
        if text and is_web_url(text.strip()) and len(text.split()) == 1:
            # The URL of an image or of a web page with images
            self.do_insert_images(
                [QtCore.QUrl(text.strip())], self.mapFromScene(pos))
            return
        if text:
            item = BeeTextItem(text)
            item.setScale(1 / self.get_scale())
            self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
            return

        msg = 'No image data or text in clipboard or image too big'
        logger.info(msg)
        widgets.BeeNotification(self, _(msg))

    def on_action_open_settings_dir(self):
        dirname = os.path.dirname(self.settings.fileName())
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(dirname))

    def on_selection_changed(self):
        logger.debug('Currently selected items: %s',
                     len(self.scene.selectedItems(user_only=True)))
        self.actiongroup_set_enabled('active_when_selection',
                                     self.scene.has_selection())
        self.actiongroup_set_enabled('active_when_single_image',
                                     self.scene.has_single_image_selection())
        self.actiongroup_set_enabled('active_when_group',
                                     bool(self.scene.target_groups()))
        self.update_text_actions()

        if self.scene.has_selection():
            item = self.scene.selectedItems(user_only=True)[0]
            grayscale = getattr(item, 'grayscale', False)
            actions.actions['grayscale'].qaction.setChecked(grayscale)
            nearest = getattr(item, 'nearest_neighbor', False)
            actions.actions['nearest_neighbor'].qaction.setChecked(nearest)
        self.viewport().repaint()

    def on_cursor_changed(self, cursor):
        if self.active_mode is None:
            self.viewport().setCursor(cursor)

    def on_cursor_cleared(self):
        if self.active_mode is None:
            self.viewport().unsetCursor()

    def recalc_scene_rect(self):
        """Resize the scene rectangle so that it is always one view width
        wider than all items' bounding box at each side and one view
        width higher on top and bottom. This gives the impression of
        an infinite canvas."""

        if self.previous_transform:
            return
        logger.trace('Recalculating scene rectangle...')
        try:
            topleft = self.mapFromScene(
                self.scene.itemsBoundingRect().topLeft())
            topleft = self.mapToScene(QtCore.QPoint(
                topleft.x() - self.size().width(),
                topleft.y() - self.size().height()))
            bottomright = self.mapFromScene(
                self.scene.itemsBoundingRect().bottomRight())
            bottomright = self.mapToScene(QtCore.QPoint(
                bottomright.x() + self.size().width(),
                bottomright.y() + self.size().height()))
            self.setSceneRect(QtCore.QRectF(topleft, bottomright))
        except OverflowError:
            logger.info('Maximum scene size reached')
        logger.trace('Done recalculating scene rectangle')

    def get_zoom_size(self, func):
        """Calculates the size of all items' bounding box in the view's
        coordinates.

        This helps ensure that we never zoom out too much (scene
        becomes so tiny that items become invisible) or zoom in too
        much (causing overflow errors).

        :param func: Function which takes the width and height as
            arguments and turns it into a number, for ex. ``min`` or ``max``.
        """

        topleft = self.mapFromScene(
            self.scene.itemsBoundingRect().topLeft())
        bottomright = self.mapFromScene(
            self.scene.itemsBoundingRect().bottomRight())
        return func(bottomright.x() - topleft.x(),
                    bottomright.y() - topleft.y())

    def scale(self, *args, **kwargs):
        super().scale(*args, **kwargs)
        self.scene.on_view_scale_change()
        self.recalc_scene_rect()

    def get_scale(self):
        return self.transform().m11()

    def pan(self, delta):
        if not self.scene.items():
            logger.debug('No items in scene; ignore pan')
            return

        hscroll = self.horizontalScrollBar()
        hscroll.setValue(int(hscroll.value() + delta.x()))
        vscroll = self.verticalScrollBar()
        vscroll.setValue(int(vscroll.value() + delta.y()))

    def zoom(self, delta, anchor):
        if not self.scene.items():
            logger.debug('No items in scene; ignore zoom')
            return

        # We calculate where the anchor is before and after the zoom
        # and then move the view accordingly to keep the anchor fixed
        # We can't use QGraphicsView's AnchorUnderMouse since it
        # uses the current cursor position while we need the initial mouse
        # press position for zooming with Ctrl + Middle Drag
        anchor = QtCore.QPoint(round(anchor.x()),
                               round(anchor.y()))
        ref_point = self.mapToScene(anchor)
        if delta == 0:
            return
        factor = 1 + abs(delta / 1000)
        if delta > 0:
            if self.get_zoom_size(max) < 10000000:
                self.scale(factor, factor)
            else:
                logger.debug('Maximum zoom size reached')
                return
        else:
            if self.get_zoom_size(min) > 50:
                self.scale(1/factor, 1/factor)
            else:
                logger.debug('Minimum zoom size reached')
                return

        self.pan(self.mapFromScene(ref_point) - anchor)
        self.reset_previous_transform()

    def wheelEvent(self, event):
        self.hide_unlock_button()
        action, inverted\
            = self.keyboard_settings.mousewheel_action_for_event(event)

        delta = event.angleDelta().y()
        if inverted:
            delta = delta * -1

        if action == 'zoom':
            self.zoom(delta, event.position())
            event.accept()
            return
        if action == 'pan_horizontal':
            self.pan(QtCore.QPointF(0, 0.5 * delta))
            event.accept()
            return
        if action == 'pan_vertical':
            self.pan(QtCore.QPointF(0.5 * delta, 0))
            event.accept()
            return

    def mouse_action_for_event(self, event):
        """The action for the given mouse press.

        While tablet mode is on, its controls take precedence over the
        regular ones.
        """

        if self.tablet_mode:
            for action in ('pan', 'zoom'):
                binding = self.settings.valueOrDefault(f'TabletMode/{action}')
                if mouse_binding_matches_event(binding, event):
                    inverted = (action == 'zoom'
                                and self.settings.valueOrDefault(
                                    'TabletMode/zoom_inverted'))
                    return action, inverted
        action, inverted = self.keyboard_settings.mouse_action_for_event(
            event)
        if action == 'movewindow' and self.scene.items_locked:
            # While locked, the right mouse button zooms
            locked_action, locked_inverted = (
                self.locked_mouse_action_for_event(event))
            if locked_action is not None:
                return locked_action, locked_inverted
        if (action == 'movewindow'
                and event.button() == Qt.MouseButton.RightButton
                and self.window_fills_screen()):
            # A maximized window can't be moved; pan instead
            return 'pan', False
        if action is None and self.scene.items_locked:
            action, inverted = self.locked_mouse_action_for_event(event)
        return action, inverted

    def window_fills_screen(self):
        window = self.window()
        return bool(window and (window.isMaximized()
                                or window.isFullScreen()))

    def locked_mouse_action_for_event(self, event):
        """While items are locked, the left and right mouse buttons are
        free, so they pan and zoom without any modifier keys.
        """

        if event.modifiers() != Qt.KeyboardModifier.NoModifier:
            return None, None
        if event.button() == Qt.MouseButton.LeftButton:
            return 'pan', False
        if event.button() == Qt.MouseButton.RightButton:
            return 'zoom', False
        return None, None

    def start_right_gesture(self, event):
        """Pan and zoom can be bound to the right mouse button, which also
        opens the context menu. To be able to tell them apart, we only
        open the context menu when the mouse hasn't been dragged.
        """

        if event.button() == Qt.MouseButton.RightButton:
            self.context_menu_blocked = True
            self.right_gesture_start = event.position()
            self.right_gesture_moved = False

    def is_right_click_pending(self, pos):
        """Whether a right mouse button press hasn't turned into a drag yet."""

        if self.right_gesture_start is None or self.right_gesture_moved:
            return False
        distance = (pos - self.right_gesture_start).manhattanLength()
        if distance < QtWidgets.QApplication.startDragDistance():
            return True
        self.right_gesture_moved = True
        return False

    def end_right_gesture(self, event):
        if self.right_gesture_start is None:
            return
        menu_pos = None
        if not self.right_gesture_moved:
            menu_pos = event.position().toPoint()
        self.right_gesture_start = None
        # Depending on the platform, Qt requests the context menu either
        # on mouse press or directly after this mouse release. We ignore
        # these requests and open the menu ourselves if necessary.
        QtCore.QTimer.singleShot(
            0, partial(self.on_right_gesture_ended, menu_pos))

    def on_right_gesture_ended(self, menu_pos):
        self.context_menu_blocked = False
        if menu_pos is not None:
            self.on_context_menu(menu_pos)

    def mousePressEvent(self, event):
        if (self.is_slideshow_running()
                and event.button() != Qt.MouseButton.RightButton):
            self.stop_slideshow()
        self.hide_unlock_button()
        if self.mousePressEventMainControls(event):
            return

        if self.active_mode == self.SAMPLE_COLOR_MODE:
            if (event.button() == Qt.MouseButton.LeftButton):
                color = self.scene.sample_color_at(
                    self.mapToScene(event.pos()))
                if color:
                    name = qcolor_to_hex(color)
                    clipboard = QtWidgets.QApplication.clipboard()
                    clipboard.setText(name)
                    self.scene.internal_clipboard = []
                    logger.debug(f'Copied color to clipboard: {name}')
                    widgets.BeeNotification(
                        self,
                        _('Copied color to clipboard: {name}').format(
                            name=name))
                else:
                    logger.debug('No color found')
            self.cancel_sample_color_mode()
            event.accept()
            return

        action, inverted = self.mouse_action_for_event(event)

        if action == 'zoom':
            self.active_mode = self.ZOOM_MODE
            self.event_start = event.position()
            self.event_anchor = event.position()
            self.event_inverted = inverted
            self.start_right_gesture(event)
            event.accept()
            return

        if action == 'pan':
            logger.trace('Begin pan')
            if self.scene.items_locked:
                # The scene doesn't get this press, so do what it would
                # do: clicking another item forgets the previous fit
                item = self.itemAt(event.pos())
                if item:
                    self.reset_previous_transform(toggle_item=item)
            self.active_mode = self.PAN_MODE
            self.event_start = event.position()
            self.start_right_gesture(event)
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            # ClosedHandCursor and OpenHandCursor don't work, but I
            # don't know if that's only on my system or a general
            # problem. It works with other cursors.
            event.accept()
            return

        if self.drag_tools_press(event, action, inverted):
            event.accept()
            return

        if self.draw_session:
            if event.button() == Qt.MouseButton.LeftButton:
                self.draw_session.press(
                    self.mapToScene(event.position().toPoint()),
                    event.modifiers())
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.draw_session:
            # Treat as a normal click so that quick strokes don't get
            # lost and the scene doesn't start editing items
            self.mousePressEvent(event)
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_right_click_pending(event.position()):
            event.accept()
            return

        if self.drag_tools_move(event):
            return

        if self.active_mode == self.PAN_MODE:
            self.reset_previous_transform()
            pos = event.position()
            self.pan(self.event_start - pos)
            self.event_start = pos
            event.accept()
            return

        if self.active_mode == self.ZOOM_MODE:
            self.reset_previous_transform()
            pos = event.position()
            delta = (self.event_start - pos).y()
            if self.event_inverted:
                delta *= -1
            self.event_start = pos
            self.zoom(delta * 20, self.event_anchor)
            event.accept()
            return

        if self.draw_session and self.draw_session.active:
            self.draw_session.move(
                self.mapToScene(event.position().toPoint()),
                event.modifiers())
            event.accept()
            return

        if self.active_mode == self.SAMPLE_COLOR_MODE:
            self.sample_color_widget.update(
                event.position(),
                self.scene.sample_color_at(self.mapToScene(event.pos())))
            event.accept()
            return

        if self.mouseMoveEventMainControls(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.end_right_gesture(event)
        if self.drag_tools_release(event):
            return
        if self.active_mode == self.PAN_MODE:
            logger.trace('End pan')
            self.viewport().unsetCursor()
            self.active_mode = None
            event.accept()
            return
        if self.active_mode == self.ZOOM_MODE:
            self.active_mode = None
            event.accept()
            return
        if self.draw_session and self.draw_session.active:
            self.draw_session.release(
                self.mapToScene(event.position().toPoint()),
                event.modifiers())
            event.accept()
            return
        if self.mouseReleaseEventMainControls(event):
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        old_size = event.oldSize()
        old_center = self.mapToScene(
            QtCore.QPoint(old_size.width() // 2, old_size.height() // 2))
        super().resizeEvent(event)
        self.scale_scene_on_resize(old_size, event.size(), old_center)
        self.recalc_scene_rect()
        self.welcome_overlay.resize(self.size())
        if self.title_editor is not None:
            self.title_editor.update_geometry()
        self.lock_button.update_position()
        if self.draw_toolbar and self.draw_toolbar.isVisible():
            self.draw_toolbar.update_position()

    def event(self, event):
        # Esc is also the shortcut for deselecting; while drawing or
        # editing text it must reach keyPressEvent instead.
        if (event.type() == QtCore.QEvent.Type.ShortcutOverride
                and event.key() == Qt.Key.Key_Escape
                and (self.draw_session
                     or actions.actions.active_context != 'global')):
            event.accept()
            return True
        # Return confirms drawing and cropping instead of triggering
        # "Edit item"
        if (event.type() == QtCore.QEvent.Type.ShortcutOverride
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and (self.draw_session or self.scene.crop_item)):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        self.drag_tools_key_press(event)
        if self.keyPressEventMainControls(event):
            return
        if self.active_mode == self.SAMPLE_COLOR_MODE:
            self.cancel_sample_color_mode()
            event.accept()
            return
        if self.draw_session and event.key() in (
                Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.exit_draw_mode()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        self.drag_tools_key_release(event)
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self.held_keys.clear()
        super().focusOutEvent(event)


def _scoped_callback(method, kwargs):
    def callback(self):
        self.apply_to_group_contents(method, **kwargs)
    return callback


def _group_aware_callback(original, method, kwargs):
    """With a single group selected, the regular organizing actions
    (and thus their shortcuts) affect the group's contents."""

    def callback(self):
        group = self.scene.selected_group()
        if group is not None:
            self.apply_to_group_contents(method, **kwargs)
        else:
            original(self)
    return callback


for _action_id, _method, _kwargs in actions.SCOPED_ACTIONS:
    setattr(BeeGraphicsView,
            f'on_action_{actions.scoped_id(_action_id)}',
            _scoped_callback(_method, _kwargs))
    _name = f'on_action_{_action_id}'
    setattr(BeeGraphicsView, _name, _group_aware_callback(
        getattr(BeeGraphicsView, _name), _method, _kwargs))
