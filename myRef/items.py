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

"""Classes for items that are added to the scene by the user (images,
text).
"""

from collections import defaultdict
from functools import cached_property
import logging
import math
import os.path

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef import commands
from myRef import drawing
from myRef import group_style
from myRef import hierarchy
from myRef import textformat
from myRef.actions.actions import (
    actions, CONTEXT_GLOBAL, CONTEXT_TEXT_EDIT)
from myRef.config import BeeSettings
from myRef.constants import COLORS
from myRef.i18n import _
from myRef.selection import SelectableMixin


logger = logging.getLogger(__name__)

item_registry = {}


def register_item(cls):
    item_registry[cls.TYPE] = cls
    return cls


def sort_by_filename(items):
    """Order items by filename.

    Items with a filename (ordered by filename) first, then items
    without a filename but with a save_id follow (ordered by
    save_id), then remaining items in the order that they have
    been inserted into the scene.
    """

    items_by_filename = []
    items_by_save_id = []
    items_remaining = []

    for item in items:
        if getattr(item, 'filename', None):
            items_by_filename.append(item)
        elif getattr(item, 'save_id', None):
            items_by_save_id.append(item)
        else:
            items_remaining.append(item)

    items_by_filename.sort(key=lambda x: x.filename)
    items_by_save_id.sort(key=lambda x: x.save_id)
    return items_by_filename + items_by_save_id + items_remaining


def sort_by_name(items):
    """Order items by their name.

    Items named by the user are ordered by that name, unnamed items by
    the name of their file (without the directory). Items with neither
    follow in their hierarchy order.
    """

    def name_of(item):
        if getattr(item, 'name', ''):
            return item.name
        filename = getattr(item, 'filename', None)
        if filename:
            return os.path.basename(filename)
        return None

    named = [item for item in items if name_of(item)]
    unnamed = [item for item in items if not name_of(item)]
    named.sort(key=lambda item: name_of(item).casefold())
    return named + items_in_order(unnamed)


def sort_by_addition(items):
    """Order items by the time they were added to the scene.

    Items without that information (e.g. from older bee files) come
    first, ordered by save_id.
    """

    def key(item):
        added_at = getattr(item, 'added_at', None)
        save_id = getattr(item, 'save_id', None)
        return (added_at is not None,
                added_at or 0,
                save_id if save_id is not None else float('inf'))

    return sorted(items, key=key)


def sibling_order(items):
    """Order items that share the same parent.

    Items with a ``sort_order`` come first, ordered by it; the
    remaining items follow, ordered by ``sort_by_filename``.
    """

    with_order = []
    without_order = []
    for item in items:
        if getattr(item, 'sort_order', None) is not None:
            with_order.append(item)
        else:
            without_order.append(item)

    with_order.sort(key=lambda x: x.sort_order)
    return with_order + sort_by_filename(without_order)


def items_in_order(items):
    """Order items in the canonical (hierarchy) order.

    This is the order used wherever the order of items matters but
    isn't chosen explicitly by the user, e.g. for exporting. It's the
    order of the hierarchy panel: Parents come before their children,
    siblings are ordered by ``sibling_order``.
    """

    items = list(items)
    chains = {}
    nodes = set()
    for item in items:
        chain = list(reversed(hierarchy.ancestors(item))) + [item]
        chains[item] = chain
        nodes.update(chain)

    by_parent = defaultdict(list)
    for node in nodes:
        by_parent[node.parentItem()].append(node)
    rank = {}
    for siblings in by_parent.values():
        for i, node in enumerate(sibling_order(siblings)):
            rank[node] = i

    return sorted(items,
                  key=lambda item: [rank[node] for node in chains[item]])


class BeeItemMixin(SelectableMixin):
    """Base for all items added by the user."""

    #: Locked by the user (Alt+L); saved in the bee file
    locked = False
    #: The whole scene is locked (View > Lock Images); not saved
    globally_locked = False
    #: Comment as HTML
    comment = ''
    #: Name given by the user; empty for the default name
    name = ''

    def default_name(self):
        return str(self)

    def display_name(self):
        """The name shown in the hierarchy panel."""
        return self.name or self.default_name()

    def in_closed_group(self):
        """Whether one of the item's ancestors is a closed group.

        Children of closed groups can't be selected on their own; a
        click on them selects the group instead.
        """
        return any(isinstance(a, BeeGroupItem) and not a.is_open
                   for a in hierarchy.ancestors(self))

    def is_interactive(self):
        """Whether the item can be selected and moved."""
        return not (self.globally_locked
                    or self.locked
                    or self.in_closed_group())

    def update_flags(self):
        flag = QtWidgets.QGraphicsItem.GraphicsItemFlag
        interactive = self.is_interactive()
        self.setFlag(flag.ItemIsSelectable, interactive)
        self.setFlag(flag.ItemIsMovable, interactive)

    def update_flags_recursive(self):
        """Update the flags of this item and all its descendants."""
        for item in [self] + hierarchy.descendants(self):
            item.update_flags()

    def setParentItem(self, parent):
        super().setParentItem(parent)
        self.update_flags_recursive()

    def set_comment(self, comment):
        """Set the comment (HTML). The comment is shown as tooltip."""
        self.comment = comment or ''
        if self.comment:
            doc = QtGui.QTextDocument()
            doc.setHtml(self.comment)
            self.setToolTip(doc.toPlainText())
        else:
            self.setToolTip('')

    def copy_with_children(self):
        """A copy of this item, including copies of its children."""

        copy = self.create_copy()
        copy.name = self.name
        copy.set_comment(self.comment)
        copy.sort_order = getattr(self, 'sort_order', None)
        for child in hierarchy.user_children(self):
            child_copy = child.copy_with_children()
            child_copy.setParentItem(copy)
        if hasattr(copy, 'fit_to_children'):
            copy.fit_to_children()
        return copy

    def set_pos_center(self, pos):
        """Sets the position using the item's center as the origin point."""

        self.setPos(pos - self.center_scene_coords)

    def has_selection_outline(self):
        return self.isSelected()

    def has_selection_handles(self):
        return (self.isSelected()
                and self.scene()
                and self.scene().has_single_selection())

    def selection_action_items(self):
        """The items affected by selection actions like scaling and rotating.
        """
        return [self]

    def set_locked(self, locked):
        """Lock or unlock the item as part of locking the whole
        scene. Locked items can neither be selected nor moved."""

        self.globally_locked = locked
        self.update_flags()

    def set_item_locked(self, locked):
        """Lock or unlock this item on its own (saved in the bee
        file)."""

        self.locked = locked
        self.update_flags()

    def on_selected_change(self, value):
        if (value and self.scene()
                and not self.scene().has_selection()
                and not self.scene().active_mode is None):
            self.bring_to_front()

    def update_from_data(self, **kwargs):
        self.save_id = kwargs.get('save_id', self.save_id)
        self.setPos(kwargs.get('x', self.pos().x()),
                    kwargs.get('y', self.pos().y()))
        self.setZValue(kwargs.get('z', self.zValue()))
        self.setScale(kwargs.get('scale', self.scale()))
        self.setRotation(kwargs.get('rotation', self.rotation()))
        if kwargs.get('flip', 1) != self.flip():
            self.do_flip()
        self.update_common_from_data(**kwargs)

    def update_common_from_data(self, **kwargs):
        """Set data common to all item types from a bee file.

        The parent can only be assigned once it has been added to the
        scene, see ``BeeGraphicsScene.resolve_parents``.
        """
        self.sort_order = kwargs.get(
            'sort_order', getattr(self, 'sort_order', None))
        self.pending_parent_id = kwargs.get('parent_id')
        data = kwargs.get('data') or {}
        self.added_at = data.get('added_at', getattr(self, 'added_at', None))
        self.name = data.get('name', self.name)
        self.set_comment(data.get('comment', self.comment))
        self.set_item_locked(data.get('locked', self.locked))

    def get_common_save_data(self):
        """Data common to all item types to be stored in the bee file."""
        data = {}
        if getattr(self, 'added_at', None) is not None:
            data['added_at'] = self.added_at
        if self.name:
            data['name'] = self.name
        if self.comment:
            data['comment'] = self.comment
        if self.locked:
            data['locked'] = True
        return data


