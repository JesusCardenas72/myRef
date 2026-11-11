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

"""Development auto-reload.

Run ``python -m myRef.devreload`` instead of ``python -m myRef``. A
supervisor process starts the app; when a source file in the package
changes, the app saves the canvas (items, zoom, position, file name,
unsaved flag) to a temporary state directory, exits, and is started
again by the supervisor, which then restores that state.

Only active when the ``MYREF_DEV_RELOAD`` environment variable points to
the state directory; normal runs are unaffected.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ENV_VAR = 'MYREF_DEV_RELOAD'
RELOAD_EXIT_CODE = 3
PKG_DIR = Path(__file__).resolve().parent
WATCHED_SUFFIXES = {'.py', '.json', '.qss', '.css'}
POLL_MS = 500
DEBOUNCE_MS = 300

restart_requested = False


def source_snapshot(root=PKG_DIR):
    snapshot = {}
    for path in root.rglob('*'):
        if '__pycache__' in path.parts:
            continue
        if path.suffix in WATCHED_SUFFIXES:
            try:
                snapshot[path] = path.stat().st_mtime_ns
            except OSError:
                pass
    return snapshot


def changed_files(old, new):
    return sorted(
        str(p.relative_to(PKG_DIR))
        for p in set(old) | set(new) if old.get(p) != new.get(p))


# ---------------------------------------------------------------------------
# App side (runs inside the myRef process)
# ---------------------------------------------------------------------------

def install(window):
    """Restore the previous canvas state and start watching sources."""
    from PyQt6 import QtCore

    state_dir = Path(os.environ[ENV_VAR])
    _restore(window.view, state_dir)

    baseline = source_snapshot()
    timer = QtCore.QTimer(window)
    timer.setInterval(POLL_MS)

    def check():
        current = source_snapshot()
        if current == baseline:
            return
        timer.stop()
        print('[dev] Cambios: ' + ', '.join(changed_files(baseline, current)),
              flush=True)
        QtCore.QTimer.singleShot(
            DEBOUNCE_MS, lambda: _save_and_restart(window, state_dir, timer))

    timer.timeout.connect(check)
    timer.start()
    window._dev_reload_timer = timer


def _busy(view):
    from PyQt6 import QtWidgets
    worker = getattr(view, 'worker', None)
    if worker is not None and worker.isRunning():
        return 'cargando/guardando un archivo'
    if QtWidgets.QApplication.activeModalWidget() is not None:
        return 'hay un diálogo abierto'
    return None


def _save_and_restart(window, state_dir, timer):
    global restart_requested
    from PyQt6 import QtCore, QtWidgets
    from myRef import fileio

    view = window.view
    reason = _busy(view)
    if reason:
        print(f'[dev] Recarga en espera: {reason}', flush=True)
        QtCore.QTimer.singleShot(
            1000, lambda: _save_and_restart(window, state_dir, timer))
        return

    view.exit_draw_mode(finish=True)
    view.cancel_active_modes()

    state_dir.mkdir(parents=True, exist_ok=True)
    scene_file = state_dir / 'scene.mref'
    tmp_file = state_dir / 'scene.tmp.mref'
    item_count = len(list(view.scene.items_for_save()))
    has_items = item_count > 0
    try:
        if has_items:
            fileio.save_bee(str(tmp_file), view.scene, create_new=True)
            os.replace(tmp_file, scene_file)
        elif scene_file.exists():
            scene_file.unlink()
    except Exception as e:  # keep the app running, nothing is lost
        print(f'[dev] No se pudo guardar el lienzo, no se recarga: {e}',
              flush=True)
        timer.start()
        return

    t = view.transform()
    center = view.mapToScene(view.viewport().rect().center())
    state = {
        'filename': view.filename,
        'dirty': not view.undo_stack.isClean(),
        'transform': [t.m11(), t.m12(), t.m13(),
                      t.m21(), t.m22(), t.m23(),
                      t.m31(), t.m32(), t.m33()],
        'center': [center.x(), center.y()],
    }
    (state_dir / 'state.json').write_text(json.dumps(state), 'utf-8')

    print(f'[dev] Lienzo guardado ({item_count} '
          f'elementos, zoom {t.m11():.2f}), reiniciando...', flush=True)
    restart_requested = True
    app = QtWidgets.QApplication.instance()
    app.setQuitOnLastWindowClosed(False)
    # Avoid selectionChanged reaching the view while the scene is torn down
    view.scene.blockSignals(True)
    window.close()  # stores window geometry
    app.exit(RELOAD_EXIT_CODE)


def _restore(view, state_dir):
    from PyQt6 import QtCore, QtGui

    state_file = state_dir / 'state.json'
    if not state_file.exists():
        return
    state = json.loads(state_file.read_text('utf-8'))
    scene_file = state_dir / 'scene.mref'
    recent = view.settings.get_recent_files()

    def apply_state(*args):
        # Loading the temp file set it as the current file and added it to
        # the recent files; undo both.
        view._filename = None
        _write_recent_files(view.settings, recent)
        if state['filename']:
            view.filename = state['filename']
        # Items carry ids of the temp file: make the next save to the real
        # file a full rewrite.
        view.scene.clear_save_ids()
        view.undo_stack.clear()
        if state['dirty'] or (scene_file.exists() and not state['filename']):
            view.undo_stack.resetClean()
        view.update_window_title()
        view.setTransform(QtGui.QTransform(*state['transform']))
        view.centerOn(QtCore.QPointF(*state['center']))
        count = len(list(view.scene.items_for_save()))
        print(f'[dev] Lienzo restaurado ({count} '
              f'elementos, zoom {view.get_scale():.2f})', flush=True)

    if scene_file.exists():
        view.open_from_file(str(scene_file))
        # Connected after the view's own handler, so this runs after the
        # automatic "fit scene".
        view.worker.finished.connect(
            lambda *a: QtCore.QTimer.singleShot(0, apply_state))
    else:
        QtCore.QTimer.singleShot(0, apply_state)


def _write_recent_files(settings, values):
    settings.remove('RecentFiles')
    settings.beginWriteArray('RecentFiles')
    for i, filename in enumerate(values[:10]):
        settings.setArrayIndex(i)
        settings.setValue('path', filename)
    settings.endArray()


# ---------------------------------------------------------------------------
# Supervisor side
# ---------------------------------------------------------------------------

def supervise(argv):
    state_dir = Path(tempfile.gettempdir()) / 'myRef-devreload'
    shutil.rmtree(state_dir, ignore_errors=True)
    state_dir.mkdir(parents=True)
    env = dict(os.environ, **{ENV_VAR: str(state_dir)})
    cmd = [sys.executable, '-m', 'myRef', *argv]

    print('[dev] Recarga automática activa: guarda un archivo de myRef/ '
          'y la app se reiniciará con el lienzo intacto.', flush=True)
    try:
        while True:
            snapshot = source_snapshot()
            rc = subprocess.call(cmd, env=env)
            if rc == RELOAD_EXIT_CODE:
                cmd = [sys.executable, '-m', 'myRef']  # args only first time
                continue
            if rc == 0:
                print('[dev] Ventana cerrada, fin.', flush=True)
                return 0
            print(f'[dev] La app terminó con error (código {rc}). '
                  'Corrige el código y guarda para reintentar '
                  '(Ctrl+C para salir).', flush=True)
            while source_snapshot() == snapshot:
                time.sleep(POLL_MS / 1000)
            time.sleep(DEBOUNCE_MS / 1000)
            cmd = [sys.executable, '-m', 'myRef']
    except KeyboardInterrupt:
        return 0
    finally:
        shutil.rmtree(state_dir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(supervise(sys.argv[1:]))
