"""Tests for groups, the hierarchy, item locking and comments (phase 4)."""

from unittest.mock import MagicMock, patch

import pytest

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from myRef import commands
from myRef import hierarchy
from myRef.actions.actions import actions
from myRef.fileio.export import SceneToPixmapExporter, SceneToSVGExporter
from myRef.fileio.sql import SQLiteIO
from myRef.items import (
    BeeGroupItem,
    BeePixmapItem,
    BeeTextItem,
    items_in_order,
)
from myRef.widgets.hierarchy import CommentDialog, HierarchyTree


def make_image(view, x=0, y=0, w=100, h=80, name=None, selected=False):
    item = BeePixmapItem(
        QtGui.QImage(w, h, QtGui.QImage.Format.Format_RGB32), name)
    item.setPos(x, y)
    view.scene.addItem(item)
    if selected:
        item.setSelected(True)
    return item


def make_group(view, items):
    for item in items:
        item.setSelected(True)
    view.scene.group_selection()
    groups = list(view.scene.items_by_type('group'))
    assert len(groups) == 1
    return groups[0]


def mouse_event(pos, modifiers=Qt.KeyboardModifier.NoModifier,
                button=Qt.MouseButton.LeftButton):
    return MagicMock(
        scenePos=MagicMock(return_value=QtCore.QPointF(*pos)),
        button=MagicMock(return_value=button),
        modifiers=MagicMock(return_value=modifiers))


def assert_points_equal(p1, p2):
    assert p1.x() == pytest.approx(p2.x(), abs=1e-6)
    assert p1.y() == pytest.approx(p2.y(), abs=1e-6)


# Hierarchy helpers

@pytest.mark.parametrize('flip', [1, -1])
@pytest.mark.parametrize('rotation', [0, 30, 90, 200])
@pytest.mark.parametrize('scale', [1, 0.5, 2.5])
def test_decompose_transform_roundtrip(qapp, flip, rotation, scale):
    item = QtWidgets.QGraphicsRectItem(0, 0, 5, 5)
    item.setTransform(QtGui.QTransform.fromScale(flip, 1))
    item.setScale(scale)
    item.setRotation(rotation)
    item.setPos(7, 3)
    pos, s, r, f = hierarchy.decompose_transform(item.sceneTransform())
    assert pos == QtCore.QPointF(7, 3)
    assert s == pytest.approx(scale)
    assert r % 360 == pytest.approx(rotation, abs=1e-6)
    assert f == flip


def test_set_parent_keep_transform_keeps_scene_corners(view):
    parent = make_image(view, 50, 60)
    parent.setScale(2)
    parent.setRotation(30)
    child = make_image(view, 300, 10)
    child.setScale(0.5)
    child.setRotation(10)
    child.do_flip()
    before = child.corners_scene_coords
    hierarchy.set_parent_keep_transform(child, parent)
    assert child.parentItem() is parent
    for p1, p2 in zip(before, child.corners_scene_coords):
        assert_points_equal(p1, p2)
    hierarchy.set_parent_keep_transform(child, None)
    assert child.parentItem() is None
    for p1, p2 in zip(before, child.corners_scene_coords):
        assert_points_equal(p1, p2)


def test_top_most_removes_descendants(view):
    parent = make_image(view)
    child = make_image(view)
    other = make_image(view)
    child.setParentItem(parent)
    assert hierarchy.top_most([child, parent, other]) == [parent, other]


def test_scene_delta_to_parent_with_scaled_parent(view):
    parent = make_image(view)
    parent.setScale(2)
    child = make_image(view)
    child.setParentItem(parent)
    delta = hierarchy.scene_delta_to_parent(child, QtCore.QPointF(10, 4))
    assert delta == QtCore.QPointF(5, 2)


def test_items_in_order_parents_before_children(view):
    a = make_image(view, name='a.png')
    b = make_image(view, name='b.png')
    c = make_image(view, name='c.png')
    c.setParentItem(a)
    assert items_in_order([b, c, a]) == [a, c, b]


def test_items_in_order_uses_sort_order_within_siblings(view):
    a = make_image(view, name='a.png')
    b = make_image(view, name='b.png')
    a.sort_order = 2
    b.sort_order = 1
    assert items_in_order([a, b]) == [b, a]


# Groups

