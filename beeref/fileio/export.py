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

import base64
import logging
import os
import re
import pathlib
from xml.etree import ElementTree as ET

from PyQt6 import QtCore, QtGui

from .errors import BeeFileIOError
from beeref import constants, drawing, hierarchy, widgets
from beeref.i18n import _
from beeref.items import BeePixmapItem, items_in_order


logger = logging.getLogger(__name__)


class ExporterRegistry(dict):

    DEFAULT_TYPE = 0

    def __getitem__(self, key):
        key = key.removeprefix('.')
        exp = self.get(key, super().__getitem__(self.DEFAULT_TYPE))
        logger.debug(f'Exporter for type {key}: {exp}')
        return exp


exporter_registry = ExporterRegistry()


def register_exporter(cls):
    exporter_registry[cls.TYPE] = cls
    return cls


class ExporterBase:

    def emit_begin_processing(self, worker, start):
        if worker:
            worker.begin_processing.emit(start)

    def emit_progress(self, worker, progress):
        if worker:
            worker.progress.emit(progress)

    def emit_finished(self, worker, filename, errors):
        filename = str(filename)
        if worker:
            worker.finished.emit(filename, errors)

    def emit_user_input_required(self, worker, msg):
        if worker:
            worker.user_input_required.emit(msg)

    def handle_export_error(self, filename, error, worker):
        filename = str(filename)
        logger.debug(f'Export failed: {error}')
        if worker:
            worker.finished.emit(filename, [str(error)])
            return
        else:
            e = error if isinstance(error, Exception) else None
            raise BeeFileIOError(msg=str(error), filename=filename) from e


class SceneExporterBase(ExporterBase):
    """For exporting the scene to a single image.

    The export itself runs in a worker thread, but Qt's graphics scene
    isn't thread safe and processes its pending updates in the main
    thread at the same time. So everything that needs the scene has to
    happen in the main thread: In ``__init__`` and ``prepare``.
    """

    def __init__(self, scene, items=None):
        """
        :param items: Only export these items (and their children);
            export all items if ``None``.
        """
        self.scene = scene
        self.only_items = list(items) if items else None
        self.scene.cancel_active_modes()
        self.scene.deselect_all_items()
        # Selection outlines/handles will be rendered to the exported
        # image, so deselect first. (Alternatively, pass an attribute
        # to paint functions to not paint them?)
        if self.only_items:
            rect = self.scene.itemsBoundingRect(items=self.only_items)
            items = list(self.only_items)
            for item in self.only_items:
                items.extend(i for i in hierarchy.descendants(item)
                             if i not in items)
        else:
            rect = self.scene.itemsBoundingRect()
            items = self.scene.items()
        logger.trace(f'Items bounding rect: {rect}')
        self.items_rect = rect
        # Sorted since z order in SVG is specified via the order of
        # elements. Children are drawn above their parents, so use the
        # scene's stacking order where possible.
        stacking = {item: i for i, item in enumerate(
            self.scene.items(order=QtCore.Qt.SortOrder.AscendingOrder))}
        self.items = sorted(
            items, key=lambda x: (stacking.get(x, -1), x.zValue()))
        size = QtCore.QSize(int(rect.width()), int(rect.height()))
        logger.trace(f'Export size without margins: {size}')
        self.margin = max(size.width(), size.height()) * 0.03
        self.default_size = size.grownBy(
            QtCore.QMargins(*([int(self.margin)] * 4)))
        logger.debug(f'Default export margin: {self.margin}')
        logger.debug(f'Default export size with margins: {self.default_size}')

    def prepare(self):
        """Does the work that needs the scene after the user input is known.

        To be called in the main thread before starting the export.
        """


