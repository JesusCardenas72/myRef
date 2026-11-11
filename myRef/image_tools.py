# This file is part of myRef.
#
# myRef is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# myRef is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with myRef.  If not, see <https://www.gnu.org/licenses/>.

"""Image features of the view that PureRef has in its Images menu:
editing the selected item, stepping the focus through the images,
the slideshow, opening an image's source and replacing an image.
"""

import logging
import os.path
import sys

from PyQt6 import QtCore, QtGui, QtWidgets

from myRef.actions.actions import actions
from myRef import commands
from myRef.fileio.image import load_image
from myRef.i18n import _
from myRef.items import BeeGroupItem, BeePixmapItem, items_in_order
from myRef import widgets


logger = logging.getLogger(__name__)


def reveal_in_file_browser(path):
    """Open the system's file browser with the given file selected."""

    path = os.path.abspath(path)
    logger.debug(f'Showing in file browser: {path}')
    if sys.platform == 'win32':
        QtCore.QProcess.startDetached(
            'explorer', ['/select,', os.path.normpath(path)])
    elif sys.platform == 'darwin':
        QtCore.QProcess.startDetached('open', ['-R', path])
    else:
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(os.path.dirname(path)))


def is_web_url(text):
    return text.lower().startswith(('http://', 'https://'))


