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

"""Dialog for changing many images at once (Images -> Manage Images):
downscaling, converting the storage format, discarding cropped pixels
and switching between embedded and linked image data.
"""

from dataclasses import dataclass
import logging
import os.path

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef.i18n import _


logger = logging.getLogger(__name__)

FORMATS = ('png', 'jpg', 'bmp')


@dataclass
class ManageOptions:
    #: Longest side in pixels, or ``None`` to keep the resolution
    max_side: int = None
    #: 'best', 'png', 'jpg', 'bmp' or ``None`` to keep the format
    storage_format: str = None
    discard_crop: bool = False
    #: 'embed', 'link' or ``None`` to keep the location
    location: str = None
    link_dir: str = ''
    name_template: str = ''
    replace_existing: bool = False


def is_local_file(filename):
    return bool(filename) and os.path.isfile(filename)


def is_cropped(item):
    return item.crop != QtCore.QRectF(item.pixmap().rect())


def needs_downscaling(item, options):
    size = item.pixmap().size()
    if options.discard_crop:
        size = item.crop.size().toSize()
    return (options.max_side is not None
            and max(size.width(), size.height()) > options.max_side)


def changes_format(item, options):
    return (options.storage_format is not None
            and options.storage_format != (item.storage_format or None))


def alters_data(item, options):
    """Whether the image data itself will be changed."""
    return ((options.discard_crop and is_cropped(item))
            or needs_downscaling(item, options))


def export_format(pixmap, storage_format):
    if storage_format in FORMATS:
        return storage_format
    if pixmap.hasAlphaChannel():
        return 'png'
    return 'jpg'


def flatten_alpha(pixmap):
    """JPG and BMP have no transparency: put the image on white."""

    if not pixmap.hasAlphaChannel():
        return pixmap
    img = QtGui.QImage(pixmap.size(), QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(255, 255, 255))
    painter = QtGui.QPainter(img)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return QtGui.QPixmap.fromImage(img)


def unique_path(path):
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(path):
        path = f'{base}-{i}{ext}'
        i += 1
    return path


def describe(item, options):
    """One line for the preview list."""

    name = item.display_name()
    size = item.pixmap().size()
    parts = [f'{size.width()} × {size.height()}']
    if alters_data(item, options):
        crop = item.crop.size().toSize() if options.discard_crop else size
        width, height = crop.width(), crop.height()
        if needs_downscaling(item, options):
            factor = options.max_side / max(width, height)
            width, height = round(width * factor), round(height * factor)
        parts.append(f'→ {width} × {height}')
    if changes_format(item, options):
        parts.append(options.storage_format.upper()
                     if options.storage_format != 'best'
                     else _('automatic format'))
    if options.location == 'link' and not item.linked:
        parts.append(_('linked'))
    if options.location == 'embed' and item.linked:
        parts.append(_('embedded'))
    marker = '⚠ ' if alters_data(item, options) else ''
    return f'{marker}{name}: ' + ', '.join(parts)


def affects(item, options):
    return (alters_data(item, options)
            or changes_format(item, options)
            or (options.location == 'link' and not item.linked)
            or (options.location == 'embed' and item.linked))


