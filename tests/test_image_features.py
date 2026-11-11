"""Tests for the image features from PureRef's handbook (PLAN_IMAGENES.md):
arranging by name/order, focusing, slideshow, source, replacing,
pasting URLs and editing items."""

import os.path
from unittest.mock import MagicMock, patch

import httpretty
from pytest import approx

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef.actions.actions import actions
from myRef import commands
from myRef.fileio.image import image_urls_from_html, load_images_from_url
from myRef.items import BeePixmapItem, BeeTextItem, BeeGroupItem


def add_image(view, x=0, y=0, width=100, height=100, filename=None,
              name=''):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(10, 20, 30))
    item = BeePixmapItem(img, filename)
    item.name = name
    view.scene.addItem(item)
    item.setPos(x, y)
    return item


def x_positions(items):
    return [round(item.pos().x()) for item in items]


# Arranging

def test_arrange_square_by_name_uses_name_then_file_name(view):
    a = add_image(view, filename='/z/b.png')
    b = add_image(view, filename='/a/c.png', name='a item')
    c = add_image(view, filename='/a/a.png')
    view.scene.arrange_square(order='name', items=[a, b, c])
    # b ("a item"), c ("a.png"), a ("b.png")
    assert b.pos().x() < c.pos().x()
    assert c.pos().y() == b.pos().y()
    assert a.pos().y() > b.pos().y()


def test_arrange_square_by_order_uses_hierarchy_order(view):
    a = add_image(view, filename='/b.png')
    b = add_image(view, filename='/a.png')
    a.sort_order = 0
    b.sort_order = 1
    view.scene.arrange_square(order='order', items=[a, b])
    assert a.pos().x() < b.pos().x()


def test_arrange_square_twice_reverses_order(view):
    a = add_image(view, filename='/a.png')
    b = add_image(view, filename='/b.png')
    view.scene.arrange_square(order='filename', items=[a, b])
    assert a.pos().x() < b.pos().x()
    view.scene.arrange_square(order='filename', items=[a, b])
    assert a.pos().x() > b.pos().x()
    view.scene.arrange_square(order='filename', items=[a, b])
    assert a.pos().x() < b.pos().x()


def test_arrange_square_not_reversed_after_other_change(view):
    a = add_image(view, filename='/a.png')
    b = add_image(view, filename='/b.png')
    view.scene.arrange_square(order='filename', items=[a, b])
    view.undo_stack.push(commands.MoveItemsBy([a], QtCore.QPointF(5, 5)))
    view.scene.arrange_square(order='filename', items=[a, b])
    assert a.pos().x() < b.pos().x()


def test_arrange_shortcuts_follow_pureref():
    assert actions['arrange_square_name'].shortcuts == ['Ctrl+Alt+N']
    assert actions['arrange_square'].shortcuts == ['Ctrl+Alt+D']
    assert actions['arrange_square_order'].shortcuts == ['Ctrl+Alt+O']
    assert actions['normalize_longest_side'].shortcuts == ['Ctrl+Alt+Up']
    assert actions['normalize_size'].shortcuts == []


def test_group_scoped_arrange_by_name_exists():
    assert 'group_arrange_square_name' in actions
    assert 'group_arrange_square_order' in actions


# Edit item