def test_group_selection_creates_group(view):
    a = make_image(view, 0, 0)
    b = make_image(view, 200, 100)
    before = [a.corners_scene_coords, b.corners_scene_coords]
    group = make_group(view, [a, b])
    assert a.parentItem() is group
    assert b.parentItem() is group
    assert group.isSelected()
    assert not a.isSelected()
    for corners, item in zip(before, [a, b]):
        for p1, p2 in zip(corners, item.corners_scene_coords):
            assert_points_equal(p1, p2)
    rect = view.scene.itemsBoundingRect(items=[group])
    pad = BeeGroupItem.PADDING
    assert rect == QtCore.QRectF(-pad, -pad, 300 + 2 * pad, 180 + 2 * pad)


def test_group_children_not_selectable_while_closed(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    flags = QtWidgets.QGraphicsItem.GraphicsItemFlag
    assert not a.flags() & flags.ItemIsSelectable
    group.set_open(True)
    assert a.flags() & flags.ItemIsSelectable
    group.set_open(False)
    assert not a.flags() & flags.ItemIsSelectable


def test_group_undo_redo(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    view.undo_stack.undo()
    assert a.parentItem() is None
    assert b.parentItem() is None
    assert group.scene() is None
    assert a.pos() == QtCore.QPointF(0, 0)
    assert b.pos() == QtCore.QPointF(200, 0)
    assert a.isSelected() and b.isSelected()
    view.undo_stack.redo()
    assert a.parentItem() is group
    assert group.scene() is view.scene


def test_group_only_items_with_same_parent(view):
    parent = make_image(view)
    child = make_image(view, 10)
    child.setParentItem(parent)
    other = make_image(view, 300)
    view.undo_stack.push(commands.GroupItems(
        view.scene, [parent, other], BeeGroupItem()))
    assert parent.parentItem() is not None
    assert child.parentItem() is parent


def test_ungroup_selection(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    view.scene.ungroup_selection()
    assert a.parentItem() is None
    assert group.scene() is None
    assert a.isSelected() and b.isSelected()
    assert b.pos() == QtCore.QPointF(200, 0)
    view.undo_stack.undo()
    assert a.parentItem() is group
    assert group.scene() is view.scene


def test_group_fits_children_after_move(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    b.moveBy(100, 0)
    view.scene.fit_groups()
    assert group.bounding_rect_unselected().width() == pytest.approx(
        400 + 2 * BeeGroupItem.PADDING)


def test_delete_child_restores_parent_on_undo(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    group.set_open(True)
    view.undo_stack.push(commands.DeleteItems(view.scene, [b]))
    assert b.scene() is None
    view.undo_stack.undo()
    assert b.parentItem() is group
    assert b.pos() + group.pos() == QtCore.QPointF(200, 0)


def test_delete_last_children_deletes_group(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    view.undo_stack.push(commands.DeleteItems(view.scene, [a, b]))
    assert group.scene() is None
    view.undo_stack.undo()
    assert group.scene() is view.scene
    assert a.parentItem() is group


def test_delete_parent_and_child_only_removes_parent(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    cmd = commands.DeleteItems(view.scene, [a, group])
    assert cmd.items == [group]


def test_click_on_child_of_closed_group_returns_group(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    assert view.scene.interactive_item_at(QtCore.QPointF(50, 40)) is group


def test_double_click_enters_group(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    view.scene.mouseDoubleClickEvent(mouse_event((250, 40)))
    assert group.is_open
    assert b.isSelected()
    assert not group.isSelected()


def test_group_closes_when_selecting_outside(view):
    a = make_image(view)
    b = make_image(view, 200)
    other = make_image(view, 1000)
    group = make_group(view, [a, b])
    view.scene.select_items([a])
    assert group.is_open
    view.scene.select_items([other])
    assert not group.is_open


def test_nested_groups(view):
    a = make_image(view)
    b = make_image(view, 200)
    c = make_image(view, 500)
    inner = make_group(view, [a, b])
    view.scene.clearSelection()
    inner.setSelected(True)
    c.setSelected(True)
    view.scene.group_selection()
    outer = inner.parentItem()
    assert isinstance(outer, BeeGroupItem)
    assert view.scene.interactive_item_at(QtCore.QPointF(50, 40)) is outer
    view.scene.select_items([a])
    assert outer.is_open and inner.is_open
    assert a.isSelected()


def test_copy_with_children(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    group.name = 'My group'
    group.color = '#ff00ff00'
    copy = group.copy_with_children()
    assert copy is not group
    assert copy.name == 'My group'
    assert copy.color == '#ff00ff00'
    children = hierarchy.user_children(copy)
    assert len(children) == 2
    assert {c.pos().x() for c in children} == {
        a.pos().x(), b.pos().x()}


def test_paste_group_copies_children(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    view.scene.copy_selection_to_internal_clipboard()
    view.scene.paste_from_internal_clipboard(QtCore.QPointF(1000, 1000))
    groups = list(view.scene.items_by_type('group'))
    assert len(groups) == 2
    new = [g for g in groups if g is not group][0]
    assert len(hierarchy.user_children(new)) == 2


def test_change_group_color_undo(view):
    a = make_image(view)
    group = make_group(view, [a])
    view.undo_stack.push(commands.ChangeGroupColor([group], '#80ff0000'))
    assert group.background_color() == QtGui.QColor('#80ff0000')
    view.undo_stack.undo()
    assert group.color is None


# Parenting

def test_parent_selection_uses_first_selected(view):
    a = make_image(view)
    b = make_image(view, 200)
    c = make_image(view, 400)
    b.setSelected(True)
    a.setSelected(True)
    c.setSelected(True)
    view.scene.parent_selection()
    assert a.parentItem() is b
    assert c.parentItem() is b
    assert a.scenePos() == QtCore.QPointF(0, 0)
    view.undo_stack.undo()
    assert a.parentItem() is None


def test_unparent_selection(view):
    a = make_image(view)
    b = make_image(view, 200)
    a.setParentItem(b)
    a.setPos(-200, 0)
    a.setSelected(True)
    view.scene.unparent_selection()
    assert a.parentItem() is None
    assert a.pos() == QtCore.QPointF(0, 0)


def test_move_in_hierarchy_sets_sort_order(view):
    a = make_image(view, name='a.png')
    b = make_image(view, name='b.png')
    c = make_image(view, name='c.png')
    view.scene.move_in_hierarchy([c], None, 0)
    assert view.scene.ordered_children(None) == [c, a, b]
    view.undo_stack.undo()
    assert view.scene.ordered_children(None) == [a, b, c]


def test_move_in_hierarchy_refuses_own_descendant(view):
    a = make_image(view)
    b = make_image(view)
    b.setParentItem(a)
    count = view.undo_stack.count()
    view.scene.move_in_hierarchy([a], b)
    assert view.undo_stack.count() == count
    assert a.parentItem() is None


def test_moving_child_of_scaled_parent(view):
    parent = make_image(view)
    parent.setScale(2)
    child = make_image(view)
    child.setParentItem(parent)
    child.setPos(10, 0)
    cmd = commands.MoveItemsBy([child], QtCore.QPointF(20, 0))
    cmd.redo()
    assert child.scenePos() == QtCore.QPointF(40, 0)
    cmd.undo()
    assert child.scenePos() == QtCore.QPointF(20, 0)


def test_arrange_child_uses_scene_coords(view):
    parent = make_image(view, 100, 100)
    child = make_image(view)
    child.setParentItem(parent)
    cmd = commands.ArrangeItems(view.scene, [child], [QtCore.QPointF(0, 0)])
    cmd.redo()
    assert child.scenePos() == QtCore.QPointF(0, 0)


def test_scale_child_with_anchor_in_rotated_parent(view):
    parent = make_image(view, 100, 100)
    parent.setRotation(90)
    child = make_image(view)
    child.setParentItem(parent)
    anchor = child.mapToScene(child.center)
    child.setScale(2, child.center)
    assert_points_equal(child.mapToScene(child.center), anchor)


# Dragging into groups

def drag_item(view, item, start, end):
    view.scene.select_items([item])
    with patch('PyQt6.QtWidgets.QGraphicsScene.mousePressEvent'):
        with patch.object(view.scene, 'itemAt', return_value=item):
            view.scene.mousePressEvent(mouse_event(start))
    item.moveBy(end[0] - start[0], end[1] - start[1])
    with patch('PyQt6.QtWidgets.QGraphicsScene.mouseReleaseEvent'):
        view.scene.mouseReleaseEvent(mouse_event(end))


def test_drag_item_into_group(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    c = make_image(view, 1000, 0)
    drag_item(view, c, (1010, 10), (160, 10))
    assert c.parentItem() is group
    view.undo_stack.undo()
    assert c.parentItem() is None
    assert c.pos() == QtCore.QPointF(1000, 0)


def test_drag_item_out_of_group(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    group.set_open(True)
    drag_item(view, b, (210, 10), (1010, 10))
    assert b.parentItem() is None
    assert b.scenePos() == QtCore.QPointF(1000, 0)
    assert a.parentItem() is group


def test_drag_into_groups_disabled(view, settings):
    settings.setValue('Items/drag_into_groups', False)
    a = make_image(view)
    group = make_group(view, [a])
    c = make_image(view, 1000, 0)
    drag_item(view, c, (1010, 10), (10, 10))
    assert c.parentItem() is None
    assert group.scene()


# Locking

def test_lock_selected_and_unlock_all(view):
    a = make_image(view, selected=True)
    b = make_image(view, 200)
    actions['lock_selected'].qaction.trigger()
    assert a.locked
    assert not a.isSelected()
    flags = QtWidgets.QGraphicsItem.GraphicsItemFlag
    assert not a.flags() & flags.ItemIsSelectable
    assert view.scene.interactive_item_at(QtCore.QPointF(10, 10)) is None
    view.on_action_unlock_all()
    assert not a.locked
    assert a.flags() & flags.ItemIsSelectable
    assert not b.locked


def test_global_lock_keeps_item_lock(view):
    a = make_image(view)
    a.set_item_locked(True)
    view.scene.set_items_locked(True)
    view.scene.set_items_locked(False)
    assert a.locked
    flags = QtWidgets.QGraphicsItem.GraphicsItemFlag
    assert not a.flags() & flags.ItemIsSelectable


# Comments and names

def test_change_comment_sets_tooltip(view):
    a = make_image(view)
    view.undo_stack.push(commands.ChangeComment([a], '<b>Hello</b>'))
    assert a.comment == '<b>Hello</b>'
    assert a.toolTip() == 'Hello'
    view.undo_stack.undo()
    assert a.comment == ''
    assert a.toolTip() == ''


def test_edit_comment_dialog(view):
    a = make_image(view, selected=True)
    with patch.object(CommentDialog, 'exec', return_value=True):
        with patch.object(CommentDialog, 'comment', return_value='<p>x</p>'):
            actions['edit_comment'].qaction.trigger()
    assert a.comment == '<p>x</p>'


def test_comment_dialog_empty_text(qapp):
    dialog = CommentDialog(None, '<p>foo</p>')
    assert 'foo' in dialog.comment()
    dialog.editor.setPlainText('   ')
    assert dialog.comment() == ''


def test_rename_item(view):
    a = make_image(view, name='/foo/bar.png', selected=True)
    assert a.display_name() == 'bar.png'
    with patch('PyQt6.QtWidgets.QInputDialog.getText',
               return_value=(' Ref ', True)):
        actions['rename_item'].qaction.trigger()
    assert a.name == 'Ref'
    assert a.display_name() == 'Ref'
    view.undo_stack.undo()
    assert a.name == ''


def test_default_names(view):
    assert BeeTextItem('foo\nbar').default_name() == 'foo'
    assert BeeGroupItem().default_name() == 'Group'
    assert make_image(view).default_name() == 'Image'


# Saving and loading

def test_save_and_load_groups(view, tmpfile):
    a = make_image(view, 0, 0)
    b = make_image(view, 200, 100)
    group = make_group(view, [a, b])
    group.name = 'Refs'
    group.color = '#8000ff00'
    a.set_item_locked(True)
    a.set_comment('<p>note</p>')
    view.scene.clearSelection()
    corners = [a.corners_scene_coords, b.corners_scene_coords]
    SQLiteIO(tmpfile, view.scene, create_new=True).write()

    view.scene.clear()
    io = SQLiteIO(tmpfile, view.scene, readonly=True)
    io.read()
    view.scene.add_queued_items()
    groups = list(view.scene.items_by_type('group'))
    assert len(groups) == 1
    loaded = groups[0]
    assert loaded.name == 'Refs'
    assert loaded.color == '#8000ff00'
    children = sorted(hierarchy.user_children(loaded),
                      key=lambda i: i.scenePos().x())
    assert len(children) == 2
    assert children[0].locked
    assert children[0].comment == '<p>note</p>'
    for old, item in zip(corners, children):
        for p1, p2 in zip(old, item.corners_scene_coords):
            assert_points_equal(p1, p2)
    flags = QtWidgets.QGraphicsItem.GraphicsItemFlag
    assert not children[1].flags() & flags.ItemIsSelectable
    assert loaded.bounding_rect_unselected().width() > 0


# Export

def test_svg_export_uses_scene_positions_of_children(view):
    parent = BeeTextItem('parent')
    parent.setPos(100, 100)
    view.scene.addItem(parent)
    child = make_image(view)
    child.setParentItem(parent)
    child.setPos(10, 20)
    exporter = SceneToSVGExporter(view.scene)
    exporter.size = QtCore.QSize(500, 500)
    exporter.margin = 0
    svg = exporter.render_to_svg()
    images = [e for e in svg if e.tag == 'image']
    offset = exporter.items_rect.topLeft()
    assert float(images[0].get('x')) == 110 - offset.x()
    assert float(images[0].get('y')) == 120 - offset.y()


def test_export_selection_includes_children(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    other = make_image(view, 1000)
    exporter = SceneToSVGExporter(view.scene, items=[group])
    assert set(exporter.items) == {group, a, b}
    hidden = SceneToPixmapExporter(view.scene, items=[group])\
        .hide_other_items()
    assert hidden == [other]
    other.setVisible(True)


# Hierarchy panel

def test_show_hierarchy_creates_dock(view):
    actions['show_hierarchy'].qaction.setChecked(True)
    assert view.hierarchy_dock is not None
    assert view.hierarchy_dock.isVisibleTo(view.parent)
    actions['show_hierarchy'].qaction.setChecked(False)
    assert not view.hierarchy_dock.isVisibleTo(view.parent)


def test_hierarchy_tree_shows_structure(view):
    a = make_image(view, name='a.png')
    b = make_image(view, 200, name='b.png')
    group = make_group(view, [a, b])
    group.name = 'G'
    c = make_image(view, 500, name='c.png')
    c.set_item_locked(True)
    tree = HierarchyTree(view)
    tree.refresh(force=True)
    assert tree.topLevelItemCount() == 2
    top = [tree.topLevelItem(i) for i in range(2)]
    texts = {t.text(0) for t in top}
    assert texts == {'G', 'c.png'}
    g_item = [t for t in top if t.text(0) == 'G'][0]
    assert {g_item.child(i).text(0) for i in range(2)} == {
        'a.png', 'b.png'}
    c_item = [t for t in top if t.text(0) == 'c.png'][0]
    assert c_item.text(HierarchyTree.COL_LOCK)


def test_hierarchy_tree_selection_selects_in_scene(view):
    a = make_image(view, name='a.png')
    b = make_image(view, 200, name='b.png')
    group = make_group(view, [a, b])
    view.scene.clearSelection()
    tree = HierarchyTree(view)
    tree.refresh(force=True)
    child = tree.topLevelItem(0).child(0)
    child.setSelected(True)
    assert tree.scene_item(child).isSelected()
    assert group.is_open


def test_hierarchy_tree_rename(view):
    a = make_image(view, name='a.png')
    tree = HierarchyTree(view)
    tree.refresh(force=True)
    tree.topLevelItem(0).setText(0, 'New')
    assert a.name == 'New'


def test_hierarchy_tree_lock_column(view):
    a = make_image(view)
    tree = HierarchyTree(view)
    tree.refresh(force=True)
    tree.on_item_clicked(tree.topLevelItem(0), HierarchyTree.COL_LOCK)
    assert a.locked


def test_hierarchy_tree_drop_onto_item(view):
    a = make_image(view, name='a.png')
    b = make_image(view, 200, name='b.png')
    tree = HierarchyTree(view)
    tree.refresh(force=True)
    items = {tree.topLevelItem(i).text(0): tree.topLevelItem(i)
             for i in range(2)}
    items['b.png'].setSelected(True)
    rect = tree.visualItemRect(items['a.png'])
    event = MagicMock()
    event.position.return_value = QtCore.QPointF(rect.center())
    Indicator = QtWidgets.QAbstractItemView.DropIndicatorPosition
    with patch.object(tree, 'dropIndicatorPosition',
                      return_value=Indicator.OnItem):
        tree.dropEvent(event)
    assert b.parentItem() is a
    assert b.scenePos() == QtCore.QPointF(200, 0)