@register_exporter
class SceneToPixmapExporter(SceneExporterBase):

    TYPE = ExporterRegistry.DEFAULT_TYPE
    image = None

    def get_user_input(self, parent):
        """Ask user for final export size."""

        dialog = widgets.SceneToPixmapExporterDialog(
            parent=parent,
            default_size=self.default_size,
        )
        if dialog.exec():
            size = dialog.value()
            logger.debug(f'Got export size {size}')
            self.size = size
            return True
        else:
            return False

    def render_to_image(self):
        logger.debug(f'Final export size: {self.size}')
        margin = self.margin * self.size.width() / self.default_size.width()
        logger.debug(f'Final export margin: {margin}')

        image = QtGui.QImage(self.size, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor(*constants.COLORS['Scene:Canvas']))
        painter = QtGui.QPainter(image)
        target_rect = QtCore.QRectF(
            margin,
            margin,
            self.size.width() - 2 * margin,
            self.size.height() - 2 * margin)
        logger.trace(f'Final export target_rect: {target_rect}')
        hidden = self.hide_other_items()
        try:
            self.scene.render(painter,
                              source=self.items_rect,
                              target=target_rect)
        finally:
            for item in hidden:
                item.setVisible(True)
        painter.end()
        return image

    def hide_other_items(self):
        """When exporting only some items, temporarily hide the others
        so they don't show up where they overlap the exported area."""

        if not self.only_items:
            return []
        keep = set(self.only_items)
        for item in self.only_items:
            keep.update(hierarchy.descendants(item))
        # Parents of exported items can't be hidden without hiding
        # the exported items, too:
        parents = set()
        for item in self.only_items:
            parents.update(hierarchy.ancestors(item))
        hidden = []
        for item in self.scene.items():
            if (item not in keep and item not in parents
                    and item.isVisible()
                    and (item.parentItem() is None
                         or item.parentItem() in parents)):
                item.setVisible(False)
                hidden.append(item)
        return hidden

    def prepare(self):
        self.image = self.render_to_image()

    def export(self, filename, worker=None):
        logger.debug(f'Exporting scene to {filename}')
        self.emit_begin_processing(worker, 1)
        if self.image is None:
            self.prepare()
        # The exporter outlives the export, don't keep the image in memory
        image, self.image = self.image, None

        if worker and worker.canceled:
            logger.debug('Export canceled')
            self.emit_finished(worker, filename, [])
            return

        if not image.save(filename, quality=90):
            self.handle_export_error(
                filename, _('Error writing file'), worker)
            return

        logger.debug('Export finished')
        self.emit_progress(worker, 1)
        self.emit_finished(worker, filename, [])


