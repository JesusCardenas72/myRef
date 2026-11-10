import os.path
import pytest
import uuid

from unittest.mock import MagicMock, patch

from PyQt6 import QtGui, QtWidgets


def pytest_configure(config):
    # Ignore logging configuration for myRef during test runs. This
    # avoids logging to the regular log file and spamming test output
    # with debug messages.
    #
    # This needs to be done before the application code is even loaded since
    # logging configuration happens on module level
    import logging.config
    logging.config.dictConfig = MagicMock


@pytest.fixture(autouse=True)
def reset_myRef_actions():
    from myRef.actions.actions import actions
    for key in list(actions.keys()):
        if key.startswith('recent_files_'):
            actions.pop(key)


@pytest.fixture(autouse=True)
def english_ui():
    """Tests expect English strings, regardless of the system language."""
    from myRef import i18n
    with patch('myRef.i18n.detect_system_language', return_value='en'):
        i18n.set_language('en')
        yield
        i18n.set_language('en')


@pytest.fixture(autouse=True)
def commandline_args():
    config_patcher = patch('myRef.view.commandline_args')
    config_mock = config_patcher.start()
    config_mock.filenames = []
    yield config_mock
    config_patcher.stop()


@pytest.fixture(autouse=True)
def settings(tmpdir):
    from myRef.config import BeeSettings
    dir_patcher = patch('myRef.config.BeeSettings.get_settings_dir',
                        return_value=tmpdir.dirname)
    dir_patcher.start()
    settings = BeeSettings()
    yield settings
    settings.clear()
    dir_patcher.stop()


@pytest.fixture(autouse=True)
def kbsettings(tmpdir):
    from myRef.config import KeyboardSettings
    dir_patcher = patch('myRef.config.BeeSettings.get_settings_dir',
                        return_value=tmpdir.dirname)
    dir_patcher.start()
    kbsettings = KeyboardSettings()
    yield kbsettings
    kbsettings.clear()
    dir_patcher.stop()


@pytest.fixture
def main_window(qtbot):
    from myRef.__main__ import myRefMainWindow
    app = QtWidgets.QApplication.instance()
    main = myRefMainWindow(app)
    qtbot.addWidget(main)
    yield main


@pytest.fixture
def view(main_window):
    yield main_window.view


@pytest.fixture
def imgfilename3x3():
    root = os.path.dirname(__file__)
    yield os.path.join(root, 'assets', 'test3x3.png')


@pytest.fixture
def imgdata3x3(imgfilename3x3):
    with open(imgfilename3x3, 'rb') as f:
        imgdata3x3 = f.read()
    yield imgdata3x3


@pytest.fixture
def tmpfile(tmpdir):
    yield os.path.join(tmpdir, str(uuid.uuid4()))


@pytest.fixture
def item():
    from myRef.items import BeePixmapItem
    yield BeePixmapItem(QtGui.QImage(10, 10, QtGui.QImage.Format.Format_RGB32))


@pytest.fixture(scope="session")
def qapp():
    from myRef.__main__ import myRefApplication
    yield myRefApplication([])


@pytest.fixture(autouse=True)
def reset_shortcut_context():
    from myRef.actions.actions import actions, CONTEXT_GLOBAL
    actions.active_context = CONTEXT_GLOBAL
    yield
    actions.active_context = CONTEXT_GLOBAL
