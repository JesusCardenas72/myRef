"""Tests for linked images, relinking missing images, the "Manage
images" dialog and the aspect ratio lock while cropping."""

import os.path
import shutil
from unittest.mock import MagicMock, patch

from pytest import approx

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from myRef import commands
from myRef.fileio import load_bee, save_bee
from myRef.items import BeeErrorItem, BeePixmapItem
from myRef.widgets.manage_images import (
    ManageImagesDialog,
    ManageOptions,
    describe,
    image_change,
)


def make_image_file(directory, name='pic.png', width=40, height=20,
                    color=(255, 0, 0)):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(*color))
    path = os.path.join(directory, name)
    img.save(path)
    return path


def add_image(view, path=None, width=40, height=20, x=0, y=0):
    if path:
        img = QtGui.QImage(path)
    else:
        img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
        img.fill(QtGui.QColor(0, 255, 0))
    item = BeePixmapItem(img, path)
    view.scene.addItem(item)
    item.setPos(x, y)
    return item


def reload(view, filename):
    view.scene.clear()
    load_bee(filename, view.scene)
    view.scene.add_queued_items()
    return list(view.scene.items_for_save())


def blob_count(filename):
    import sqlite3
    con = sqlite3.connect(filename)
    try:
        return con.execute('SELECT COUNT(*) FROM sqlar').fetchone()[0]
    finally:
        con.close()


# Linked images

def test_linked_image_saves_only_its_path(view, tmpdir):
    path = make_image_file(tmpdir)
    item = add_image(view, path)
    item.linked = True
    bee = os.path.join(tmpdir, 'scene.bee')
    save_bee(bee, view.scene, create_new=True)
    assert blob_count(bee) == 0

    items = reload(view, bee)
    assert len(items) == 1
    assert isinstance(items[0], BeePixmapItem)
    assert items[0].linked is True
    assert items[0].pixmap().width() == 40


def test_embedded_image_saves_data(view, tmpdir):
    path = make_image_file(tmpdir)
    add_image(view, path)
    bee = os.path.join(tmpdir, 'scene.bee')
    save_bee(bee, view.scene, create_new=True)
    assert blob_count(bee) == 1


def test_linked_image_with_missing_file_is_embedded_on_save(view, tmpdir):
    item = add_image(view, os.path.join(tmpdir, 'gone.png'))
    item.linked = True
    bee = os.path.join(tmpdir, 'scene.bee')
    save_bee(bee, view.scene, create_new=True)
    assert blob_count(bee) == 1
    assert item.linked is False


def test_missing_linked_image_shows_error_and_keeps_data(view, tmpdir):
    path = make_image_file(tmpdir)
    item = add_image(view, path, x=12, y=34)
    item.linked = True
    item.setScale(2)
    bee = os.path.join(tmpdir, 'scene.bee')
    save_bee(bee, view.scene, create_new=True)
    os.remove(path)

    items = reload(view, bee)
    errors = [i for i in view.scene.items() if isinstance(i, BeeErrorItem)]
    assert len(errors) == 1
    assert errors[0].missing_link is True
    assert 'pic.png' in errors[0].toPlainText()
    assert items == []

    # Saving again keeps the missing image in the file
    save_bee(bee, view.scene)
    reload(view, bee)
    errors = [i for i in view.scene.items() if isinstance(i, BeeErrorItem)]
    assert len(errors) == 1


def test_relink_single_missing_image(view, tmpdir):
    path = make_image_file(tmpdir)
    item = add_image(view, path, x=12, y=34)
    item.linked = True
    item.setScale(2)
    bee = os.path.join(tmpdir, 'scene.bee')
    save_bee(bee, view.scene, create_new=True)
    moved_dir = os.path.join(tmpdir, 'moved')
    os.makedirs(moved_dir)
    new_path = os.path.join(moved_dir, 'pic.png')
    shutil.move(path, new_path)

    reload(view, bee)
    with patch.object(view, 'ask_image_file', return_value=new_path):
        view.on_action_relink_missing_images()
    items = list(view.scene.items_for_save())
    assert len(items) == 1
    relinked = items[0]
    assert isinstance(relinked, BeePixmapItem)
    assert os.path.normpath(relinked.filename) == os.path.normpath(new_path)
    assert relinked.linked is True
    assert relinked.pos() == QtCore.QPointF(12, 34)
    assert relinked.scale() == 2

    # Saved into the same row, still without image data
    save_bee(bee, view.scene)
    assert blob_count(bee) == 0
    items = reload(view, bee)
    assert len(items) == 1
    assert isinstance(items[0], BeePixmapItem)


def test_relink_undo_restores_error_item(view, tmpdir):
    path = make_image_file(tmpdir)
    item = add_image(view, path)
    item.linked = True
    bee = os.path.join(tmpdir, 'scene.bee')
    save_bee(bee, view.scene, create_new=True)
    new_path = make_image_file(tmpdir, 'other.png')
    os.remove(path)
    reload(view, bee)
    with patch.object(view, 'ask_image_file', return_value=new_path):
        view.on_action_relink_missing_images()
    view.undo_stack.undo()
    errors = [i for i in view.scene.items() if isinstance(i, BeeErrorItem)]
    assert len(errors) == 1