@register_exporter
class SceneToSVGExporter(SceneExporterBase):

    TYPE = 'svg'

    def get_user_input(self, parent):
        self.size = self.default_size
        return True

    def _get_drawing_element(self, item, offset):
        """A group of SVG paths for a drawing item."""

        transform = item.sceneTransform() * QtGui.QTransform.fromTranslate(
            -offset.x(), -offset.y())
        values = [transform.m11(), transform.m12(), transform.m21(),
                  transform.m22(), transform.dx(), transform.dy()]
        group = ET.Element('g', attrib={
            'transform': 'matrix({})'.format(
                ' '.join(f'{round(v, 6):g}' for v in values)),
            'opacity': str(item.opacity())})
        for shape in item.shapes:
            group.append(ET.Element('path',
                                    attrib=drawing.svg_attributes(shape)))
        return group

    def _get_textstyles(self, item, scale=None):
        fontstylemap = {
            QtGui.QFont.Style.StyleNormal: 'normal',
            QtGui.QFont.Style.StyleItalic: 'italic',
            QtGui.QFont.Style.StyleOblique: 'oblique',
        }

        font = item.font()
        if scale is None:
            scale = item.scale()
        fontsize = font.pointSize() * scale
        families = ', '.join(font.families())
        fontstyle = fontstylemap[font.style()]

        return ('white-space:pre',
                f'font-size:{fontsize}pt',
                f'font-family:{families}',
                f'font-weight:{font.weight()}',
                f'font-stretch:{font.stretch()}',
                f'font-style:{fontstyle}')

    def render_to_svg(self, worker=None):
        svg = ET.Element(
            'svg',
            attrib={'width': str(self.size.width()),
                    'height': str(self.size.height()),
                    'xmlns': 'http://www.w3.org/2000/svg',
                    'xmlns:xlink': 'http://www.w3.org/1999/xlink',
                    })

        offset = (self.items_rect.topLeft()
                  - QtCore.QPointF(self.margin, self.margin))

        for i, item in enumerate(self.items):
            if item.TYPE == 'drawing':
                svg.append(self._get_drawing_element(item, offset))
                self.emit_progress(worker, i)
                if worker and worker.canceled:
                    return
                continue
            if item.TYPE not in ('text', 'pixmap'):
                # E.g. placeholders for images that couldn't be loaded
                logger.debug(f'Not exporting {item} to SVG')
                self.emit_progress(worker, i)
                continue

            # Children are positioned relative to their parents; use
            # the values relative to the scene:
            scene_pos, scale, rotation, flip = (
                hierarchy.decompose_transform(item.sceneTransform()))
            pos = scene_pos - offset
            anchor = pos

            if item.TYPE == 'text':
                styles = self._get_textstyles(item, scale)
                element = ET.Element(
                    'text',
                    attrib={'style': ';'.join(styles),
                            'dominant-baseline': 'hanging'})
                element.text = item.toPlainText()
            if item.TYPE == 'pixmap':
                width = item.width * scale
                height = item.height * scale
                pixmap, imgformat = item.pixmap_to_bytes(
                    apply_grayscale=True,
                    apply_crop=True)
                pixmap = base64.b64encode(pixmap).decode('ascii')
                element = ET.Element(
                    'image',
                    attrib={
                        'xlink:href':
                        f'data:image/{imgformat};base64,{pixmap}',
                        'width': str(width),
                        'height': str(height),
                        'image-rendering': ('crisp-edges' if scale > 2
                                            else 'optimizeQuality')})
                pos = pos + item.crop.topLeft()

            transforms = []
            if flip == -1:
                # The following is not recognised by Inkscape and not an
                # official standard:
                # element.set('transform-origin', f'{anchor.x()} {anchor.y()}')
                # Thus we need to fix the origin manually
                transforms.append(f'translate({anchor.x()} {anchor.y()})')
                transforms.append(f'scale({float(flip)} 1)')
                transforms.append(f'translate(-{anchor.x()} -{anchor.y()})')
            transforms.append(
                f'rotate({round(rotation, 6)} {anchor.x()} {anchor.y()})')

            element.set('transform', ' '.join(transforms))
            element.set('x', str(pos.x()))
            element.set('y', str(pos.y()))
            element.set('opacity', str(item.opacity()))

            svg.append(element)
            self.emit_progress(worker, i)
            if worker and worker.canceled:
                return

        return svg

    def export(self, filename, worker=None):
        logger.debug(f'Exporting scene to {filename}')
        self.emit_begin_processing(worker, len(self.items))
        svg = self.render_to_svg(worker)

        if worker and worker.canceled:
            logger.debug('Export canceled')
            worker.finished.emit(filename, [])
            return

        tree = ET.ElementTree(svg)
        ET.indent(tree, space='  ')

        try:
            with open(filename, 'w') as f:
                tree.write(f, encoding='unicode', xml_declaration=True)
        except OSError as e:
            self.handle_export_error(filename, e, worker)
            return

        logger.debug('Export finished')
        self.emit_finished(worker, filename, [])


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def format_export_name(template, item, index, total, scene_name,
                       imgformat):
    """Build a file name for an exported image from a template.

    Placeholders:

    * ``%0``: Original file name (without extension)
    * ``%1``: Sequence number, starting at 1
    * ``%2``: Zero-padded sequence number
    * ``%3``: Scene name

    Characters that aren't allowed in file names are replaced by ``_``.
    """

    if item.filename:
        original = os.path.splitext(os.path.basename(item.filename))[0]
    else:
        original = str(index + 1)
    number = index + 1
    width = len(str(total))
    replacements = {
        '%0': original,
        '%1': str(number),
        '%2': str(number).zfill(max(width, 2)),
        '%3': scene_name,
    }
    name = re.sub('%[0-3]', lambda m: replacements[m.group(0)], template)
    name = INVALID_FILENAME_CHARS.sub('_', name).strip().strip('.')
    if not name:
        name = original
    return f'{name}.{imgformat}'


