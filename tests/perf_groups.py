"""Performance baseline for groups (not collected by default).

Run with: pytest tests/perf_groups.py -s
"""

import time

import pytest

from PyQt6 import QtCore, QtGui

from myRef.items import BeePixmapItem


@pytest.mark.parametrize('wavy,nested', [
    (False, False), (True, False), (False, True)])
def test_perf_groups(view, wavy, nested):
    scene = view.scene
    images = []
    for i in range(500):
        item = BeePixmapItem(
            QtGui.QImage(100, 80, QtGui.QImage.Format.Format_RGB32))
        item.setPos((i % 25) * 120, (i // 25) * 100)
        scene.addItem(item)
        images.append(item)
    for g in range(20):
        scene.clearSelection()
        for item in images[g * 25:(g + 1) * 25]:
            item.setSelected(True)
        scene.group_selection()
    scene.clearSelection()
    if nested:
        # 4 groups of 5 groups each, all in one top group
        groups = sorted(scene.groups(), key=lambda g: g.scenePos().y())
        for i in range(4):
            scene.clearSelection()
            for group in groups[i * 5:(i + 1) * 5]:
                group.setSelected(True)
            scene.group_selection()
        scene.clearSelection()
        for group in scene.groups():
            if group.parentItem() is None:
                group.setSelected(True)
        scene.group_selection()
        scene.clearSelection()
        assert len(scene.groups()) == 25
    if wavy:
        for group in scene.groups():
            group.set_style(border_shape='wave', border_style='dash')

    n = 50
    start = time.perf_counter()
    for _ in range(n):
        scene.fit_groups()
    fit_ms = (time.perf_counter() - start) / n * 1000

    rect = scene.itemsBoundingRect()
    image = QtGui.QImage(1600, 1000, QtGui.QImage.Format.Format_ARGB32)
    n = 10
    start = time.perf_counter()
    for _ in range(n):
        painter = QtGui.QPainter(image)
        scene.render(painter, QtCore.QRectF(image.rect()), rect)
        painter.end()
    render_ms = (time.perf_counter() - start) / n * 1000
    print(f'\nwavy={wavy} nested={nested} fit_groups: {fit_ms:.2f} ms  '
          f'render: {render_ms:.2f} ms')