def test_relink_several_images_searches_folder(view, tmpdir):
    a = add_image(view, make_image_file(tmpdir, 'a.png'))
    b = add_image(view, make_image_file(tmpdir, 'b.png'), x=100)
    a.linked = b.linked = True
    bee = os.path.join(tmpdir, 'scene.bee')
    save_bee(bee, view.scene, create_new=True)
    sub = os.path.join(tmpdir, 'new', 'sub')
    os.makedirs(sub)
    shutil.move(os.path.join(tmpdir, 'a.png'), os.path.join(sub, 'a.png'))
    os.remove(os.path.join(tmpdir, 'b.png'))

    reload(view, bee)
    with patch('PyQt6.QtWidgets.QFileDialog.getExistingDirectory',
               return_value=os.path.join(tmpdir, 'new')):
        with patch('myRef.widgets.BeeNotification') as notify_mock:
            view.on_action_relink_missing_images()
    images = [i for i in view.scene.items() if isinstance(i, BeePixmapItem)]
    errors = [i for i in view.scene.items() if isinstance(i, BeeErrorItem)]
    assert len(images) == 1
    assert len(errors) == 1
    notify_mock.assert_called_once()


def test_relink_without_missing_images_notifies(view):
    with patch('myRef.widgets.BeeNotification') as notify_mock:
        view.on_action_relink_missing_images()
    notify_mock.assert_called_once()


def test_double_click_on_missing_image_relinks(view):
    error = BeeErrorItem('missing')
    error.missing_link = True
    view.scene.addItem(error)
    event = MagicMock()
    event.scenePos.return_value = QtCore.QPointF(5, 5)
    with patch.object(view, 'relink_items') as relink_mock:
        view.scene.mouseDoubleClickEvent(event)
    relink_mock.assert_called_once_with([error])


def test_embed_setting_off_links_opened_files(view, tmpdir, settings):
    from myRef.fileio import load_images
    settings.setValue('Images/embed_local_images', False)
    path = make_image_file(tmpdir)
    worker = MagicMock(canceled=False)
    load_images([path], QtCore.QPointF(0, 0), view.scene, worker)
    view.scene.add_queued_items()
    item = list(view.scene.items_for_save())[0]
    assert item.linked is True


def test_embed_setting_on_embeds_opened_files(view, tmpdir):
    from myRef.fileio import load_images
    path = make_image_file(tmpdir)
    worker = MagicMock(canceled=False)
    load_images([path], QtCore.QPointF(0, 0), view.scene, worker)
    view.scene.add_queued_items()
    assert list(view.scene.items_for_save())[0].linked is False


# Replaced image data is saved

def test_changed_pixmap_is_written_on_save(view, tmpdir):
    item = add_image(view)
    bee = os.path.join(tmpdir, 'scene.bee')
    save_bee(bee, view.scene, create_new=True)
    new = QtGui.QPixmap(7, 7)
    new.fill(QtGui.QColor(0, 0, 255))
    view.undo_stack.push(commands.ReplacePixmaps(
        [{'item': item, 'pixmap': new}]))
    save_bee(bee, view.scene)
    items = reload(view, bee)
    assert items[0].pixmap().width() == 7


# Manage images

def test_image_change_downscales(view):
    item = add_image(view, width=400, height=200)
    item.crop = QtCore.QRectF(100, 50, 200, 100)
    center = view.scene.itemsBoundingRect(items=[item]).center()
    change = image_change(item, ManageOptions(max_side=100))
    view.undo_stack.push(commands.ReplacePixmaps([change]))
    assert item.pixmap().width() == 100
    assert item.pixmap().height() == 50
    assert item.scale() == approx(4)
    assert item.crop == QtCore.QRectF(25, 12.5, 50, 25)
    rect = view.scene.itemsBoundingRect(items=[item])
    assert rect.center().x() == approx(center.x())
    assert rect.width() == approx(200)
    view.undo_stack.undo()
    assert item.pixmap().width() == 400
    assert item.crop == QtCore.QRectF(100, 50, 200, 100)


def test_image_change_small_image_not_affected(view):
    item = add_image(view, width=40, height=20)
    assert image_change(item, ManageOptions(max_side=100)) is None


def test_image_change_discards_cropped_pixels(view):
    item = add_image(view, width=400, height=200)
    item.crop = QtCore.QRectF(100, 50, 200, 100)
    rect = view.scene.itemsBoundingRect(items=[item])
    change = image_change(item, ManageOptions(discard_crop=True))
    view.undo_stack.push(commands.ReplacePixmaps([change]))
    assert item.pixmap().width() == 200
    assert item.crop == QtCore.QRectF(0, 0, 200, 100)
    new_rect = view.scene.itemsBoundingRect(items=[item])
    assert new_rect.center().x() == approx(rect.center().x())
    assert new_rect.width() == approx(rect.width())


