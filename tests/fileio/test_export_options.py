"""Tests for export options added in phase 1: exporting only a selection,
file name templates, cropped export and "copy as file"."""

import os
from unittest.mock import patch, MagicMock

import pytest

from PyQt6 import QtCore, QtGui, QtWidgets

from beeref.fileio.export import (
    format_export_name,
    ImagesToDirectoryExporter,
    SceneToPixmapExporter,
    SceneToSVGExporter,
)
from beeref.items import BeePixmapItem, BeeTextItem


def make_image(view, x=0, y=0, w=10, h=10, filename=None,
               color=(255, 0, 0)):
    img = QtGui.QImage(w, h, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(*color))
    item = BeePixmapItem(img, filename=filename)
    view.scene.addItem(item)
    item.setPos(x, y)
    return item


# format_export_name

@pytest.mark.parametrize('template,expected', [
    ('%0', 'bee.png'),
    ('%1', '3.png'),
    ('%2 - %0', '03 - bee.png'),
    ('%3_%2', 'myscene_03.png'),
    ('%%0', '%bee.png'),
    ('a/b:c', 'a_b_c.png'),
    ('  ', 'bee.png'),
])
def test_format_export_name(template, expected):
    item = MagicMock(filename=os.path.join('foo', 'bee.jpg'))
    assert format_export_name(
        template, item=item, index=2, total=12, scene_name='myscene',
        imgformat='png') == expected


def test_format_export_name_pads_to_total_digits():
    item = MagicMock(filename='bee.jpg')
    assert format_export_name(
        '%2', item=item, index=4, total=150, scene_name='',
        imgformat='jpg') == '005.jpg'


def test_format_export_name_without_filename():
    item = MagicMock(filename=None)
    assert format_export_name(
        '%0', item=item, index=4, total=10, scene_name='',
        imgformat='jpg') == '5.jpg'


# ImagesToDirectoryExporter options

def test_export_images_only_given_items(view, tmpdir):
    item1 = make_image(view, filename='a.png')
    make_image(view, filename='b.png')
    text = BeeTextItem('foo')
    view.scene.addItem(text)
    exporter = ImagesToDirectoryExporter(
        view.scene, tmpdir, items=[item1, text], name_template='%0')
    exporter.export()
    assert sorted(os.listdir(tmpdir)) == ['a.png']


def test_export_images_with_template(view, tmpdir):
    make_image(view, filename='b.png')
    make_image(view, filename='a.png')
    exporter = ImagesToDirectoryExporter(
        view.scene, tmpdir, name_template='%3-%2-%0', scene_name='sc')
    exporter.export()
    assert sorted(os.listdir(tmpdir)) == ['sc-01-a.png', 'sc-02-b.png']


def test_export_images_cropped(view, tmpdir):
    item = make_image(view, w=10, h=10, filename='a.png')
    item.crop = QtCore.QRectF(2, 2, 4, 3)
    exporter = ImagesToDirectoryExporter(
        view.scene, tmpdir, name_template='%0', export_cropped=True)
    exporter.export()
    img = QtGui.QImage(os.path.join(tmpdir, 'a.png'))
    assert img.size() == QtCore.QSize(4, 3)


def test_export_images_not_cropped_by_default(view, tmpdir):
    item = make_image(view, w=10, h=10, filename='a.png')
    item.crop = QtCore.QRectF(2, 2, 4, 3)
    exporter = ImagesToDirectoryExporter(
        view.scene, tmpdir, name_template='%0')
    exporter.export()
    img = QtGui.QImage(os.path.join(tmpdir, 'a.png'))
    assert img.size() == QtCore.QSize(10, 10)


# Scene exporters with only some items

def test_scene_exporter_items_rect_only_given_items(view):
    item1 = make_image(view, 0, 0, 10, 10)
    make_image(view, 100, 100, 10, 10)
    exporter = SceneToPixmapExporter(view.scene, items=[item1])
    assert exporter.items_rect == QtCore.QRectF(0, 0, 10, 10)
    assert exporter.items == [item1]