class ImagesToDirectoryExporter(ExporterBase):
    """Export all images to a folder.

    Not registered in the registry as it is accessed via its own menu entry,
    not auto-detected by file extension.
    """

    def __init__(self, scene, dirname, items=None, name_template='',
                 export_cropped=False, scene_name=''):
        """
        :param items: Only export these items; all images if ``None``.
        :param name_template: See ``format_export_name``; an empty
            template keeps the default naming.
        :param export_cropped: Export only the visible (cropped) area.
        :param scene_name: Name of the scene for the template.
        """
        self.scene = scene
        self.dirname = dirname
        if items is None:
            items = self.scene.items_by_type(BeePixmapItem.TYPE)
        else:
            items = [i for i in items
                     if getattr(i, 'TYPE', None) == BeePixmapItem.TYPE]
        self.items = items_in_order(items)
        self.name_template = name_template or ''
        self.export_cropped = export_cropped
        self.scene_name = scene_name or ''
        self.max_save_id = 0
        for item in self.items:
            if item.save_id:
                self.max_save_id = max(self.max_save_id, item.save_id)
        self.num_total = len(self.items)
        self.start_from = 0
        self.handle_existing = None

    def export(self, worker=None):
        logger.debug(f'Exporting images to {self.dirname}')
        logger.debug(f'Starting at {self.start_from}')

        self.emit_begin_processing(worker, self.num_total)
        self.emit_progress(worker, self.start_from)

        for i, item in enumerate(
                self.items[self.start_from:], start=self.start_from):
            if worker and worker.canceled:
                logger.debug('Export canceled')
                worker.finished.emit(self.dirname, [])
                return

            pixmap, imgformat = item.pixmap_to_bytes(
                apply_crop=self.export_cropped)

            if self.name_template:
                filename = format_export_name(
                    self.name_template,
                    item=item,
                    index=i,
                    total=self.num_total,
                    scene_name=self.scene_name,
                    imgformat=imgformat)
            elif item.save_id:
                filename = item.get_filename_for_export(imgformat)
            else:
                self.max_save_id += 1
                save_id = self.max_save_id
                filename = item.get_filename_for_export(imgformat, save_id)

            try:
                path = pathlib.Path(self.dirname) / filename
                path_exists = path.exists()
            except OSError as e:
                self.handle_export_error(self.dirname, e, worker)
                return

            if path_exists:
                logger.debug(f'File already exists: {path}')
                if self.handle_existing is None:
                    self.start_from = i
                    self.emit_user_input_required(worker, str(path))
                    return
                else:
                    if self.handle_existing == 'skip':
                        self.handle_existing = None
                        logger.debug('Skipping file')
                        continue
                    elif self.handle_existing == 'skip_all':
                        logger.debug('Skipping file')
                        continue
                    elif self.handle_existing == 'overwrite':
                        self.handle_existing = None
                        logger.debug('Overwrite file')
                    elif self.handle_existing == 'overwrite_all':
                        logger.debug('Overwrite file')

            logger.debug(f'Writing file: {path}')
            try:
                path.write_bytes(pixmap)
            except OSError as e:
                self.handle_export_error(path, e, worker)
                return

            self.emit_progress(worker, i)

        self.emit_finished(worker, self.dirname, [])