def test_image_change_converts_format_without_alpha(view):
    item = add_image(view)
    change = image_change(item, ManageOptions(storage_format='jpg'))
    view.undo_stack.push(commands.ReplacePixmaps([change]))
    assert item.storage_format == 'jpg'
    assert item.pixmap().hasAlphaChannel() is False
    assert item.pixmap_dirty is True
    data, fmt = item.pixmap_to_bytes()
    assert fmt == 'jpg'


def test_image_change_links_to_existing_source(view, tmpdir):
    item = add_image(view, make_image_file(tmpdir))
    change = image_change(item, ManageOptions(location='link'))
    assert change['linked'] is True
    assert 'filename' not in change


def test_image_change_link_exports_pasted_image(view, tmpdir):
    item = add_image(view)
    options = ManageOptions(location='link', link_dir=str(tmpdir),
                            name_template='%3-%2')
    change = image_change(item, options, 0, 3, 'myscene')
    name, ext = os.path.splitext(change['filename'])
    assert name == os.path.join(tmpdir, 'myscene-01')
    assert os.path.isfile(change['filename'])
    # Don't overwrite existing files unless asked to
    change = image_change(item, options, 0, 3, 'myscene')
    assert change['filename'] == os.path.join(tmpdir, 'myscene-01-1' + ext)


def test_image_change_embed_linked_image(view, tmpdir):
    item = add_image(view, make_image_file(tmpdir))
    item.linked = True
    change = image_change(item, ManageOptions(location='embed'))
    view.undo_stack.push(commands.ReplacePixmaps([change]))
    assert item.linked is False
    assert item.pixmap_dirty is True


def test_describe_marks_altered_images(view):
    item = add_image(view, width=400, height=200)
    text = describe(item, ManageOptions(max_side=100))
    assert text.startswith('⚠')
    assert '→ 100 × 50' in text


def test_manage_images_dialog_builds_changes(view, qtbot):
    a = add_image(view, width=400, height=200)
    b = add_image(view, width=40, height=20)
    dialog = ManageImagesDialog(view, [a, b])
    qtbot.addWidget(dialog)
    dialog.resolution_box.setChecked(True)
    dialog.max_side.setValue(100)
    assert dialog.preview.count() == 1
    changes, errors = dialog.build_changes()
    assert errors == []
    assert [c['item'] for c in changes] == [a]


def test_manage_images_action_applies_dialog(view):
    item = add_image(view, width=400, height=200)
    dialog = MagicMock()
    dialog.exec.return_value = 1
    dialog.build_changes.return_value = (
        [image_change(item, ManageOptions(max_side=100))], [])
    with patch('myRef.widgets.manage_images.ManageImagesDialog',
               return_value=dialog):
        view.on_action_manage_images()
    assert item.pixmap().width() == 100


# Crop aspect ratio

def crop_drag(item, handle, start, end, modifiers):
    press = MagicMock()
    press.pos.return_value = QtCore.QPointF(*start)
    item.crop_mode_move = None
    item.crop_temp = QtCore.QRectF(item.crop)
    item.crop_mode = True
    for h in item.crop_handles():
        if h.__name__ == handle:
            item.crop_mode_move = h
    item.crop_mode_event_start = QtCore.QPointF(*start)
    item.crop_mode_start_rect = QtCore.QRectF(item.crop_temp)
    item.crop_mode_press_pos = QtCore.QPointF(*start)
    move = MagicMock()
    move.pos.return_value = QtCore.QPointF(*end)
    move.modifiers.return_value = modifiers
    item.mouseMoveEvent(move)
    return item.crop_temp


def test_crop_shift_keeps_aspect_ratio(view):
    item = add_image(view, width=200, height=100)
    rect = crop_drag(item, 'crop_handle_bottomright', (199, 99), (150, 90),
                     Qt.KeyboardModifier.ShiftModifier)
    assert rect.topLeft() == QtCore.QPointF(0, 0)
    assert rect.width() / rect.height() == approx(2)


def test_crop_shift_alt_makes_square(view):
    item = add_image(view, width=200, height=100)
    rect = crop_drag(item, 'crop_handle_topleft', (1, 1), (21, 11),
                     Qt.KeyboardModifier.ShiftModifier
                     | Qt.KeyboardModifier.AltModifier)
    assert rect.bottomRight() == QtCore.QPointF(200, 100)
    assert rect.width() == approx(rect.height())


def test_crop_without_shift_is_free(view):
    item = add_image(view, width=200, height=100)
    rect = crop_drag(item, 'crop_handle_bottomright', (199, 99), (150, 90),
                     Qt.KeyboardModifier.NoModifier)
    assert rect.width() == approx(151)
    assert rect.height() == approx(91)