@register_item
class BeePixmapItem(BeeItemMixin, QtWidgets.QGraphicsPixmapItem):
    """Class for images added by the user."""

    TYPE = 'pixmap'
    CROP_HANDLE_SIZE = 15

    def __init__(self, image, filename=None, **kwargs):
        super().__init__(QtGui.QPixmap.fromImage(image))
        self.save_id = None
        self.filename = filename
        self.reset_crop()
        logger.debug(f'Initialized {self}')
        self.is_image = True
        self.crop_mode = False
        self.init_selectable()
        self.settings = BeeSettings()
        self.grayscale = False
        self.nearest_neighbor = (
            self.settings.valueOrDefault('Images/default_sampling')
            == 'nearest')
        #: The image data has changed since loading (needs saving)
        self.pixmap_dirty = False
        #: Only the path is saved, not the image data
        self.linked = False
        #: Format for storing the image data ('png', 'jpg', 'bmp' or
        #: 'best'); ``None`` for the format from the settings
        self.storage_format = None

    @classmethod
    def create_from_data(self, **kwargs):
        item = kwargs.pop('item')
        data = kwargs.pop('data', {})
        item.filename = item.filename or data.get('filename')
        if 'crop' in data:
            item.crop = QtCore.QRectF(*data['crop'])
        if not data:
            # A new image (not loaded from a bee file) keeps its
            # defaults, like linking and the default sampling
            return item
        item.setOpacity(data.get('opacity', 1))
        item.grayscale = data.get('grayscale', False)
        item.nearest_neighbor = data.get('nearest_neighbor', False)
        item.linked = data.get('linked', False)
        item.storage_format = data.get('storage_format')
        return item

    def __str__(self):
        size = self.pixmap().size()
        return (f'Image "{self.filename}" {size.width()} x {size.height()}')

    def default_name(self):
        if self.filename:
            return os.path.basename(self.filename)
        return _('Image')

    @property
    def crop(self):
        return self._crop

    @crop.setter
    def crop(self, value):
        logger.debug(f'Setting crop for {self} to {value}')
        self.prepareGeometryChange()
        self._crop = value
        self.update()

    @property
    def grayscale(self):
        return self._grayscale

    @grayscale.setter
    def grayscale(self, value):
        logger.debug(f'Setting grayscale for {self} to {value}')
        self._grayscale = value
        self._grayscale_pixmap = None
        if value is True:
            self.get_grayscale_pixmap()
        self.update()

    @property
    def displays_grayscale(self):
        """Whether the image is shown in grayscale, either by itself or
        because the whole canvas is shown in grayscale."""
        return self.grayscale or bool(
            self.scene() and getattr(self.scene(), 'grayscale_canvas', False))

    def get_grayscale_pixmap(self):
        """The grayscale version of the pixmap (cached)."""

        if self._grayscale_pixmap is None:
            # Using the grayscale image format to convert to grayscale
            # loses an image's tranparency. So the straightworward
            # following method gives us an ugly black replacement:
            # img = img.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)

            # Instead, we will fill the background with the current
            # canvas colour, so the issue is only visible if the image
            # overlaps other images. The way we do it here only works
            # as long as the canvas colour is itself grayscale,
            # though.
            img = QtGui.QImage(
                self.pixmap().size(), QtGui.QImage.Format.Format_Grayscale8)
            img.fill(QtGui.QColor(*COLORS['Scene:Canvas']))
            painter = QtGui.QPainter(img)
            painter.drawPixmap(0, 0, self.pixmap())
            painter.end()
            self._grayscale_pixmap = QtGui.QPixmap.fromImage(img)

            # Alternative methods that have their own issues:
            #
            # 1. Use setAlphaChannel of the resulting grayscale
            # image. How do we get the original alpha channel? Using
            # the whole original image also takes color values into
            # account, not just their alpha values.
            #
            # 2. QtWidgets.QGraphicsColorizeEffect() with black colour
            # on the GraphicsItem. This applys to everything the paint
            # method does, so the selection outline/handles will also
            # be gray. setGraphicsEffect is only available on some
            # widgets, so we can't apply it selectively.
            #
            # 3. Going through every pixel and doing it manually — bad
            # performance.
        return self._grayscale_pixmap

    def sample_color_at(self, pos):
        ipos = self.mapFromScene(pos)
        if self.displays_grayscale:
            pm = self.get_grayscale_pixmap()
        else:
            pm = self.pixmap()
        img = pm.toImage()

        color = img.pixelColor(int(ipos.x()), int(ipos.y()))
        if color.alpha():
            return color

    def bounding_rect_unselected(self):
        if self.crop_mode:
            return QtWidgets.QGraphicsPixmapItem.boundingRect(self)
        else:
            return self.crop

    def get_extra_save_data(self):
        data = {'filename': self.filename,
                'opacity': self.opacity(),
                'grayscale': self.grayscale,
                'crop': [self.crop.topLeft().x(),
                         self.crop.topLeft().y(),
                         self.crop.width(),
                         self.crop.height()]}
        if self.nearest_neighbor:
            data['nearest_neighbor'] = True
        if self.linked:
            data['linked'] = True
        if self.storage_format:
            data['storage_format'] = self.storage_format
        return data

    def get_filename_for_export(self, imgformat, save_id_default=None):
        save_id = self.save_id or save_id_default
        assert save_id is not None

        if self.filename:
            basename = os.path.splitext(os.path.basename(self.filename))[0]
            return f'{save_id:04}-{basename}.{imgformat}'
        else:
            return f'{save_id:04}.{imgformat}'

    def get_imgformat(self, img):
        """Determines the format for storing this image."""

        formt = (self.storage_format
                 or self.settings.valueOrDefault('Items/image_storage_format'))

        if formt == 'best':
            # Images with alpha channel and small images are stored as png
            if (img.hasAlphaChannel()
                    or (img.height() < 500 and img.width() < 500)):
                formt = 'png'
            else:
                formt = 'jpg'

        logger.debug(f'Found format {formt} for {self}')
        return formt

    def pixmap_to_bytes(self, apply_grayscale=False, apply_crop=False):
        """Convert the pixmap data to PNG bytestring."""
        barray = QtCore.QByteArray()
        buffer = QtCore.QBuffer(barray)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        if apply_grayscale and self.grayscale:
            pm = self.get_grayscale_pixmap()
        else:
            pm = self.pixmap()

        if apply_crop:
            pm = pm.copy(self.crop.toRect())

        img = pm.toImage()
        imgformat = self.get_imgformat(img)
        img.save(buffer, imgformat.upper(), quality=90)
        return (barray.data(), imgformat)

    def setPixmap(self, pixmap):
        super().setPixmap(pixmap)
        self._grayscale_pixmap = None
        self.reset_crop()

    def pixmap_from_bytes(self, data):
        """Set image pimap from a bytestring."""
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(data)
        self.setPixmap(pixmap)

    def create_copy(self):
        item = BeePixmapItem(QtGui.QImage(), self.filename)
        item.setPixmap(self.pixmap())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        item.setOpacity(self.opacity())
        item.grayscale = self.grayscale
        item.nearest_neighbor = self.nearest_neighbor
        item.linked = self.linked
        item.storage_format = self.storage_format
        if self.flip() == -1:
            item.do_flip()
        item.crop = self.crop
        return item

    @cached_property
    def color_gamut(self):
        logger.debug(f'Calculating color gamut for {self}')
        gamut = defaultdict(int)
        img = self.pixmap().toImage()
        # Don't evaluate every pixel for larger images:
        step = max(1, int(max(img.width(), img.height()) / 1000))
        logger.debug(f'Considering every {step}. row/column')

        # Not actually faster than solution below :(
        # ptr = img.bits()
        # size = img.sizeInBytes()
        # pixelsize = int(img.sizeInBytes() / img.width() / img.height())
        # ptr.setsize(size)
        # for pixel in batched(ptr, n=pixelsize):
        #     r, g, b, alpha = tuple(map(ord, pixel))
        #     if 5 < alpha and 5 < r < 250 and 5 < g < 250 and 5 < b < 250:
        #         # Only consider pixels that aren't close to
        #         # transparent, white or black
        #         rgb = QtGui.QColor(r, g, b)
        #         gamut[rgb.hue(), rgb.saturation()] += 1

        for i in range(0, img.width(), step):
            for j in range(0, img.height(), step):
                rgb = img.pixelColor(i, j)
                rgbtuple = (rgb.red(), rgb.blue(), rgb.green())
                if (5 < rgb.alpha()
                        and min(rgbtuple) < 250 and max(rgbtuple) > 5):
                    # Only consider pixels that aren't close to
                    # transparent, white or black
                    gamut[rgb.hue(), rgb.saturation()] += 1

        logger.debug(f'Got {len(gamut)} color gamut values')
        return gamut

    def copy_to_clipboard(self, clipboard):
        clipboard.setPixmap(self.pixmap())

    def reset_crop(self):
        self.crop = QtCore.QRectF(
            0, 0, self.pixmap().size().width(), self.pixmap().size().height())

    @property
    def crop_handle_size(self):
        return self.fixed_length_for_viewport(self.CROP_HANDLE_SIZE)

    def crop_handle_topleft(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x(),
            topleft.y(),
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_bottomleft(self):
        bottomleft = self.crop_temp.bottomLeft()
        return QtCore.QRectF(
            bottomleft.x(),
            bottomleft.y() - self.crop_handle_size,
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_bottomright(self):
        bottomright = self.crop_temp.bottomRight()
        return QtCore.QRectF(
            bottomright.x() - self.crop_handle_size,
            bottomright.y() - self.crop_handle_size,
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_topright(self):
        topright = self.crop_temp.topRight()
        return QtCore.QRectF(
            topright.x() - self.crop_handle_size,
            topright.y(),
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handles(self):
        return (self.crop_handle_topleft,
                self.crop_handle_bottomleft,
                self.crop_handle_bottomright,
                self.crop_handle_topright)

    def crop_edge_top(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x() + self.crop_handle_size,
            topleft.y(),
            self.crop_temp.width() - 2 * self.crop_handle_size,
            self.crop_handle_size)

    def crop_edge_left(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x(),
            topleft.y() + self.crop_handle_size,
            self.crop_handle_size,
            self.crop_temp.height() - 2 * self.crop_handle_size)

    def crop_edge_bottom(self):
        bottomleft = self.crop_temp.bottomLeft()
        return QtCore.QRectF(
            bottomleft.x() + self.crop_handle_size,
            bottomleft.y() - self.crop_handle_size,
            self.crop_temp.width() - 2 * self.crop_handle_size,
            self.crop_handle_size)

    def crop_edge_right(self):
        topright = self.crop_temp.topRight()
        return QtCore.QRectF(
            topright.x() - self.crop_handle_size,
            topright.y() + self.crop_handle_size,
            self.crop_handle_size,
            self.crop_temp.height() - 2 * self.crop_handle_size)

    def crop_edges(self):
        return (self.crop_edge_top,
                self.crop_edge_left,
                self.crop_edge_bottom,
                self.crop_edge_right)

    def get_crop_handle_cursor(self, handle):
        """Gets the crop cursor for the given handle."""

        is_topleft_or_bottomright = handle in (
            self.crop_handle_topleft, self.crop_handle_bottomright)
        return self.get_diag_cursor(is_topleft_or_bottomright)

    def get_crop_edge_cursor(self, edge):
        """Gets the crop edge cursor for the given edge."""

        top_or_bottom = edge in (
            self.crop_edge_top, self.crop_edge_bottom)
        sideways = (45 < self.rotation() < 135
                    or 225 < self.rotation() < 315)

        if top_or_bottom is sideways:
            return Qt.CursorShape.SizeHorCursor
        else:
            return Qt.CursorShape.SizeVerCursor

    def draw_crop_rect(self, painter, rect):
        """Paint a dotted rectangle for the cropping UI."""
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
        pen.setWidth(2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(rect)
        pen.setColor(QtGui.QColor(0, 0, 0))
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawRect(rect)

    def paint(self, painter, option, widget):
        if (not self.nearest_neighbor
                and abs(painter.combinedTransform().m11()) < 2):
            # We want image smoothing, but only for images where we
            # are not zoomed in a lot. This is to ensure that for
            # example icons and pixel sprites can be viewed correctly.
            # Users can turn smoothing off completely per image
            # (e.g. for pixel art).
            painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)

        if self.crop_mode:
            self.paint_debug(painter, option, widget)

            # Darken image outside of cropped area
            painter.drawPixmap(0, 0, self.pixmap())
            path = QtWidgets.QGraphicsPixmapItem.shape(self)
            path.addRect(self.crop_temp)
            color = QtGui.QColor(0, 0, 0)
            color.setAlpha(100)
            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)
            painter.setBrush(QtGui.QBrush())

            for handle in self.crop_handles():
                self.draw_crop_rect(painter, handle())
            self.draw_crop_rect(painter, self.crop_temp)
        else:
            if self.displays_grayscale:
                pm = self.get_grayscale_pixmap()
            else:
                pm = self.pixmap()
            painter.drawPixmap(self.crop, pm, self.crop)
            self.paint_selectable(painter, option, widget)

    def enter_crop_mode(self):
        logger.debug(f'Entering crop mode on {self}')
        self.prepareGeometryChange()
        self.crop_mode = True
        self.crop_temp = QtCore.QRectF(self.crop)
        self.crop_mode_move = None
        self.crop_mode_event_start = None
        self.grabKeyboard()
        self.update()
        self.scene().crop_item = self

    def exit_crop_mode(self, confirm):
        logger.debug(f'Exiting crop mode with {confirm} on {self}')
        if confirm and self.crop != self.crop_temp:
            self.scene().undo_stack.push(
                commands.CropItem(self, self.crop_temp))
        self.prepareGeometryChange()
        self.crop_mode = False
        self.crop_temp = None
        self.crop_mode_move = None
        self.crop_mode_event_start = None
        self.ungrabKeyboard()
        self.update()
        self.scene().crop_item = None

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.exit_crop_mode(confirm=True)
        elif event.key() == Qt.Key.Key_Escape:
            self.exit_crop_mode(confirm=False)
        else:
            super().keyPressEvent(event)

    def hoverMoveEvent(self, event):
        if not self.crop_mode:
            return super().hoverMoveEvent(event)

        for handle in self.crop_handles():
            if handle().contains(event.pos()):
                self.set_cursor(self.get_crop_handle_cursor(handle))
                return
        for edge in self.crop_edges():
            if edge().contains(event.pos()):
                self.set_cursor(self.get_crop_edge_cursor(edge))
                return
        self.unset_cursor()

    def mousePressEvent(self, event):
        if not self.crop_mode:
            return super().mousePressEvent(event)

        event.accept()
        for handle in self.crop_handles():
            # Click into a handle?
            if handle().contains(event.pos()):
                self.crop_mode_event_start = event.pos()
                self.crop_mode_move = handle
                self.crop_mode_start_rect = QtCore.QRectF(self.crop_temp)
                self.crop_mode_press_pos = event.pos()
                return
        for edge in self.crop_edges():
            # Click into an edge handle?
            if edge().contains(event.pos()):
                self.crop_mode_event_start = event.pos()
                self.crop_mode_move = edge
                return
        # Click not in handle, end cropping mode:
        self.exit_crop_mode(
            confirm=self.crop_temp.contains(event.pos()))

    def ensure_point_within_crop_bounds(self, point, handle):
        """Returns the point, or the nearest point within the pixmap."""

        if handle == self.crop_handle_topleft:
            topleft = QtCore.QPointF(0, 0)
            bottomright = self.crop_temp.bottomRight()
        if handle == self.crop_handle_bottomleft:
            topleft = QtCore.QPointF(0, self.crop_temp.top())
            bottomright = QtCore.QPointF(
                self.crop_temp.right(), self.pixmap().size().height())
        if handle == self.crop_handle_bottomright:
            topleft = self.crop_temp.topLeft()
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())
        if handle == self.crop_handle_topright:
            topleft = QtCore.QPointF(self.crop_temp.left(), 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.crop_temp.bottom())
        if handle == self.crop_edge_top:
            topleft = QtCore.QPointF(0, 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.crop_temp.bottom())
        if handle == self.crop_edge_bottom:
            topleft = QtCore.QPointF(0, self.crop_temp.top())
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())
        if handle == self.crop_edge_left:
            topleft = QtCore.QPointF(0, 0)
            bottomright = QtCore.QPointF(
                self.crop_temp.right(), self.pixmap().size().height())
        if handle == self.crop_edge_right:
            topleft = QtCore.QPointF(self.crop_temp.left(), 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())

        point.setX(min(bottomright.x(), max(topleft.x(), point.x())))
        point.setY(min(bottomright.y(), max(topleft.y(), point.y())))

        return point

    def constrain_crop_aspect(self, modifiers, pos):
        """While dragging a corner of the crop rect, Shift keeps its
        aspect ratio and Shift+Alt makes it square."""

        shift = Qt.KeyboardModifier.ShiftModifier
        alt = Qt.KeyboardModifier.AltModifier
        if (not modifiers & shift
                or self.crop_mode_move not in self.crop_handles()):
            return
        start = getattr(self, 'crop_mode_start_rect', None)
        if start is None or start.width() <= 0 or start.height() <= 0:
            return
        if modifiers & alt:
            ratio = 1
        else:
            ratio = start.width() / start.height()

        handle = self.crop_mode_move
        # The corner opposite to the dragged one stays where it is
        left = handle in (self.crop_handle_topleft,
                          self.crop_handle_bottomleft)
        top = handle in (self.crop_handle_topleft,
                         self.crop_handle_topright)
        anchor_x = start.right() if left else start.left()
        anchor_y = start.bottom() if top else start.top()
        # Where the dragged corner would be without constraints
        moved = pos - self.crop_mode_press_pos
        corner_x = (start.left() if left else start.right()) + moved.x()
        corner_y = (start.top() if top else start.bottom()) + moved.y()
        width = max(1, (anchor_x - corner_x) if left
                    else (corner_x - anchor_x))
        height = max(1, (anchor_y - corner_y) if top
                     else (corner_y - anchor_y))
        if width / height > ratio:
            width = height * ratio
        else:
            height = width / ratio
        size = self.pixmap().size()
        max_width = anchor_x if left else size.width() - anchor_x
        max_height = anchor_y if top else size.height() - anchor_y
        shrink = min(1, max_width / width, max_height / height)
        width *= shrink
        height *= shrink
        x = anchor_x - width if left else anchor_x
        y = anchor_y - height if top else anchor_y
        self.crop_temp = QtCore.QRectF(x, y, width, height)

    def mouseMoveEvent(self, event):
        if self.crop_mode and self.crop_mode_event_start:
            diff = event.pos() - self.crop_mode_event_start
            if self.crop_mode_move == self.crop_handle_topleft:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setTopLeft(new)
            if self.crop_mode_move == self.crop_handle_bottomleft:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomLeft() + diff, self.crop_mode_move)
                self.crop_temp.setBottomLeft(new)
            if self.crop_mode_move == self.crop_handle_bottomright:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomRight() + diff, self.crop_mode_move)
                self.crop_temp.setBottomRight(new)
            if self.crop_mode_move == self.crop_handle_topright:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topRight() + diff, self.crop_mode_move)
                self.crop_temp.setTopRight(new)
            if self.crop_mode_move == self.crop_edge_top:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setTop(new.y())
            if self.crop_mode_move == self.crop_edge_left:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setLeft(new.x())
            if self.crop_mode_move == self.crop_edge_bottom:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomLeft() + diff, self.crop_mode_move)
                self.crop_temp.setBottom(new.y())
            if self.crop_mode_move == self.crop_edge_right:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topRight() + diff, self.crop_mode_move)
                self.crop_temp.setRight(new.x())
            self.constrain_crop_aspect(event.modifiers(), event.pos())
            self.update()
            self.crop_mode_event_start = event.pos()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.crop_mode:
            self.crop_mode_move = None
            self.crop_mode_event_start = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)


