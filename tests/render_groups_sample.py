"""Renders sample groups to a PNG for a visual check (not collected).

Run with: GROUPS_SAMPLE=<file.png> pytest tests/render_groups_sample.py
"""

import os

from PyQt6 import QtGui

from myRef.fileio.export import SceneToPixmapExporter
from myRef.items import BeePixmapItem


COLORS = ['#c0504d', '#4f81bd', '#9bbb59', '#8064a2', '#f79646']


def image(scene, x, y, color, w=120, h=90):
    img = QtGui.QImage(w, h, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(color))
    item = BeePixmapItem(img)
    item.setPos(x, y)
    scene.addItem(item)
    return item


def group(scene, items, name, **style):
    scene.clearSelection()
    for item in items:
        item.setSelected(True)
    scene.group_selection()
    result = items[0].parentItem()
    result.name = name
    result.set_style(**style)
    return result


def test_render_sample(view):
    scene = view.scene
    shapes = [('straight', 'solid'), ('zigzag', 'solid'),
              ('wave', 'solid'), ('scallop', 'dash'),
              ('battlement', 'dot')]
    for row, (shape, line) in enumerate(shapes):
        items = [image(scene, 400 * 0 + i * 140, row * 260, COLORS[i])
                 for i in range(2)]
        group(scene, items, f'{shape} / {line}', border_shape=shape,
              border_style=line, border_width=3,
              border_color='#ffe0c060', color='#40ffffff')

    # Nested groups with opacity and a long title
    a = image(scene, 500, 0, COLORS[0])
    b = image(scene, 640, 0, COLORS[1])
    c = image(scene, 500, 200, COLORS[2])
    inner = group(scene, [a, b], 'Inner', border_shape='wave',
                  border_color='#ff60c0e0')
    group(scene, [inner, c],
          'Outer group with a very long title that gets elided',
          border_width=5, border_style='dash_dot', opacity=0.6)

    scene.fit_groups()
    scene.clearSelection()
    exporter = SceneToPixmapExporter(scene)
    exporter.size = exporter.default_size
    exporter.render_to_image().save(
        os.environ.get('GROUPS_SAMPLE', 'groups_sample.png'))
