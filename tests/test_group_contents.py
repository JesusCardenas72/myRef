"""Tests for organizing the contents of groups (Group menu)."""

from unittest.mock import patch

import pytest

from PyQt6 import QtCore

from myRef.actions.actions import SCOPED_ACTIONS, actions, scoped_id
from myRef.actions.menu_structure import menu_structure
from myRef.widgets.controls.keyboard import KeyboardShortcutsModel

from .test_groups import make_group, make_image


def setup_group(view):
    """A group with three images in a diagonal, plus an image outside."""

    a = make_image(view, 0, 0)
    b = make_image(view, 150, 100, w=50, h=50)
    c = make_image(view, 300, 250, w=80, h=120)
    outside = make_image(view, 1000, 1000)
    group = make_group(view, [a, b, c])
    return group, [a, b, c], outside


def scene_rect(view, item):
    return view.scene.itemsBoundingRect(items=[item])


@pytest.mark.parametrize('action_id', [a[0] for a in SCOPED_ACTIONS])
def test_scoped_action_exists(view, action_id):
    action = actions[scoped_id(action_id)]
    assert action.text == actions[action_id].text
    assert action.group == 'active_when_group'
    assert callable(getattr(view, action.callback))
    assert action.menu_path[0] == 'G&roup'


def test_scoped_actions_in_group_submenus():
    group_menu = [m for m in menu_structure if m['menu'] == 'G&roup'][0]
    in_menus = []
    for item in group_menu['items']:
        if isinstance(item, dict):
            in_menus.extend(item['items'])
    for action_id, _, _ in SCOPED_ACTIONS:
        assert scoped_id(action_id) in in_menus


def test_shortcut_table_tells_scoped_actions_apart(view):
    model = KeyboardShortcutsModel()
    keys = list(actions.keys())
    role = QtCore.Qt.ItemDataRole.DisplayRole
    glob = model.data(model.index(keys.index('align_left'), 0), role)
    scoped = model.data(
        model.index(keys.index('group_align_left'), 0), role)
    assert glob != scoped


@pytest.mark.parametrize('action_id', [a[0] for a in SCOPED_ACTIONS])
def test_scoped_action_leaves_outside_alone(view, action_id):
    group, children, outside = setup_group(view)
    outside_rect = scene_rect(view, outside)
    getattr(view, actions[scoped_id(action_id)].callback)()
    view.scene.fit_groups()
    assert scene_rect(view, outside) == outside_rect
    for child in children:
        assert child.parentItem() is group
    group_rect = scene_rect(view, group)
    for child in children:
        assert group_rect.contains(scene_rect(view, child))


def test_group_align_left(view):
    group, (a, b, c), outside = setup_group(view)
    view.on_action_group_align_left()
    for child in (a, b, c):
        assert scene_rect(view, child).left() == pytest.approx(0)
    view.undo_stack.undo()
    assert scene_rect(view, c).left() == pytest.approx(300)


def test_group_align_works_with_child_selected(view):
    group, (a, b, c), outside = setup_group(view)
    view.scene.select_items([b])
    view.on_action_group_align_top()
    for child in (a, b, c):
        assert scene_rect(view, child).top() == pytest.approx(0)
    assert scene_rect(view, outside).top() == pytest.approx(1000)


def test_group_arrange_horizontal_is_one_undo_step(view):
    group, (a, b, c), outside = setup_group(view)
    count = view.undo_stack.count()
    positions = [child.pos() for child in (a, b, c)]
    view.on_action_group_arrange_horizontal()
    assert view.undo_stack.count() == count + 1
    tops = {round(scene_rect(view, x).center().y()) for x in (a, b, c)}
    assert len(tops) == 1
    view.undo_stack.undo()
    assert [child.pos() for child in (a, b, c)] == positions


def test_group_arrange_keeps_content_center(view):
    group, children, outside = setup_group(view)
    center = view.scene.items_center(children)
    view.on_action_group_arrange_optimal()
    new_center = view.scene.items_center(children)
    assert new_center.x() == pytest.approx(center.x(), abs=2)
    assert new_center.y() == pytest.approx(center.y(), abs=2)


def test_group_shrinks_after_stack(view):
    group, children, outside = setup_group(view)
    width = scene_rect(view, group).width()
    view.on_action_group_stack()
    assert scene_rect(view, group).width() < width


def test_group_normalize_height(view):
    group, (a, b, c), outside = setup_group(view)
    view.on_action_group_normalize_height()
    heights = {round(scene_rect(view, x).height(), 3) for x in (a, b, c)}
    assert len(heights) == 1
    assert outside.scale() == 1


def test_subgroup_counts_as_one_item(view):
    a = make_image(view, 0, 0)
    b = make_image(view, 150, 0)
    c = make_image(view, 400, 300)
    inner = make_group(view, [a, b])
    view.scene.clearSelection()
    inner.setSelected(True)
    c.setSelected(True)
    view.scene.group_selection()
    outer = inner.parentItem()
    distance = b.scenePos() - a.scenePos()
    view.on_action_group_align_left()
    assert b.scenePos() - a.scenePos() == distance
    assert a.parentItem() is inner
    assert scene_rect(view, inner).left() == pytest.approx(
        scene_rect(view, c).left())
    assert outer.isSelected()


def test_inside_subgroup(view):
    a = make_image(view, 0, 0)
    b = make_image(view, 150, 100)
    c = make_image(view, 400, 300)
    inner = make_group(view, [a, b])
    view.scene.clearSelection()
    inner.setSelected(True)
    c.setSelected(True)
    view.scene.group_selection()
    view.scene.select_items([a])
    view.on_action_group_align_top()
    assert scene_rect(view, a).top() == pytest.approx(
        scene_rect(view, b).top())
    assert scene_rect(view, c).top() == pytest.approx(300)


def test_several_groups_one_undo_step(view):
    a = make_image(view, 0, 0)
    b = make_image(view, 150, 100)
    c = make_image(view, 1000, 0)
    d = make_image(view, 1150, 100)
    g1 = make_group(view, [a, b])
    view.scene.clearSelection()
    c.setSelected(True)
    d.setSelected(True)
    view.scene.group_selection()
    g2 = c.parentItem()
    view.scene.clearSelection()
    g1.setSelected(True)
    g2.setSelected(True)
    count = view.undo_stack.count()
    view.on_action_group_align_top()
    assert view.undo_stack.count() == count + 1
    assert scene_rect(view, b).top() == pytest.approx(0)
    assert scene_rect(view, d).top() == pytest.approx(0)


def test_without_group_does_nothing(view):
    make_image(view, selected=True)
    count = view.undo_stack.count()
    view.on_action_group_align_left()
    assert view.undo_stack.count() == count


def test_too_few_items_adds_no_undo_step(view):
    a = make_image(view)
    make_group(view, [a])
    count = view.undo_stack.count()
    view.on_action_group_distribute_horizontal()
    assert view.undo_stack.count() == count


def test_group_focus(view):
    group, children, outside = setup_group(view)
    with patch.object(view, 'fit_rect') as fit_rect:
        view.on_action_group_focus()
        fit_rect.assert_called_once_with(
            view.scene.itemsBoundingRect(items=[group]))


def test_global_actions_unchanged_with_group_selected(view):
    group, (a, b, c), outside = setup_group(view)
    view.scene.clearSelection()
    group.setSelected(True)
    outside.setSelected(True)
    view.on_action_align_left()
    assert scene_rect(view, outside).left() == pytest.approx(
        scene_rect(view, group).left())
    # The children moved along with their group
    assert scene_rect(view, b).left() > scene_rect(view, a).left()