def test_edit_item_starts_editing_text(view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    item.setSelected(True)
    with patch.object(item, 'enter_edit_mode') as edit_mock:
        view.on_action_edit_item()
    edit_mock.assert_called_once_with()


def test_edit_item_enters_group(view):
    group = BeeGroupItem()
    view.scene.addItem(group)
    group.setSelected(True)
    with patch.object(view.scene, 'enter_group') as enter_mock:
        view.on_action_edit_item()
    enter_mock.assert_called_once_with()


def test_edit_item_ignores_multi_selection(view):
    a = BeeTextItem('a')
    b = BeeTextItem('b')
    for item in (a, b):
        view.scene.addItem(item)
        item.setSelected(True)
    with patch.object(a, 'enter_edit_mode') as edit_mock:
        view.on_action_edit_item()
    edit_mock.assert_not_called()


def test_edit_item_shortcut_is_return():
    assert actions['edit_item'].shortcuts == ['Return']


def test_return_goes_to_crop_mode_instead_of_shortcut(view):
    item = add_image(view)
    item.setSelected(True)
    view.scene.crop_item = item
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.ShortcutOverride,
                            Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    assert view.event(event) is True
    assert event.isAccepted()
    view.scene.crop_item = None


# Focus next/previous

def test_focus_next_steps_through_images_in_order(view):
    a = add_image(view, 0, 0, filename='/a.png')
    b = add_image(view, 200, 0, filename='/b.png')
    add_image(view, 400, 0, filename='/c.png')
    with patch.object(view, 'fit_rect') as fit_mock:
        view.on_action_focus_next()
        assert view.focus_item is a
        view.on_action_focus_next()
        assert view.focus_item is b
        view.on_action_focus_previous()
        assert view.focus_item is a
        view.on_action_focus_previous()
        assert view.focus_item.filename == '/c.png'
    assert fit_mock.call_count == 4


def test_focus_next_starts_at_selected_image(view):
    add_image(view, filename='/a.png')
    b = add_image(view, filename='/b.png')
    c = add_image(view, filename='/c.png')
    b.setSelected(True)
    with patch.object(view, 'fit_rect'):
        view.on_action_focus_next()
    assert view.focus_item is c


def test_focus_next_without_images_does_nothing(view):
    with patch.object(view, 'fit_rect') as fit_mock:
        view.on_action_focus_next()
    fit_mock.assert_not_called()


# Slideshow

def test_slideshow_uses_selected_images(view, settings):
    settings.setValue('Images/slideshow_interval', 3)
    a = add_image(view, filename='/a.png')
    b = add_image(view, filename='/b.png')
    add_image(view, filename='/c.png')
    a.setSelected(True)
    b.setSelected(True)
    with patch.object(view, 'fit_rect'):
        view.start_slideshow()
        assert view.is_slideshow_running()
        assert view.slideshow_timer.interval() == 3000
        assert view.focus_item is a
        view.slideshow_next()
        assert view.focus_item is b
        view.slideshow_next()
        assert view.focus_item is a
    assert actions['slideshow'].qaction.isChecked() is True
    view.stop_slideshow()
    assert not view.is_slideshow_running()
    assert actions['slideshow'].qaction.isChecked() is False


def test_slideshow_without_images_notifies(view):
    with patch('myRef.widgets.BeeNotification') as notify_mock:
        view.start_slideshow()
    notify_mock.assert_called_once()
    assert not view.is_slideshow_running()


def test_esc_stops_slideshow_before_deselecting(view):
    a = add_image(view)
    a.setSelected(True)
    with patch.object(view, 'fit_rect'):
        view.start_slideshow()
    view.on_action_deselect_all()
    assert not view.is_slideshow_running()
    assert a.isSelected()


def test_mouse_press_stops_slideshow(view):
    add_image(view)
    with patch.object(view, 'fit_rect'):
        view.start_slideshow()
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.MiddleButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    event.position.return_value = QtCore.QPointF(5, 5)
    view.mousePressEvent(event)
    assert not view.is_slideshow_running()


# Open source

def test_open_source_url(view):
    item = add_image(view, filename='https://example.com/a.png')
    item.setSelected(True)
    with patch('PyQt6.QtGui.QDesktopServices.openUrl') as open_mock:
        view.on_action_open_source()
    open_mock.assert_called_once_with(
        QtCore.QUrl('https://example.com/a.png'))


def test_open_source_local_file(view, imgfilename3x3):
    item = add_image(view, filename=imgfilename3x3)
    item.setSelected(True)
    with patch('myRef.image_tools.reveal_in_file_browser') as reveal_mock:
        view.on_action_open_source()
    reveal_mock.assert_called_once_with(imgfilename3x3)


def test_open_source_without_filename_notifies(view):
    item = add_image(view)
    item.setSelected(True)
    with patch('myRef.widgets.BeeNotification') as notify_mock:
        view.on_action_open_source()
    notify_mock.assert_called_once()


def test_open_source_missing_file_notifies(view, tmpdir):
    item = add_image(view, filename=os.path.join(tmpdir, 'gone.png'))
    item.setSelected(True)
    with patch('myRef.widgets.BeeNotification') as notify_mock:
        view.on_action_open_source()
    notify_mock.assert_called_once()


# Replace image

def test_replace_image_keeps_center_and_longest_side(view, imgfilename3x3):
    item = add_image(view, 50, 60, width=100, height=50)
    item.setSelected(True)
    old_center = view.scene.itemsBoundingRect(items=[item]).center()
    with patch.object(view, 'ask_image_file',
                      return_value=imgfilename3x3):
        view.on_action_replace_image()
    assert item.pixmap().width() == 3
    assert item.filename == imgfilename3x3
    rect = view.scene.itemsBoundingRect(items=[item])
    assert rect.center().x() == approx(old_center.x())
    assert rect.center().y() == approx(old_center.y())
    assert rect.width() == approx(100)
    assert item.pixmap_dirty is True

    view.undo_stack.undo()
    assert item.pixmap().width() == 100
    assert item.pos() == QtCore.QPointF(50, 60)
    assert item.filename is None


def test_replace_image_canceled(view):
    item = add_image(view)
    item.setSelected(True)
    with patch.object(view, 'ask_image_file', return_value=''):
        view.on_action_replace_image()
    assert view.undo_stack.count() == 0


# Pasting

def test_paste_url_text_imports_from_url(view):
    clipboard = QtWidgets.QApplication.clipboard()
    clipboard.setText('https://example.com/page')
    with patch.object(view, 'do_insert_images') as insert_mock:
        view.on_action_paste()
    urls = insert_mock.call_args[0][0]
    assert urls == [QtCore.QUrl('https://example.com/page')]


def test_paste_regular_text_creates_note(view):
    clipboard = QtWidgets.QApplication.clipboard()
    clipboard.setText('some words')
    with patch.object(view, 'do_insert_images') as insert_mock:
        view.on_action_paste()
    insert_mock.assert_not_called()
    assert isinstance(view.scene.items()[0], BeeTextItem)


def test_paste_copied_files(view, imgfilename3x3):
    mimedata = QtCore.QMimeData()
    mimedata.setUrls([QtCore.QUrl.fromLocalFile(imgfilename3x3)])
    QtWidgets.QApplication.clipboard().setMimeData(mimedata)
    with patch.object(view, 'do_insert_images') as insert_mock:
        view.on_action_paste()
    urls = insert_mock.call_args[0][0]
    assert os.path.normpath(urls[0].toLocalFile()) == imgfilename3x3


# Images from web pages

def test_image_urls_from_html():
    html = b'''<html><head>
        <meta property="og:image" content="/og.jpg">
        </head><body>
        <img src="a.png">
        <img src="small.png" srcset="small.png 100w, big.png 800w">
        <img data-src="lazy.jpg" src="placeholder.gif">
        <img src="data:image/png;base64,AAAA">
        <a href="full.jpeg">full</a>
        <a href="page.html">page</a>
        <img src="a.png">
        </body></html>'''
    urls = image_urls_from_html(html, 'https://example.com/dir/page')
    assert urls == [
        'https://example.com/og.jpg',
        'https://example.com/dir/a.png',
        'https://example.com/dir/big.png',
        'https://example.com/dir/small.png',
        'https://example.com/dir/lazy.jpg',
        'https://example.com/dir/full.jpeg',
    ]


@httpretty.activate
def test_load_images_from_url_web_page(qapp, imgfilename3x3):
    big = QtGui.QImage(80, 80, QtGui.QImage.Format.Format_RGB32)
    big.fill(QtGui.QColor(1, 2, 3))
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    big.save(buffer, 'PNG')
    with open(imgfilename3x3, 'rb') as f:
        tiny = f.read()
    httpretty.register_uri(
        httpretty.GET, 'https://example.com/page',
        body='<img src="big.png"><img src="tiny.png">',
        content_type='text/html; charset=utf-8')
    httpretty.register_uri(
        httpretty.GET, 'https://example.com/big.png',
        body=bytes(buffer.data()), content_type='image/png')
    httpretty.register_uri(
        httpretty.GET, 'https://example.com/tiny.png',
        body=tiny, content_type='image/png')
    results = load_images_from_url('https://example.com/page')
    # The tiny image is skipped
    assert len(results) == 1
    img, url = results[0]
    assert url == 'https://example.com/big.png'
    assert img.width() == 80


@httpretty.activate
def test_load_images_from_url_direct_image(qapp, imgdata3x3):
    httpretty.register_uri(
        httpretty.GET, 'https://example.com/img.png',
        body=imgdata3x3, content_type='image/png')
    results = load_images_from_url('https://example.com/img.png')
    assert len(results) == 1
    assert results[0][0].width() == 3


@httpretty.activate
def test_load_images_from_url_page_without_images(qapp):
    httpretty.register_uri(
        httpretty.GET, 'https://example.com/page',
        body='<p>nothing</p>', content_type='text/html')
    results = load_images_from_url('https://example.com/page')
    assert len(results) == 1
    assert results[0][0].isNull()


# Default sampling

def test_default_sampling_nearest(settings):
    settings.setValue('Images/default_sampling', 'nearest')
    item = BeePixmapItem(QtGui.QImage(5, 5, QtGui.QImage.Format.Format_RGB32))
    assert item.nearest_neighbor is True


def test_default_sampling_bilinear(settings):
    item = BeePixmapItem(QtGui.QImage(5, 5, QtGui.QImage.Format.Format_RGB32))
    assert item.nearest_neighbor is False


# Unlock button

def test_click_on_locked_item_offers_unlocking(view):
    item = add_image(view, 0, 0)
    item.set_item_locked(True)
    view.show_unlock_button(item)
    assert view.unlock_button.isVisibleTo(view.viewport())
    view.unlock_button.click()
    assert item.locked is False
    assert item.isSelected()
    view.undo_stack.undo()
    assert item.locked is True


def test_scene_press_on_locked_item_shows_unlock_button(view):
    item = add_image(view, 0, 0)
    item.set_item_locked(True)
    with patch.object(view, 'show_unlock_button') as show_mock:
        view.scene.notify_locked_item_at(QtCore.QPointF(50, 50))
    show_mock.assert_called_once_with(item)


def test_scene_press_on_unlocked_item_no_unlock_button(view):
    add_image(view, 0, 0)
    with patch.object(view, 'show_unlock_button') as show_mock:
        view.scene.notify_locked_item_at(QtCore.QPointF(50, 50))
    show_mock.assert_not_called()


def test_edit_item_gives_text_keyboard_focus(view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_edit_item()
    assert view.scene.edit_item is item
    assert item.hasFocus() or view.scene.focusItem() is item
    assert item.textCursor().position() == 3
    item.exit_edit_mode()


def test_escape_override_while_editing_text(view):
    # Used to raise an AttributeError (wrong ``actions`` object)
    from myRef.actions.actions import CONTEXT_TEXT_EDIT, actions as alist
    alist.set_context(CONTEXT_TEXT_EDIT)
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.ShortcutOverride,
                            Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    assert view.event(event) is True
    assert event.isAccepted()