def image_change(item, options, index=0, total=1, scene_name='scene'):
    """The ``ReplacePixmaps`` change for one image, or ``None`` if the
    options don't affect it.

    Images that are linked to files are written to ``link_dir``.

    :raises OSError: If writing a linked file fails
    """

    if not affects(item, options):
        return None
    change = {'item': item,
              'center': item.mapToScene(item.crop.center())}
    pixmap = item.pixmap()
    crop = QtCore.QRectF(item.crop)
    scale = item.scale()
    altered = False

    if options.discard_crop and is_cropped(item):
        pixmap = pixmap.copy(crop.toRect())
        crop = None
        altered = True
    if needs_downscaling(item, options):
        factor = options.max_side / max(pixmap.width(), pixmap.height())
        pixmap = pixmap.scaled(
            max(1, round(pixmap.width() * factor)),
            max(1, round(pixmap.height() * factor)),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        scale = scale / factor
        if crop is not None:
            crop = QtCore.QRectF(crop.x() * factor, crop.y() * factor,
                                 crop.width() * factor,
                                 crop.height() * factor)
        altered = True
    if changes_format(item, options):
        change['storage_format'] = options.storage_format
        if options.storage_format in ('jpg', 'bmp'):
            flat = flatten_alpha(pixmap)
            if flat is not pixmap:
                pixmap = flat
                altered = True
    if altered:
        change.update({'pixmap': pixmap, 'scale': scale, 'crop': crop})

    if options.location == 'embed':
        change['linked'] = False
    elif options.location == 'link':
        if (not altered and not changes_format(item, options)
                and is_local_file(item.filename)):
            # The original file can be used as it is
            change['linked'] = True
        else:
            # Imported here to avoid a circular import
            from myRef.fileio.export import format_export_name
            fmt = export_format(pixmap, options.storage_format)
            name = format_export_name(
                options.name_template or '%0', item, index, total,
                scene_name, fmt)
            path = os.path.join(options.link_dir, name)
            if not options.replace_existing:
                path = unique_path(path)
            logger.debug(f'Writing linked image: {path}')
            if not pixmap.save(path, fmt.upper(), quality=90):
                raise OSError(_('Could not write {path}').format(path=path))
            change['filename'] = path
            change['linked'] = True
    return change


class ManageImagesDialog(QtWidgets.QDialog):

    def __init__(self, parent, items, scene_name='scene'):
        super().__init__(parent)
        self.items = items
        self.scene_name = scene_name
        self.setWindowTitle(_('Manage images'))
        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel(
            _('{num} image(s) (the selected ones, or all if none are '
              'selected)').format(num=len(items))))

        # Resolution
        self.resolution_box = QtWidgets.QGroupBox(
            _('Downscale images larger than'))
        self.resolution_box.setCheckable(True)
        self.resolution_box.setChecked(False)
        box_layout = QtWidgets.QHBoxLayout(self.resolution_box)
        self.max_side = QtWidgets.QSpinBox()
        self.max_side.setRange(16, 32000)
        self.max_side.setValue(2048)
        self.max_side.setSuffix(' px')
        box_layout.addWidget(QtWidgets.QLabel(_('Longest side:')))
        box_layout.addWidget(self.max_side)
        box_layout.addStretch()
        layout.addWidget(self.resolution_box)

        # Optimization
        optimize_box = QtWidgets.QGroupBox(_('Optimize'))
        form = QtWidgets.QFormLayout(optimize_box)
        self.format_combo = QtWidgets.QComboBox()
        for value, text in ((None, _('Unchanged')),
                            ('best', _('Automatic (PNG with transparency, '
                                       'else JPG)')),
                            ('png', 'PNG'), ('jpg', 'JPG'), ('bmp', 'BMP')):
            self.format_combo.addItem(text, value)
        form.addRow(_('Format:'), self.format_combo)
        self.discard_crop = QtWidgets.QCheckBox(_('Discard cropped pixels'))
        form.addRow(self.discard_crop)
        layout.addWidget(optimize_box)

        # Location
        location_box = QtWidgets.QGroupBox(_('Image data location'))
        form = QtWidgets.QFormLayout(location_box)
        self.location_combo = QtWidgets.QComboBox()
        for value, text in ((None, _('Unchanged')),
                            ('embed', _('Embed in the scene file')),
                            ('link', _('Link to image files'))):
            self.location_combo.addItem(text, value)
        form.addRow(_('Location:'), self.location_combo)
        dir_layout = QtWidgets.QHBoxLayout()
        self.link_dir = QtWidgets.QLineEdit()
        browse = QtWidgets.QPushButton(_('Browse...'))
        browse.clicked.connect(self.on_browse)
        dir_layout.addWidget(self.link_dir)
        dir_layout.addWidget(browse)
        form.addRow(_('Folder for new files:'), dir_layout)
        self.name_template = QtWidgets.QLineEdit()
        self.name_template.setPlaceholderText('%0')
        self.name_template.setToolTip(
            _('%0 original name, %1 number, %2 number with leading zeros, '
              '%3 scene name'))
        form.addRow(_('File name template:'), self.name_template)
        self.replace_existing = QtWidgets.QCheckBox(
            _('Replace existing files'))
        form.addRow(self.replace_existing)
        layout.addWidget(location_box)

        # Preview
        layout.addWidget(QtWidgets.QLabel(_('Affected images:')))
        self.preview = QtWidgets.QListWidget()
        layout.addWidget(self.preview)
        self.warning = QtWidgets.QLabel(
            _('⚠ The image data of marked images is changed. '
              'This can be undone with Ctrl+Z.'))
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for signal in (self.resolution_box.toggled,
                       self.max_side.valueChanged,
                       self.format_combo.currentIndexChanged,
                       self.discard_crop.toggled,
                       self.location_combo.currentIndexChanged):
            signal.connect(self.update_preview)
        self.update_preview()
        self.resize(560, 620)

    def options(self):
        return ManageOptions(
            max_side=(self.max_side.value()
                      if self.resolution_box.isChecked() else None),
            storage_format=self.format_combo.currentData(),
            discard_crop=self.discard_crop.isChecked(),
            location=self.location_combo.currentData(),
            link_dir=self.link_dir.text(),
            name_template=self.name_template.text(),
            replace_existing=self.replace_existing.isChecked(),
        )

    def affected_items(self, options=None):
        options = options or self.options()
        return [item for item in self.items if affects(item, options)]

    def update_preview(self):
        options = self.options()
        self.preview.clear()
        affected = self.affected_items(options)
        for item in affected:
            self.preview.addItem(describe(item, options))
        if not affected:
            self.preview.addItem(_('No images are affected'))
        self.warning.setVisible(
            any(alters_data(item, options) for item in affected))

    def on_browse(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, _('Folder for linked images'), self.link_dir.text())
        if directory:
            self.link_dir.setText(directory)

    def on_accept(self):
        options = self.options()
        if options.location == 'link' and not os.path.isdir(
                options.link_dir):
            needs_dir = any(
                alters_data(item, options) or changes_format(item, options)
                or not is_local_file(item.filename)
                for item in self.affected_items(options) if not item.linked)
            if needs_dir:
                QtWidgets.QMessageBox.warning(
                    self, _('Manage images'),
                    _('Please choose a folder for the new image files.'))
                return
        self.accept()

    def build_changes(self):
        """The changes for ``ReplacePixmaps`` and a list of errors."""

        options = self.options()
        affected = self.affected_items(options)
        changes = []
        errors = []
        for i, item in enumerate(affected):
            try:
                change = image_change(item, options, i, len(affected),
                                      self.scene_name)
            except OSError as e:
                errors.append(str(e))
                continue
            if change:
                changes.append(change)
        return changes, errors