@register_item
class BeeTextItem(BeeItemMixin, QtWidgets.QGraphicsTextItem):
    """Class for text notes added by the user.

    Notes contain rich text, which is stored as HTML. Notes either
    grow with their text, or have a fixed width with word wrap
    (``text_width``).
    """

    TYPE = 'text'
    #: Width of the area at the right edge for changing the text width,
    #: in pixels on screen
    WIDTH_HANDLE_SIZE = 8
    MIN_TEXT_WIDTH = 20

    def __init__(self, text=None, html=None, text_width=None,
                 background=None, **kwargs):
        super().__init__()
        if html:
            self.setHtml(html)
        else:
            self.setPlainText(text or _('Text'))
        if text_width and text_width > 0:
            self.setTextWidth(text_width)
        #: Background color as hex ARGB, or None for the default
        self.background = background
        self.save_id = None
        logger.debug(f'Initialized {self}')
        self.is_image = False
        self.init_selectable()
        self.is_editable = True
        self.edit_mode = False
        self.width_drag_start = None
        self.setAcceptHoverEvents(True)
        self.setDefaultTextColor(QtGui.QColor(*COLORS['Scene:Text']))

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {})
        item = cls(**data)
        return item

    def __str__(self):
        txt = self.toPlainText()[:40]
        return (f'Text "{txt}"')

    def default_name(self):
        lines = self.toPlainText().strip().splitlines()
        return lines[0][:40] if lines else _('Text')

    def get_extra_save_data(self):
        # The plain text is kept for older versions:
        data = {'text': self.toPlainText(), 'html': self.html()}
        if self.has_fixed_width():
            data['text_width'] = self.textWidth()
        if self.background:
            data['background'] = self.background
        return data

    def html(self):
        return self.toHtml()

    def has_fixed_width(self):
        return self.textWidth() > 0

    def set_text_width(self, width):
        """Fixed text width with word wrap; None or a negative value
        for a width that grows with the text."""

        self.prepareGeometryChange()
        self.setTextWidth(-1 if width is None or width <= 0 else width)
        self.update()

    def text_state(self):
        return (self.html(), self.textWidth())

    def set_text_state(self, html, width):
        self.prepareGeometryChange()
        self.setHtml(html)
        self.setTextWidth(width)
        self.update()

    def default_background_color(self):
        color = QtGui.QColor(0, 0, 0)
        color.setAlpha(40)
        return color

    def background_color(self):
        if self.background:
            color = QtGui.QColor(self.background)
            if color.isValid():
                return color
        return self.default_background_color()

    def set_background(self, background):
        self.background = background
        self.update()

    def contains(self, point):
        return self.boundingRect().contains(point)

    def paint(self, painter, option, widget):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(self.background_color()))
        rect = QtWidgets.QGraphicsTextItem.boundingRect(self)
        painter.drawRect(rect)
        option.state = QtWidgets.QStyle.StateFlag.State_Enabled
        super().paint(painter, option, widget)
        if self.edit_mode:
            # Grip for changing the text width:
            pen = QtGui.QPen(QtGui.QColor(*COLORS['Scene:Selection']))
            pen.setCosmetic(True)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(QtCore.QLineF(rect.topRight(),
                                           rect.bottomRight()))
        self.paint_selectable(painter, option, widget)

    def create_copy(self):
        item = BeeTextItem(html=self.html(), background=self.background)
        if self.has_fixed_width():
            item.setTextWidth(self.textWidth())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        if self.flip() == -1:
            item.do_flip()
        return item

    def notify_view_edit_mode(self):
        scene = self.scene()
        views = scene.views() if scene else []
        if views and hasattr(views[0], 'on_text_edit_mode_changed'):
            views[0].on_text_edit_mode_changed()

    def enter_edit_mode(self):
        logger.debug(f'Entering edit mode on {self}')
        self.edit_mode = True
        self.old_text = self.html()
        self.old_width = self.textWidth()
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        self.scene().edit_item = self
        actions.set_context(CONTEXT_TEXT_EDIT)
        self.update()
        self.notify_view_edit_mode()

    def exit_edit_mode(self, commit=True):
        logger.debug(f'Exiting edit mode on {self}')
        self.edit_mode = False
        self.width_drag_start = None
        # reset selection:
        self.setTextCursor(QtGui.QTextCursor(self.document()))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.scene().edit_item = None
        actions.set_context(CONTEXT_GLOBAL)
        old_width = getattr(self, 'old_width', self.textWidth())
        if commit:
            self.scene().undo_stack.push(
                commands.ChangeText(self, self.html(), self.old_text,
                                    self.textWidth(), old_width))
            if not self.toPlainText().strip():
                logger.debug('Removing empty text item')
                self.scene().undo_stack.push(
                    commands.DeleteItems(self.scene(), [self]))
        else:
            self.set_text_state(self.old_text, old_width)
        self.update()
        self.notify_view_edit_mode()

    def has_selection_handles(self):
        return super().has_selection_handles() and not self.edit_mode

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return)
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            self.exit_edit_mode()
            event.accept()
            return
        if (event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return)
                and event.modifiers() == Qt.KeyboardModifier.ShiftModifier):
            # A new paragraph (and list item), not just a line break:
            cursor = self.textCursor()
            cursor.insertBlock()
            self.setTextCursor(cursor)
            event.accept()
            return
        if (event.key() == Qt.Key.Key_Escape
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            self.exit_edit_mode(commit=False)
            event.accept()
            return
        if (event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
                and self.textCursor().currentList()):
            delta = -1 if event.key() == Qt.Key.Key_Backtab else 1
            cursor = self.textCursor()
            textformat.indent(delta)(cursor)
            self.setTextCursor(cursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def anchor_at(self, pos):
        """The link target at the given position in item coordinates."""

        return textformat.anchor_at(self.document(), pos)

    def screen_scale(self):
        """How many screen pixels one unit of this item covers."""

        scene = self.scene()
        if not scene or not scene.views():
            return 1
        view = scene.views()[0]
        transform = self.deviceTransform(view.viewportTransform())
        return max(math.hypot(transform.m11(), transform.m12()), 0.0001)

    def is_on_width_handle(self, pos):
        rect = QtWidgets.QGraphicsTextItem.boundingRect(self)
        margin = self.WIDTH_HANDLE_SIZE / self.screen_scale()
        return (self.edit_mode
                and rect.right() - margin <= pos.x() <= rect.right() + margin
                and rect.top() <= pos.y() <= rect.bottom())

    def hoverMoveEvent(self, event):
        if self.is_on_width_handle(event.pos()):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif self.edit_mode:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if self.edit_mode and event.button() == Qt.MouseButton.LeftButton:
            if self.is_on_width_handle(event.pos()):
                self.width_drag_start = event.pos()
                event.accept()
                return
            block = textformat.checkbox_at(self.document(), event.pos())
            if block is not None:
                textformat.toggle_checkbox(block)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.width_drag_start is not None:
            self.set_text_width(max(self.MIN_TEXT_WIDTH, event.pos().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.width_drag_start is not None:
            self.width_drag_start = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def copy_to_clipboard(self, clipboard):
        mimedata = QtCore.QMimeData()
        mimedata.setText(self.toPlainText())
        mimedata.setHtml(self.html())
        clipboard.setMimeData(mimedata)


@register_item
class BeeErrorItem(BeeItemMixin, QtWidgets.QGraphicsTextItem):
    """Class for displaying error messages when an item can't be loaded
    from a bee file.

    This item will be displayed instead of the original item. It won't
    save to bee files. The original item will be preserved in the bee
    file, unless this item gets deleted by the user, or a new bee file
    is saved.
    """

    TYPE = 'error'

    def __init__(self, text=None, **kwargs):
        super().__init__(text or "Text")
        self.original_save_id = None
        logger.debug(f'Initialized {self}')
        self.is_image = False
        self.init_selectable()
        self.is_editable = False
        #: A linked image whose file is missing (can be relinked)
        self.missing_link = False
        #: The item's data from the bee file, for relinking
        self.original_data = None
        self.setDefaultTextColor(QtGui.QColor(*COLORS['Scene:Text']))

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {})
        item = cls(text=data.get('text'))
        if data.get('missing_link'):
            item.missing_link = True
            item.original_data = dict(kwargs)
            item.original_data['data'] = dict(data.get('original', {}))
        return item

    def __str__(self):
        txt = self.toPlainText()[:40]
        return (f'Error "{txt}"')

    def contains(self, point):
        return self.boundingRect().contains(point)

    def paint(self, painter, option, widget):
        painter.setPen(Qt.PenStyle.NoPen)
        color = QtGui.QColor(200, 0, 0)
        brush = QtGui.QBrush(color)
        painter.setBrush(brush)
        painter.drawRect(QtWidgets.QGraphicsTextItem.boundingRect(self))
        option.state = QtWidgets.QStyle.StateFlag.State_Enabled
        super().paint(painter, option, widget)
        self.paint_selectable(painter, option, widget)

    def update_from_data(self, **kwargs):
        self.original_save_id = kwargs.get('save_id', self.original_save_id)
        self.setPos(kwargs.get('x', self.pos().x()),
                    kwargs.get('y', self.pos().y()))
        self.setZValue(kwargs.get('z', self.zValue()))
        self.setScale(kwargs.get('scale', self.scale()))
        self.setRotation(kwargs.get('rotation', self.rotation()))
        self.update_common_from_data(**kwargs)

    def create_copy(self):
        item = BeeErrorItem(self.toPlainText())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        return item

    def flip(self, *args, **kwargs):
        """Returns the flip value (1 or -1)"""
        # Never display error messages flipped
        return 1

    def do_flip(self, *args, **kwargs):
        """Flips the item."""
        # Never flip error messages
        pass

    def copy_to_clipboard(self, clipboard):
        clipboard.setText(self.toPlainText())


_gear_path = None


def gear_path():
    """The outline of a gear with radius 1, around the origin."""

    global _gear_path
    if _gear_path is None:
        path = QtGui.QPainterPath()
        teeth = 8
        step = 2 * math.pi / teeth
        inner, outer = 0.74, 1.0
        points = []
        for i in range(teeth):
            for fraction, radius in ((0, inner), (0.14, outer),
                                     (0.36, outer), (0.5, inner)):
                angle = (i + fraction) * step
                points.append(QtCore.QPointF(
                    radius * math.cos(angle), radius * math.sin(angle)))
        path.addPolygon(QtGui.QPolygonF(points))
        path.closeSubpath()
        path.addEllipse(QtCore.QPointF(0, 0), 0.34, 0.34)
        path.setFillRule(Qt.FillRule.OddEvenFill)
        _gear_path = path
    return _gear_path


class TitleGhostItem(QtWidgets.QGraphicsItem):
    """Shows where a group's title would end up while it is dragged."""

    def __init__(self, group):
        super().__init__()
        self.group = group
        self.position = group.style['title_position']
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(1e6)
        self.setParentItem(group)

    def set_position(self, position):
        if position != self.position:
            self.prepareGeometryChange()
            self.position = position
            self.update()

    def boundingRect(self):
        return self.group.bounding_rect_unselected()

    def paint(self, painter, option, widget):
        rect = self.group.title_text_rect(self.position)
        if rect.isNull():
            return
        rect = rect.adjusted(-3, -2, 3, 2)
        color = QtGui.QColor(*COLORS['Scene:Selection'])
        pen = QtGui.QPen(color)
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        fill = QtGui.QColor(color)
        fill.setAlpha(40)
        painter.setBrush(fill)
        painter.drawRect(rect)
        frame, transform = self.group.title_frame(self.position)
        painter.save()
        painter.setTransform(transform, True)
        painter.setFont(group_style.title_font(self.group.style))
        text_color = QtGui.QColor(self.group.style['title_color'])
        text_color.setAlpha(120)
        painter.setPen(text_color)
        text_frame = self.group.title_text_frame(self.position)
        painter.drawText(
            text_frame, Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter, self.group.elided_title(
                self.position))
        painter.restore()


@register_item
class BeeGroupItem(BeeItemMixin, QtWidgets.QGraphicsItem):
    """A group of items, drawn as a coloured area behind its children.

    Groups are closed by default: Clicking on a child selects the whole
    group. Double clicking opens the group so that its children can be
    selected on their own. The group closes again when nothing inside
    it is selected anymore.
    """

    TYPE = 'group'
    #: Space between the children and the border
    PADDING = 10
    #: Height of the title band relative to the title's font size
    TITLE_LINE_HEIGHT = 1.4
    #: Size of the settings icon (gear) on the screen
    GEAR_PIXELS = 24
    #: Size of a new group's title on the screen
    TITLE_PIXELS = 20
    #: Size of the title's resize handles on the screen
    HANDLE_PIXELS = 9

    def __init__(self, **kwargs):
        super().__init__()
        self.save_id = None
        self.is_image = False
        self.is_open = False
        #: Set while the title is edited in a text field
        self.editing_title = False
        #: The text typed so far while the title is edited
        self.editing_text = None
        #: The title is selected: it shows handles for resizing it
        self.title_active = False
        self.color = None
        self.style = group_style.default_style()
        self._border_cache = None
        self._rect = QtCore.QRectF()
        self.init_selectable()
        logger.debug(f'Initialized {self}')

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data') or {}
        item = cls()
        item.color = data.get('color')
        item.style = group_style.from_data(data)
        item.setOpacity(group_style.clean_opacity(data.get('opacity', 1)))
        return item

    def __str__(self):
        return f'Group "{self.name}"'

    def default_name(self):
        return _('Group')

    def get_extra_save_data(self):
        data = group_style.to_data(self.style)
        if self.color:
            data['color'] = self.color
        if self.opacity() != 1:
            data['opacity'] = self.opacity()
        return data

    def get_style(self):
        """The group's look: Background color, opacity and the style
        values (see myRef.group_style)."""

        return {'color': self.color, 'opacity': self.opacity(),
                **self.style}

    def set_style(self, **values):
        """Change the group's look. Accepts the keys of ``get_style``."""

        if 'color' in values:
            self.color = values.pop('color')
        if 'opacity' in values:
            self.setOpacity(
                group_style.clean_opacity(values.pop('opacity')))
        for key, value in values.items():
            self.style[key] = group_style.clean_value(key, value)
        self.fit_to_children()
        self.update()

    def background_color(self):
        if self.color:
            return QtGui.QColor(self.color)
        return QtGui.QColor(*COLORS['Scene:Group'])

    def bounding_rect_unselected(self):
        return QtCore.QRectF(self._rect)

    def title_text(self):
        if self.editing_title and self.editing_text is not None:
            return self.editing_text or ' '
        return self.display_name()

    def title_height(self):
        if group_style.title_font(self.style) is None:
            return 0
        return self.style['title_size'] * self.TITLE_LINE_HEIGHT

    def title_side(self, position=None):
        return group_style.title_side(
            position or self.style['title_position'])

    def margins(self):
        """Space around the children: (left, top, right, bottom).

        Border and title are drawn inside the group's area (otherwise
        they'd get cut off when exporting), so the margins make room
        for them.
        """

        side = self.PADDING + group_style.border_inset(self.style)
        left = top = right = bottom = side
        height = self.title_height()
        title_side = self.title_side()
        if title_side == 'top':
            top += height
        elif title_side == 'bottom':
            bottom += height
        elif title_side == 'left':
            left += height
        else:
            right += height
        return (left, top, right, bottom)

    def gear_size(self):
        """Side length of the settings icon in the corner."""

        rect = self._rect
        size = self.GEAR_PIXELS / self.screen_scale()
        return max(0, min(size, rect.width() / 4, rect.height() / 4))

    def gear_rect(self):
        """Where the settings icon is, in item coordinates (bottom
        right corner)."""

        inset = group_style.border_inset(self.style) + 2
        size = self.gear_size()
        return QtCore.QRectF(self._rect.right() - inset - size,
                             self._rect.bottom() - inset - size,
                             size, size)

    def gear_contains(self, pos):
        rect = self.gear_rect()
        return (not self._rect.isNull() and rect.width() > 0
                and rect.adjusted(-2, -2, 2, 2).contains(pos))

    def children_rect(self):
        """The area of all children plus margins, in item coordinates."""

        rect = QtCore.QRectF()
        for child in hierarchy.user_children(self):
            rect = rect.united(
                child.mapRectToParent(child.bounding_rect_unselected()))
        if rect.isNull():
            return rect
        left, top, right, bottom = self.margins()
        return rect.adjusted(-left, -top, right, bottom)

    def fit_to_children(self):
        """Adjust the group's area to its children."""

        rect = self.children_rect()
        if rect != self._rect:
            self.prepareGeometryChange()
            self._rect = rect

    def set_open(self, value):
        """Open or close the group (see class docstring)."""

        if value == self.is_open:
            return
        logger.debug(f'Setting {self} open: {value}')
        self.is_open = value
        for item in hierarchy.descendants(self):
            item.update_flags()
        self.update()

    def title_frame(self, position=None):
        """Where the title line is, as ``(rect, transform)``.

        The title is laid out horizontally in ``rect``; ``transform``
        maps that to item coordinates. On the left and right side the
        title runs along the edge (rotated by 90 degrees).
        """

        position = position or self.style['title_position']
        side = group_style.title_side(position)
        border = group_style.border_inset(self.style)
        pad = self.PADDING
        height = self.title_height()
        rect = self._rect
        # The gear takes the end of the bottom and right title lines
        gear = self.gear_size() + 4
        transform = QtGui.QTransform()
        if side in ('top', 'bottom'):
            frame = QtCore.QRectF(
                rect.left() + border + pad, 0,
                rect.width() - 2 * (border + pad), height)
            if side == 'top':
                frame.moveTop(rect.top() + border + pad / 2)
            else:
                frame.moveTop(rect.bottom() - border - pad / 2 - height)
                frame.setRight(frame.right() - gear)
        else:
            length = rect.height() - 2 * (border + pad)
            if side == 'left':
                transform.translate(rect.left() + border + pad / 2,
                                    rect.bottom() - border - pad)
                transform.rotate(-90)
            else:
                length -= gear
                transform.translate(rect.right() - border - pad / 2,
                                    rect.top() + border + pad)
                transform.rotate(90)
            frame = QtCore.QRectF(0, 0, length, height)
        return frame, transform

    def title_rect(self, position=None):
        """The band the title is in, in item coordinates."""

        frame, transform = self.title_frame(position)
        return transform.mapRect(frame)

    def title_text_frame(self, position=None, text=None):
        """The part of the title frame that the text takes."""

        frame, _transform = self.title_frame(position)
        font = group_style.title_font(self.style)
        if font is None:
            return QtCore.QRectF()
        if text is None:
            text = self.elided_title(position)
        width = min(QtGui.QFontMetricsF(font).horizontalAdvance(text),
                    frame.width())
        result = QtCore.QRectF(frame)
        result.setWidth(width)
        alignment = group_style.title_alignment(
            position or self.style['title_position'])
        if alignment == 'center':
            result.moveLeft(frame.left() + (frame.width() - width) / 2)
        elif alignment == 'right':
            result.moveRight(frame.right())
        return result

    def title_text_rect(self, position=None, text=None):
        """The area of the title's text, in item coordinates."""

        if group_style.title_font(self.style) is None:
            return QtCore.QRectF()
        frame = self.title_text_frame(position, text)
        return self.title_frame(position)[1].mapRect(frame)

    def title_contains(self, pos):
        """Whether the given point (item coordinates) is on the text
        of the title."""

        if group_style.title_font(self.style) is None or self.editing_title:
            return False
        rect = self.title_text_rect()
        return rect.adjusted(-3, -3, 3, 3).contains(pos)

    def screen_scale(self):
        """How many screen pixels one unit of the item takes."""

        scene = self.scene()
        if scene and scene.views():
            transform = self.deviceTransform(
                scene.views()[0].viewportTransform())
            return max(math.hypot(transform.m11(), transform.m12()),
                       0.0001)
        return 1

    def handle_size(self):
        """Side of the title's handles in scene units (they have a
        fixed size on the screen)."""

        return self.HANDLE_PIXELS / self.screen_scale()

    def title_handle_rects(self):
        """The handles at the corners of the title: {corner: rect}, in
        item coordinates."""

        rect = self.title_text_rect().adjusted(-6, -6, 6, 6)
        size = self.handle_size()
        corners = {'tl': rect.topLeft(), 'tr': rect.topRight(),
                   'bl': rect.bottomLeft(), 'br': rect.bottomRight()}
        return {key: QtCore.QRectF(p.x() - size / 2, p.y() - size / 2,
                                   size, size)
                for key, p in corners.items()}

    def title_handle_at(self, pos):
        """The corner whose handle is at pos (item coordinates), if
        any."""

        if not self.title_active:
            return None
        if group_style.title_font(self.style) is None:
            return None
        for key, rect in self.title_handle_rects().items():
            if rect.adjusted(-2, -2, 2, 2).contains(pos):
                return key
        return None

    def paint_title_handles(self, painter):
        if (not self.title_active
                or group_style.title_font(self.style) is None):
            return
        color = QtGui.QColor(*COLORS['Scene:Selection'])
        pen = QtGui.QPen(color)
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush())
        painter.drawRect(self.title_text_rect().adjusted(-3, -3, 3, 3))
        pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(QtGui.QColor(255, 255, 255))
        for rect in self.title_handle_rects().values():
            painter.drawRect(rect)
        painter.restore()

    def title_position_at(self, pos):
        """The title position that is nearest to the given point (item
        coordinates): The corners and the middle of each side."""

        rect = self._rect
        center = rect.center()
        anchors = {
            'top_left': rect.topLeft(),
            'top_center': QtCore.QPointF(center.x(), rect.top()),
            'top_right': rect.topRight(),
            'middle_left': QtCore.QPointF(rect.left(), center.y()),
            'middle_right': QtCore.QPointF(rect.right(), center.y()),
            'bottom_left': rect.bottomLeft(),
            'bottom_center': QtCore.QPointF(center.x(), rect.bottom()),
            'bottom_right': rect.bottomRight(),
        }
        return min(anchors, key=lambda key: (
            (anchors[key].x() - pos.x()) ** 2
            + (anchors[key].y() - pos.y()) ** 2))

    def border_path(self):
        """The outline of the border (the middle of the border
        line), in item coordinates. Cached, since wavy borders consist
        of many points."""

        half = self.style['border_width'] / 2
        rect = self._rect.adjusted(half, half, -half, -half)
        key = (rect.getRect(), self.style['border_shape'],
               self.style['border_amplitude'],
               self.style['border_wavelength'])
        if self._border_cache is None or self._border_cache[0] != key:
            self._border_cache = (
                key, group_style.border_path(rect, *key[1:]))
        return self._border_cache[1]

    def paint_background(self, painter):
        color = self.background_color()
        if (group_style.is_wavy(self.style)
                and self.style['border_width'] > 0):
            # Don't fill the area outside of the waves
            painter.fillPath(self.border_path(), color)
        else:
            painter.fillRect(self._rect, color)

    def paint_border(self, painter):
        pen = group_style.border_pen(self.style)
        if pen is None:
            return
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush())
        painter.drawPath(self.border_path())

    def elided_title(self, position=None):
        """The title, shortened with an ellipsis if it doesn't fit."""

        font = group_style.title_font(self.style)
        width = self.title_frame(position)[0].width()
        if font is None or width <= 0:
            return ''
        return QtGui.QFontMetricsF(font).elidedText(
            self.title_text(), Qt.TextElideMode.ElideRight, width)

    def paint_title(self, painter):
        if self.editing_title:
            return
        text = self.elided_title()
        if not text:
            return
        transform = self.title_frame()[1]
        painter.save()
        painter.setTransform(transform, True)
        painter.setFont(group_style.title_font(self.style))
        painter.setPen(QtGui.QColor(self.style['title_color']))
        painter.drawText(
            self.title_text_frame(text=text),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text)
        painter.restore()

    def paint_gear(self, painter):
        """The semi-transparent settings icon in the corner."""

        rect = self.gear_rect()
        if rect.width() <= 0:
            return
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.translate(rect.center())
        painter.scale(rect.width() / 2, rect.height() / 2)
        pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 170))
        pen.setCosmetic(True)
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.setBrush(QtGui.QColor(255, 255, 255, 200))
        painter.drawPath(gear_path())
        painter.restore()

    def paint(self, painter, option, widget):
        if self._rect.isNull():
            return
        self.paint_background(painter)
        self.paint_border(painter)
        self.paint_title(painter)
        if widget is not None:
            # Not when rendering for export
            self.paint_gear(painter)
            self.paint_title_handles(painter)
        if self.is_open:
            pen = QtGui.QPen(QtGui.QColor(*COLORS['Scene:Selection']))
            pen.setCosmetic(True)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QtGui.QBrush())
            painter.drawRect(self._rect)
        self.paint_selectable(painter, option, widget)

    def create_copy(self):
        item = BeeGroupItem()
        item.color = self.color
        item.style = dict(self.style)
        item.setOpacity(self.opacity())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        if self.flip() == -1:
            item.do_flip()
        item._rect = QtCore.QRectF(self._rect)
        return item

    def copy_to_clipboard(self, clipboard):
        clipboard.setText(self.display_name())