def test_scene_exporter_renders_only_given_items(view):
    item1 = make_image(view, 0, 0, 10, 10, color=(255, 0, 0))
    item2 = make_image(view, 5, 0, 10, 10, color=(0, 0, 255))
    item2.setZValue(10)
    exporter = SceneToPixmapExporter(view.scene, items=[item1])
    exporter.size = QtCore.QSize(10, 10)
    exporter.margin = 0
    exporter.default_size = QtCore.QSize(10, 10)
    image = exporter.render_to_image()
    # The blue item overlaps the red one but isn't exported:
    assert image.pixelColor(8, 5) == QtGui.QColor(255, 0, 0)
    assert item2.isVisible() is True


def test_svg_exporter_only_given_items(view):
    item1 = make_image(view, 0, 0, 10, 10)
    make_image(view, 100, 100, 10, 10)
    exporter = SceneToSVGExporter(view.scene, items=[item1])
    exporter.get_user_input(None)
    svg = exporter.render_to_svg()
    assert len(svg.findall('image')) == 1


# View actions

@patch('beeref.widgets.SceneToPixmapExporterDialog.exec', return_value=1)
@patch('beeref.widgets.SceneToPixmapExporterDialog.value',
       return_value=QtCore.QSize(10, 10))
@patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
def test_on_action_export_selection_as_scene(
        file_mock, value_mock, exec_mock, view, tmpdir, qtbot):
    item1 = make_image(view, 0, 0)
    item2 = make_image(view, 100, 0)
    item1.setSelected(True)
    filename = os.path.join(tmpdir, 'test.png')
    file_mock.return_value = (filename, None)
    view.on_export_finished = MagicMock()
    orig_init = SceneToPixmapExporter.__init__
    captured = {}

    def spy_init(self, scene, items=None):
        captured['items'] = items
        orig_init(self, scene, items=items)

    with patch.object(SceneToPixmapExporter, '__init__', spy_init):
        view.on_action_export_selection_as_scene()
    assert captured['items'] == [item1]
    qtbot.waitUntil(lambda: view.on_export_finished.called is True)
    # Selection is restored after export
    assert item1.isSelected() is True
    assert item2.isSelected() is False


@patch('PyQt6.QtWidgets.QFileDialog.getExistingDirectory')
def test_on_action_export_selected_images_uses_settings(
        dir_mock, view, tmpdir, qtbot, settings):
    settings.setValue('Export/name_template', 'x-%1')
    item1 = make_image(view, filename='a.png')
    make_image(view, filename='b.png')
    item1.setSelected(True)
    dir_mock.return_value = str(tmpdir)
    view.on_export_finished = MagicMock()
    view.on_action_export_selected_images()
    qtbot.waitUntil(lambda: view.on_export_finished.called is True)
    assert os.listdir(tmpdir) == ['x-1.png']


def test_on_action_copy_as_file(view):
    item1 = make_image(view, filename=os.path.join('foo', 'bee.jpg'))
    item1.crop = QtCore.QRectF(0, 0, 5, 5)
    item1.setSelected(True)
    item2 = make_image(view)
    item2.setSelected(True)
    clipboard = QtWidgets.QApplication.clipboard()
    view.on_action_copy_as_file()
    urls = clipboard.mimeData().urls()
    paths = sorted(url.toLocalFile() for url in urls)
    assert [os.path.basename(p) for p in paths] == ['bee.png', 'image.png']
    assert QtGui.QImage(paths[0]).size() == QtCore.QSize(5, 5)


def test_on_action_copy_as_file_without_images_does_nothing(view):
    text = BeeTextItem('foo')
    view.scene.addItem(text)
    text.setSelected(True)
    clipboard = QtWidgets.QApplication.clipboard()
    clipboard.setText('unchanged')
    view.on_action_copy_as_file()
    assert clipboard.text() == 'unchanged'
