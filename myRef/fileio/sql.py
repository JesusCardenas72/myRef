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

"""myRef's native file format is using SQLite. Embedded files are
stored in an sqlar table so that they can be extracted using sqlite's
archive command line option.

For more info, see:

https://www.sqlite.org/appfileformat.html
https://www.sqlite.org/sqlar.html
"""

import json
import logging
import os
import pathlib
import shutil
import sqlite3
import tempfile

from PyQt6 import QtGui

from myRef import constants
from myRef.i18n import _
from myRef.items import BeePixmapItem, BeeErrorItem
from .errors import BeeFileIOError, IMG_LOADING_ERROR_MSG, LINK_MISSING_MSG
from .image import exif_rotated_image
from .schema import SCHEMA, USER_VERSION, MIGRATIONS, APPLICATION_ID


logger = logging.getLogger(__name__)


def is_bee_file(path):
    """Check whether the file at the given path is a bee file."""

    return os.path.splitext(path)[1] == '.bee'


def item_depth(item):
    """Number of ancestors of the given item."""

    depth = 0
    parent = item.parentItem()
    while parent is not None:
        depth += 1
        parent = parent.parentItem()
    return depth


def parent_save_id(item):
    """The save_id of the item's parent, if the parent is a saved item.

    Positions, scales and rotations of child items are stored relative
    to their parent.
    """

    parent = item.parentItem()
    return getattr(parent, 'save_id', None) if parent else None


def item_save_data(item):
    """The JSON data column for the given item."""

    data = item.get_extra_save_data()
    if hasattr(item, 'get_common_save_data'):
        data.update(item.get_common_save_data())
    return data


def handle_sqlite_errors(func):
    def wrapper(self, *args, **kwargs):
        try:
            func(self, *args, **kwargs)
        except Exception as e:
            logger.exception(f'Error while reading/writing {self.filename}')
            try:
                # Try to roll back transaction if there is any
                if (hasattr(self, '_connection')
                        and self._connection.in_transaction):
                    self.ex('ROLLBACK')
                    logger.debug('Transaction rolled back')
            except sqlite3.Error:
                pass
            self._close_connection()
            if self.worker:
                self.worker.finished.emit(self.filename, [str(e)])
            else:
                raise BeeFileIOError(msg=str(e), filename=self.filename) from e

    return wrapper


