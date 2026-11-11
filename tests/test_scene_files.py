"""Tests for opening the last scene, showing the scene in the file
browser and double-clicking the empty canvas."""

import os
from unittest.mock import patch, MagicMock

from PyQt6 import QtCore
from PyQt6.QtCore import Qt


def test_open_last_scene_opens_most_recent(view, settings, tmpdir):
    filename = os.path.join(tmpdir, 'test.bee')
    open(filename, 'w').close()
    settings.update_recent_files(filename)
    with patch.object(view, 'on_action_open_recent_file') as open_mock:
        view.on_action_open_last_scene()
    open_mock.assert_called_once_with(os.path.abspath(filename))


@patch('myRef.widgets.BeeNotification')
def test_open_last_scene_without_recent_files(notify_mock, view, settings):
    with patch.object(view, 'on_action_open_recent_file') as open_mock:
        view.on_action_open_last_scene()
    open_mock.assert_not_called()
    notify_mock.assert_called_once()


@patch('myRef.widgets.BeeNotification')
def test_show_in_file_browser_unsaved(notify_mock, view):
    view.filename = None
    with patch('PyQt6.QtCore.QProcess.startDetached') as proc_mock:
        view.on_action_show_in_file_browser()
    proc_mock.assert_not_called()
    notify_mock.assert_called_once()


@patch('myRef.image_tools.sys.platform', 'win32')
def test_show_in_file_browser_windows(view, tmpdir):
    view.filename = os.path.join(tmpdir, 'test.bee')
    with patch('PyQt6.QtCore.QProcess.startDetached') as proc_mock:
        view.on_action_show_in_file_browser()
    proc_mock.assert_called_once_with(
        'explorer', ['/select,', os.path.normpath(view.filename)])


@patch('myRef.image_tools.sys.platform', 'darwin')
def test_show_in_file_browser_mac(view, tmpdir):
    view.filename = os.path.join(tmpdir, 'test.bee')
    with patch('PyQt6.QtCore.QProcess.startDetached') as proc_mock:
        view.on_action_show_in_file_browser()
    proc_mock.assert_called_once_with(
        'open', ['-R', os.path.abspath(view.filename)])


@patch('myRef.image_tools.sys.platform', 'linux')
def test_show_in_file_browser_linux(view, tmpdir):
    view.filename = os.path.join(tmpdir, 'test.bee')
    with patch('PyQt6.QtGui.QDesktopServices.openUrl') as open_mock:
        view.on_action_show_in_file_browser()
    open_mock.assert_called_once_with(
        QtCore.QUrl.fromLocalFile(str(tmpdir)))


def test_welcome_overlay_double_click_opens(view):
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    with patch.object(view, 'on_action_open') as open_mock:
        view.welcome_overlay.mouseDoubleClickEvent(event)
    open_mock.assert_called_once_with()
    event.accept.assert_called_once_with()