class ImageToolsMixin:

    def init_image_tools(self):
        self.focus_item = None
        self.slideshow_items = []
        self.slideshow_timer = QtCore.QTimer(self)
        self.slideshow_timer.timeout.connect(self.slideshow_next)
        self.unlock_button = None
        self.unlock_item = None

    # Edit item (Return)

    def on_action_edit_item(self):
        """Start editing the selected note or drawing, or enter the
        selected group."""

        if self.scene.items_locked:
            return
        items = self.scene.selectedItems(user_only=True)
        if len(items) != 1:
            return
        item = items[0]
        if isinstance(item, BeeGroupItem):
            self.scene.enter_group()
            return
        if getattr(item, 'is_editable', False):
            item.enter_edit_mode()
            if isinstance(item, QtWidgets.QGraphicsTextItem):
                # Unlike double-clicking, there's no click that puts
                # the text cursor, so it goes to the end of the text
                item.setFocus()
                cursor = item.textCursor()
                cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
                item.setTextCursor(cursor)
        elif getattr(item, 'missing_link', False):
            self.relink_items([item])

    # Focus next/previous image (Right/Left)

    def focusable_images(self):
        """The images to step through, in hierarchy order."""

        if self.slideshow_items:
            return [i for i in self.slideshow_items if i.scene() is self.scene]
        return items_in_order(
            item for item in self.scene.items_for_save()
            if getattr(item, 'is_image', False) and item.isVisible())

    def focus_image(self, item):
        self.focus_item = item
        self.previous_transform = None
        self.fit_rect(self.scene.itemsBoundingRect(items=[item]))

    def step_focus(self, step):
        images = self.focusable_images()
        if not images:
            return
        current = self.focus_item
        if current not in images:
            selected = [i for i in images if i.isSelected()]
            current = selected[0] if selected else None
        if current in images:
            index = (images.index(current) + step) % len(images)
        else:
            index = 0 if step > 0 else len(images) - 1
        self.focus_image(images[index])

    def on_action_focus_next(self):
        self.step_focus(1)
        if self.slideshow_items:
            self.slideshow_timer.start()

    def on_action_focus_previous(self):
        self.step_focus(-1)
        if self.slideshow_items:
            self.slideshow_timer.start()

    # Slideshow (Alt+S)

    def is_slideshow_running(self):
        return bool(self.slideshow_items)

    def start_slideshow(self):
        selected = [item for item in self.scene.selectedItems(user_only=True)
                    if getattr(item, 'is_image', False)]
        if len(selected) < 2:
            selected = [item for item in self.scene.items_for_save()
                        if getattr(item, 'is_image', False)]
        if not selected:
            widgets.BeeNotification(self, _('No images for a slideshow'))
            self.set_slideshow_checked(False)
            return
        self.slideshow_items = items_in_order(selected)
        seconds = self.settings.valueOrDefault('Images/slideshow_interval')
        self.slideshow_timer.setInterval(int(seconds * 1000))
        logger.debug(f'Starting slideshow: {len(selected)} images, '
                     f'{seconds} s each')
        self.focus_item = None
        self.focus_image(self.slideshow_items[0])
        self.slideshow_timer.start()
        self.set_slideshow_checked(True)
        widgets.BeeNotification(
            self, _('Slideshow started (Alt+S or Esc to stop)'))

    def stop_slideshow(self):
        if not self.slideshow_items:
            return
        logger.debug('Stopping slideshow')
        self.slideshow_timer.stop()
        self.slideshow_items = []
        self.set_slideshow_checked(False)

    def set_slideshow_checked(self, value):
        qaction = actions['slideshow'].qaction
        if qaction and qaction.isChecked() != value:
            qaction.blockSignals(True)
            qaction.setChecked(value)
            qaction.blockSignals(False)

    def slideshow_next(self):
        if not self.focusable_images():
            self.stop_slideshow()
            return
        self.step_focus(1)

    def on_action_slideshow(self, checked):
        if checked:
            self.start_slideshow()
        else:
            self.stop_slideshow()

    # Open source (Ctrl+Shift+O)

    def selected_images(self):
        return [item for item in self.scene.selectedItems(user_only=True)
                if getattr(item, 'is_image', False)]

    def on_action_open_source(self):
        images = self.selected_images()
        if not images:
            return
        filename = images[0].filename
        if not filename:
            widgets.BeeNotification(
                self, _('This image has no source (it was pasted)'))
            return
        if is_web_url(filename):
            logger.debug(f'Opening source URL: {filename}')
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(filename))
        elif os.path.exists(filename):
            reveal_in_file_browser(filename)
        else:
            widgets.BeeNotification(
                self,
                _('Source file not found: {filename}').format(
                    filename=filename))

    # Replace image

    def ask_image_file(self, caption):
        formats = self.get_supported_image_formats(QtGui.QImageReader)
        filename, f = QtWidgets.QFileDialog.getOpenFileName(
            parent=self,
            caption=caption,
            filter=_('Images ({formats})').format(formats=formats))
        return filename

    @staticmethod
    def replacement_change(item, img, filename):
        """The ReplacePixmaps change that shows ``img`` in place of the
        item: Same center and the same length of the longest side."""

        old_rect = item.crop
        old_side = max(old_rect.width(), old_rect.height()) * item.scale()
        new_side = max(img.width(), img.height()) or 1
        scale = old_side / new_side
        return {
            'item': item,
            'pixmap': QtGui.QPixmap.fromImage(img),
            'filename': filename,
            'crop': None,
            'scale': scale,
            'center': item.mapToScene(old_rect.center()),
            'linked': False,
        }

    def on_action_replace_image(self):
        images = self.selected_images()
        if len(images) != 1:
            return
        filename = self.ask_image_file(_('Select the replacement image'))
        if not filename:
            return
        img, filename = load_image(filename)
        if img.isNull():
            QtWidgets.QMessageBox.warning(
                self,
                _('Problem loading images'),
                _('Image could not be loaded: {filename}\n').format(
                    filename=filename))
            return
        self.undo_stack.push(commands.ReplacePixmaps(
            [self.replacement_change(images[0], img, filename)],
            text='Replace image'))

    # Unlocking a locked item by clicking on it

    def show_unlock_button(self, item):
        """Show a button in the lower right corner of a locked item that
        unlocks it."""

        if self.unlock_button is None:
            button = QtWidgets.QToolButton(self.viewport())
            button.setText(_('Unlock'))
            button.setToolTip(_('Unlock this item (Alt+L locks it again)'))
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                'QToolButton { background-color: rgba(30, 30, 30, 220);'
                ' color: #f0f0f0; border: 1px solid #555555;'
                ' padding: 3px 8px; }'
                'QToolButton:hover { background-color: #3d6fb4; }')
            button.clicked.connect(self.on_unlock_button_clicked)
            self.unlock_button = button
        self.unlock_item = item
        rect = self.scene.itemsBoundingRect(items=[item])
        corner = self.mapFromScene(rect.bottomRight())
        button = self.unlock_button
        button.adjustSize()
        viewport = self.viewport().rect()
        x = min(corner.x(), viewport.right()) - button.width() - 4
        y = min(corner.y(), viewport.bottom()) - button.height() - 4
        button.move(max(0, x), max(0, y))
        button.show()
        button.raise_()

    def hide_unlock_button(self):
        if self.unlock_button is not None:
            self.unlock_button.hide()
        self.unlock_item = None

    def on_unlock_button_clicked(self):
        item = self.unlock_item
        self.hide_unlock_button()
        if item is not None and item.scene() is self.scene and item.locked:
            self.undo_stack.push(commands.SetItemsLocked([item], False))
            self.scene.clearSelection()
            item.setSelected(True)

    # Relinking missing images (Ctrl+Alt+Shift+R)

    def missing_link_items(self):
        return [item for item in self.scene.items()
                if getattr(item, 'missing_link', False)]

    def on_action_relink_missing_images(self):
        items = self.missing_link_items()
        if not items:
            widgets.BeeNotification(self, _('No missing images'))
            return
        self.relink_items(items)

    @staticmethod
    def relinked_item(error_item, img, filename):
        """A new image item with the data of the missing image."""

        data = dict(error_item.original_data or {})
        item_data = dict(data.get('data') or {})
        item_data['filename'] = filename
        data['data'] = item_data
        data['item'] = BeePixmapItem(img, filename)
        item = BeePixmapItem.create_from_data(**dict(data))
        data.pop('item', None)
        data['save_id'] = error_item.original_save_id
        data.pop('parent_id', None)
        item.update_from_data(**data)
        item.pending_parent_id = None
        item.linked = True
        # The bee file has no image data for this item yet
        item.pixmap_dirty = True
        return item

    def relink_items(self, items):
        """Ask for the new location of missing linked images.

        A single image is chosen directly; for several images, a folder
        is searched (including subfolders) for files with the same names.
        """

        if len(items) == 1:
            original = (items[0].original_data or {}).get('data', {})
            name = os.path.basename(original.get('filename') or '')
            filename = self.ask_image_file(
                _('Select the new location of {name}').format(name=name))
            found = {items[0]: filename} if filename else {}
        else:
            directory = QtWidgets.QFileDialog.getExistingDirectory(
                self, _('Select a folder containing the missing images'))
            if not directory:
                return
            found = self.find_missing_files(items, directory)

        pairs = []
        for item, filename in found.items():
            img, filename = load_image(filename)
            if img.isNull():
                continue
            pairs.append((item, self.relinked_item(item, img, filename)))
        if pairs:
            self.undo_stack.push(commands.SwapItems(self.scene, pairs))
        missing = len(items) - len(pairs)
        if len(items) > 1 or missing:
            widgets.BeeNotification(
                self,
                _('Relinked {found} image(s), {missing} still missing').format(
                    found=len(pairs), missing=missing))

    @staticmethod
    def find_missing_files(items, directory):
        wanted = {}
        for item in items:
            original = (item.original_data or {}).get('data', {})
            name = os.path.basename(original.get('filename') or '')
            if name:
                wanted.setdefault(name.casefold(), []).append(item)
        found = {}
        for root, dirs, files in os.walk(directory):
            for name in files:
                for item in wanted.pop(name.casefold(), []):
                    found[item] = os.path.join(root, name)
            if not wanted:
                break
        return found

    # Manage images (Ctrl+Shift+J)

    def on_action_manage_images(self):
        self.cancel_active_modes()
        images = self.selected_images() or [
            item for item in self.scene.items_for_save()
            if getattr(item, 'is_image', False)]
        if not images:
            widgets.BeeNotification(self, _('No images in the scene'))
            return
        dialog = widgets.manage_images.ManageImagesDialog(
            self, items_in_order(images), self.scene_name())
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        changes, errors = dialog.build_changes()
        if errors:
            QtWidgets.QMessageBox.warning(
                self, _('Manage images'), '\n'.join(errors))
        if changes:
            self.undo_stack.push(
                commands.ReplacePixmaps(changes, text='Manage images'))
            widgets.BeeNotification(
                self, _('{num} image(s) changed').format(num=len(changes)))

    def scene_name(self):
        if self.filename:
            return os.path.splitext(os.path.basename(self.filename))[0]
        return 'scene'