class SQLiteIO:

    def __init__(self, filename, scene, create_new=False, readonly=False,
                 worker=None):
        self.scene = scene
        self.create_new = create_new
        self.filename = filename
        self.readonly = readonly
        self.worker = worker
        self.retry = False

    def __del__(self):
        self._close_connection()

    def _close_connection(self):
        if hasattr(self, '_connection'):
            self._connection.close()
            delattr(self, '_connection')
        if hasattr(self, '_cursor'):
            delattr(self, '_cursor')
        if hasattr(self, '_tmpdir'):
            self._tmpdir.cleanup()
            delattr(self, '_tmpdir')

    def _establish_connection(self):
        if (self.create_new
                and not self.readonly
                and os.path.exists(self.filename)):
            os.remove(self.filename)

        if self.create_new:
            self.scene.clear_save_ids()

        uri = pathlib.Path(self.filename).resolve().as_uri()
        if self.readonly:
            uri = f'{uri}?mode=rw'
        self._connection = sqlite3.connect(uri, uri=True)
        self._cursor = self.connection.cursor()
        if not self.create_new:
            try:
                self._migrate()
            except Exception:
                # Updating a file failed; try creating it from scratch instead
                logger.exception('Error migrating bee file')
                self.create_new = True
                self._establish_connection()

    def _migrate(self):
        """Migrate database if necessary."""

        version = self.fetchone('PRAGMA user_version')[0]
        logger.debug(f'Found bee file version: {version}')
        if version >= USER_VERSION:
            logger.debug('Version ok; no migrations necessary')
            return

        if self.readonly:
            try:
                # See whether file is writable so we can migrate it directly
                self.ex('PRAGMA application_id=%s' % APPLICATION_ID)
            except sqlite3.Error:
                logger.debug('File not writable; use temporary copy instead')
                self._connection.close()
                self._tmpdir = tempfile.TemporaryDirectory(
                    prefix=constants.APPNAME)
                tmpname = os.path.join(self._tmpdir.name, 'mig.bee')
                shutil.copyfile(self.filename, tmpname)
                self._connection = sqlite3.connect(tmpname)
                self._cursor = self.connection.cursor()

        self.ex('BEGIN TRANSACTION')
        for i in range(version, USER_VERSION):
            logger.debug(f'Migrating from version {i} to {i + 1}...')
            for migration in MIGRATIONS[i + 1]:
                self.ex(migration)
        self.write_meta()
        self.connection.commit()
        logger.debug('Migration finished')

    @property
    def connection(self):
        if not hasattr(self, '_connection'):
            self._establish_connection()
        return self._connection

    @property
    def cursor(self):
        if not hasattr(self, '_cursor'):
            self._establish_connection()
        return self._cursor

    def ex(self, *args, **kwargs):
        return self.cursor.execute(*args, **kwargs)

    def exmany(self, *args, **kwargs):
        return self.cursor.executemany(*args, **kwargs)

    def fetchone(self, *args, **kwargs):
        self.ex(*args, **kwargs)
        return self.cursor.fetchone()

    def fetchall(self, *args, **kwargs):
        self.ex(*args, **kwargs)
        return self.cursor.fetchall()

    def write_meta(self):
        self.ex('PRAGMA application_id=%s' % APPLICATION_ID)
        self.ex('PRAGMA user_version=%s' % USER_VERSION)
        self.ex('PRAGMA foreign_keys=ON')

    def create_schema_on_new(self):
        if self.create_new:
            self.write_meta()
            for schema in SCHEMA:
                self.ex(schema)

    ITEM_COLUMNS = ('items.id, type, x, y, z, scale, rotation, flip, '
                    'items.data, parent_id, sort_order')

    @handle_sqlite_errors
    def read(self):
        # Items with binary data (images):
        rows = self.fetchall(
            f'SELECT {self.ITEM_COLUMNS}, sqlar.data '
            'FROM sqlar JOIN items on sqlar.item_id = items.id')
        # Items of any type without binary data (text, groups,
        # drawings, ...). Avoid OUTER JOIN for performance reasons;
        # sqlar.item_id is UNIQUE and thus indexed.
        rows.extend(self.fetchall(
            f'SELECT {self.ITEM_COLUMNS}, null as data '
            'FROM items '
            'WHERE NOT EXISTS '
            '(SELECT 1 FROM sqlar WHERE sqlar.item_id = items.id)'))
        if self.worker:
            self.worker.begin_processing.emit(len(rows))

        for i, row in enumerate(rows):
            data = {
                'save_id': row[0],
                'type': row[1],
                'x': row[2],
                'y': row[3],
                'z': row[4],
                'scale': row[5],
                'rotation': row[6],
                'flip': row[7],
                'data': json.loads(row[8]) if row[8] else {},
                'parent_id': row[9],
                'sort_order': row[10],
            }

            if data['type'] == BeePixmapItem.TYPE:
                filename = data['data'].get('filename')
                linked = data['data'].get('linked', False)
                item = None
                if row[11] is not None:
                    item = BeePixmapItem(QtGui.QImage())
                    item.pixmap_from_bytes(row[11])
                elif linked and filename and os.path.isfile(filename):
                    img = exif_rotated_image(filename)
                    if not img.isNull():
                        item = BeePixmapItem(img)
                if linked and (item is None or item.pixmap().isNull()):
                    original = dict(data['data'])
                    data['data'] = {
                        'text': _(LINK_MISSING_MSG).format(filename=filename),
                        'missing_link': True,
                        'original': original,
                    }
                    data['type'] = BeeErrorItem.TYPE
                elif item is None or item.pixmap().isNull():
                    data['data']['text'] = (
                        _('Image could not be loaded: {filename}\n').format(
                            filename=filename)
                        + _(IMG_LOADING_ERROR_MSG))
                    data['type'] = BeeErrorItem.TYPE
                else:
                    data['item'] = item

            self.scene.add_item_later(data)

            if self.worker:
                logger.trace(f'Emit progress: {i}')
                self.worker.progress.emit(i)
                if self.worker.canceled:
                    self.worker.finished.emit('', [])
                    return
                # Give main thread time to process items:
                self.worker.msleep(10)
        if self.worker:
            self.worker.finished.emit(self.filename, [])

    @handle_sqlite_errors
    def write(self):
        if self.readonly:
            raise sqlite3.OperationalError(
                'Attempt to write to a readonly database')
        try:
            self.create_schema_on_new()
            self.write_data()
        except Exception:
            if self.retry:
                # Trying to recover failed
                raise
            else:
                self.retry = True
                # Try creating file from scratch and save again
                logger.exception(
                    f'Updating to existing file {self.filename} failed')
                self.create_new = True
                self._close_connection()
                self.write()

    def write_data(self):
        to_delete = {row[0] for row in self.fetchall('SELECT id from ITEMS')}
        # We don't want to touch existing items that are displayed as errors:
        keep = {item.original_save_id
                for item in self.scene.items_by_type(BeeErrorItem.TYPE)}
        logger.debug(f'Not saving error items: {keep}')
        to_delete = to_delete - keep

        # Parents need to be saved before their children so that the
        # children can reference the parents' save_ids:
        to_save = sorted(self.scene.items_for_save(), key=item_depth)
        if self.worker:
            self.worker.begin_processing.emit(len(to_save))
        for i, item in enumerate(to_save):
            logger.debug(f'Saving {item} with id {item.save_id}')
            if item.save_id:
                self.update_item(item)
                to_delete.remove(item.save_id)
            else:
                self.insert_item(item)
            if self.worker:
                self.worker.progress.emit(i)
                if self.worker.canceled:
                    break
        self.delete_items(to_delete)
        self.ex('VACUUM')
        self.connection.commit()
        if self.worker:
            self.worker.finished.emit(self.filename, [])

    def delete_items(self, to_delete):
        to_delete = [(pk,) for pk in to_delete]
        self.exmany('DELETE FROM items WHERE id=?', to_delete)
        self.exmany('DELETE FROM sqlar WHERE item_id=?', to_delete)
        self.connection.commit()

    def insert_item(self, item):
        self.ex(
            'INSERT INTO items (type, x, y, z, scale, rotation, flip, '
            'data, parent_id, sort_order) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (item.TYPE, item.pos().x(), item.pos().y(), item.zValue(),
             item.scale(), item.rotation(), item.flip(),
             json.dumps(item_save_data(item)),
             parent_save_id(item), getattr(item, 'sort_order', None)))
        item.save_id = self.cursor.lastrowid

        if hasattr(item, 'pixmap_to_bytes'):
            self.insert_pixmap(item)
        self.connection.commit()

    @staticmethod
    def stores_link_only(item):
        """Whether only the path of the image is saved, not its data.

        If the file has vanished, the image is embedded after all.
        """
        if not getattr(item, 'linked', False):
            return False
        if item.filename and os.path.isfile(item.filename):
            return True
        logger.debug(f'Linked file missing, embedding instead: {item}')
        item.linked = False
        return False

    def insert_pixmap(self, item):
        item.pixmap_dirty = False
        if self.stores_link_only(item):
            return
        pixmap, imgformat = item.pixmap_to_bytes()
        name = item.get_filename_for_export(imgformat)
        self.ex(
            'INSERT INTO sqlar (item_id, name, mode, sz, data) '
            'VALUES (?, ?, ?, ?, ?)',
            (item.save_id, name, 0o644, len(pixmap), pixmap))

    def update_item(self, item):
        """Update item data.

        The pixmap data is time-consuming to save, so it's only saved
        again if it has changed (e.g. replaced or downscaled image) or
        if the image has been switched between linked and embedded.
        """
        if getattr(item, 'pixmap_dirty', False):
            self.ex('DELETE FROM sqlar WHERE item_id=?', (item.save_id,))
            self.insert_pixmap(item)
        self.ex(
            'UPDATE items SET x=?, y=?, z=?, scale=?, rotation=?, flip=?, '
            'data=?, parent_id=?, sort_order=? '
            'WHERE id=?',
            (item.pos().x(), item.pos().y(), item.zValue(), item.scale(),
             item.rotation(), item.flip(),
             json.dumps(item_save_data(item)),
             parent_save_id(item), getattr(item, 'sort_order', None),
             item.save_id))
        self.connection.commit()