@register_item
class BeeDrawingItem(BeeItemMixin, QtWidgets.QGraphicsItem):
    """Vector drawing: A list of shapes (see myRef.drawing)."""

    TYPE = 'drawing'
    #: Clicks this many screen pixels away from a stroke still hit it
    HIT_TOLERANCE = 4

    def __init__(self, shapes=None, **kwargs):
        super().__init__()
        self.save_id = None
        self.is_image = False
        self.shapes = [s for s in (shapes or [])
                       if drawing.is_valid_shape(s)]
        self._rect = drawing.shapes_rect(self.shapes)
        self.init_selectable()
        self.is_editable = True
        logger.debug(f'Initialized {self}')

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data') or {}
        return cls(shapes=data.get('shapes'))

    def __str__(self):
        return f'Drawing ({len(self.shapes)} shapes)'

    def default_name(self):
        return _('Drawing')

    def get_extra_save_data(self):
        return {'shapes': drawing.copy_shapes(self.shapes)}

    def set_shapes(self, shapes):
        self.prepareGeometryChange()
        self.shapes = shapes
        self._rect = drawing.shapes_rect(shapes)
        self.update()

    def add_shape(self, shape):
        self.set_shapes(self.shapes + [shape])

    def update_last_shape(self, shape):
        """Replace the last shape (e.g. while it is being drawn)."""

        self.set_shapes(self.shapes[:-1] + [shape])

    def bounding_rect_unselected(self):
        if self._rect.isNull():
            return QtCore.QRectF(0, 0, 1, 1)
        return QtCore.QRectF(self._rect)

    def screen_scale(self):
        scene = self.scene()
        if not scene or not scene.views():
            return 1
        view = scene.views()[0]
        transform = self.deviceTransform(view.viewportTransform())
        return max(math.hypot(transform.m11(), transform.m12()), 0.0001)

    def shapes_at(self, pos, radius):
        """Indices of the shapes within radius of pos (item coords)."""

        return [i for i, shape in enumerate(self.shapes)
                if drawing.shape_hit(shape, pos, radius)]

    def contains(self, point):
        if self.has_selection_handles():
            return super().contains(point)
        radius = self.HIT_TOLERANCE / self.screen_scale()
        return bool(self.shapes_at(point, radius))

    def shape(self):
        if self.has_selection_handles():
            return super().shape()
        path = QtGui.QPainterPath()
        extra = 2 * self.HIT_TOLERANCE / self.screen_scale()
        for shape in self.shapes:
            path.addPath(drawing.stroked_path(shape, extra))
        return path

    def paint(self, painter, option, widget):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        for shape in self.shapes:
            drawing.paint_shape(painter, shape)
        self.paint_selectable(painter, option, widget)

    def create_copy(self):
        item = BeeDrawingItem(shapes=drawing.copy_shapes(self.shapes))
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        if self.flip() == -1:
            item.do_flip()
        return item

    def enter_edit_mode(self):
        """Double click: continue drawing on this item."""

        scene = self.scene()
        if scene and scene.views():
            scene.views()[0].enter_draw_mode(self)

    def copy_to_clipboard(self, clipboard):
        rect = self.bounding_rect_unselected()
        image = QtGui.QImage(
            max(1, math.ceil(rect.width())), max(1, math.ceil(rect.height())),
            QtGui.QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.translate(-rect.topLeft())
        for shape in self.shapes:
            drawing.paint_shape(painter, shape)
        painter.end()
        clipboard.setImage(image)
