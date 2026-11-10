"""The scene must only be accessed from the main thread during exports.

Otherwise the application can crash at random, since Qt's graphics scene
isn't thread safe. Tests for a crash wouldn't be reliable, so these tests
check where the scene gets accessed instead.
"""

import os
from unittest.mock import patch

from PyQt6 import QtCore, QtGui
import pytest

from myRef import fileio
from myRef.fileio.export import (
    ImagesToDirectoryExporter,
    SceneToPixmapExporter,
    SceneToSVGExporter,
)
from myRef.items import BeePixmapItem, BeeTextItem
from myRef.scene import BeeGraphicsScene


@pytest.fixture
def scene_threads():
    """The threads from which the scene has been accessed."""

    threads = set()
    patchers = []

    for name in ('render', 'items', 'itemsBoundingRect', 'selectedItems'):
        def wrapper(self, *args, _original=getattr(BeeGraphicsScene, name),
                    **kwargs):
            threads.add(QtCore.QThread.currentThread())
            return _original(self, *args, **kwargs)
        patchers.append(patch.object(BeeGraphicsScene, name, wrapper))

    for patcher in patchers:
        patcher.start()
    yield threads
    for patcher in patchers:
        patcher.stop()


@pytest.fixture
def filled_view(view):
    image = BeePixmapItem(
        QtGui.QImage(100, 100, QtGui.QImage.Format.Format_RGB32))
    image.save_id = 1
    view.scene.addItem(image)
    view.scene.addItem(BeeTextItem('foo'))
    return view


def run_in_worker(qtbot, func, *args):
    results = []
    worker = fileio.ThreadedIO(func, *args)
    worker.finished.connect(lambda *result: results.append(result))
    worker.start()
    qtbot.waitUntil(lambda: bool(results))
    worker.wait()
    return results[0]


def test_export_to_pixmap_uses_scene_only_in_main_thread(
        filled_view, tmpdir, qtbot, scene_threads):
    filename = os.path.join(tmpdir, 'foo.png')
    exporter = SceneToPixmapExporter(filled_view.scene)
    exporter.size = QtCore.QSize(100, 100)
    exporter.prepare()
    scene_threads.clear()

    assert run_in_worker(qtbot, exporter.export, filename) == (filename, [])
    assert scene_threads == set()
    assert QtGui.QImage(filename).size() == QtCore.QSize(100, 100)


def test_export_to_svg_uses_scene_only_in_main_thread(
        filled_view, tmpdir, qtbot, scene_threads):
    filename = os.path.join(tmpdir, 'foo.svg')
    exporter = SceneToSVGExporter(filled_view.scene)
    exporter.get_user_input(None)
    exporter.prepare()
    scene_threads.clear()

    assert run_in_worker(qtbot, exporter.export, filename) == (filename, [])
    assert scene_threads == set()
    with open(filename) as f:
        content = f.read()
    assert '<image' in content
    assert '<text' in content


def test_export_images_uses_scene_only_in_main_thread(
        filled_view, tmpdir, qtbot, scene_threads):
    exporter = ImagesToDirectoryExporter(filled_view.scene, str(tmpdir))
    scene_threads.clear()

    assert run_in_worker(qtbot, exporter.export) == (str(tmpdir), [])
    assert scene_threads == set()
    assert len(os.listdir(tmpdir)) == 1


@patch('myRef.widgets.SceneToPixmapExporterDialog.exec', return_value=1)
@patch('myRef.widgets.SceneToPixmapExporterDialog.value',
       return_value=QtCore.QSize(100, 100))
@patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
def test_export_action_renders_in_main_thread(
        file_mock, value_mock, exec_mock, filled_view, tmpdir, qtbot,
        scene_threads):
    filename = os.path.join(tmpdir, 'foo.png')
    file_mock.return_value = (filename, None)
    results = []
    filled_view.on_export_finished = lambda *args: results.append(args)

    filled_view.on_action_export_scene()
    qtbot.waitUntil(lambda: bool(results))
    filled_view.worker.wait()

    assert results == [(filename, [])]
    assert scene_threads == {QtCore.QThread.currentThread()}
    assert QtGui.QImage(filename).size() == QtCore.QSize(100, 100)


def test_export_to_pixmap_without_prepare_still_works(filled_view, tmpdir):
    filename = os.path.join(tmpdir, 'foo.png')
    exporter = SceneToPixmapExporter(filled_view.scene)
    exporter.size = QtCore.QSize(100, 100)
    exporter.export(filename)
    assert QtGui.QImage(filename).size() == QtCore.QSize(100, 100)


def test_export_to_pixmap_releases_image(filled_view, tmpdir):
    exporter = SceneToPixmapExporter(filled_view.scene)
    exporter.size = QtCore.QSize(100, 100)
    exporter.prepare()
    assert exporter.image is not None
    exporter.export(os.path.join(tmpdir, 'foo.png'))
    assert exporter.image is None


def test_svg_export_keeps_z_order(filled_view):
    items = list(filled_view.scene.items())
    items[0].setZValue(5)
    items[1].setZValue(-5)
    exporter = SceneToSVGExporter(filled_view.scene)
    assert exporter.items == [items[1], items[0]]
