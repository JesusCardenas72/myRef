"""Tests for the Group menu, its actions and the group style dialog."""

from unittest.mock import patch

import pytest

from PyQt6 import QtCore, QtGui

from myRef import group_style
from myRef.actions.actions import actions
from myRef.actions.menu_structure import menu_structure
from myRef.widgets import ChangeOpacityDialog
from myRef.widgets.groups import GroupStyleDialog

from .test_groups import (
    assert_points_equal,
    make_group,
    make_image,
    mouse_event,
)


def make_nested(view):
    """Group a and b into ``inner``, then inner and c into ``outer``."""

    a = make_image(view)
    b = make_image(view, 200)
    c = make_image(view, 400)
    inner = make_group(view, [a, b])
    view.scene.clearSelection()
    inner.setSelected(True)
    c.setSelected(True)
    view.scene.group_selection()
    return a, b, c, inner, inner.parentItem()


def test_group_menu_holds_group_actions():
    menus = {m['menu']: m['items'] for m in menu_structure}
    for action_id in ('group_items', 'ungroup_items', 'group_color',
                      'add_to_group', 'remove_from_group', 'group_style'):
        assert action_id in menus['G&roup']
        assert action_id not in menus['Ite&ms']


def test_group_selection_reports_left_out_items(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    c = make_image(view, 500)
    view.scene.select_items([a])
    c.setSelected(True)
    assert group.is_open
    with patch('myRef.widgets.BeeNotification') as notification:
        view.on_action_group_items()
        notification.assert_called_once()


def test_group_selection_without_left_out_items(view):
    a = make_image(view, selected=True)
    make_image(view, 200, selected=True)
    with patch('myRef.widgets.BeeNotification') as notification:
        view.on_action_group_items()
        notification.assert_not_called()
    assert a.parentItem() is not None


def test_target_groups(view):
    a = make_image(view)
    b = make_image(view, 200)
    c = make_image(view, 500)
    assert view.scene.target_groups() == []
    group = make_group(view, [a, b])
    assert view.scene.target_groups() == [group]
    view.scene.select_items([a, b])
    assert view.scene.target_groups() == [group]
    view.scene.select_items([c])
    assert view.scene.target_groups() == []
    assert view.scene.target_group() is None


def test_active_when_group(view):
    a = make_image(view)
    make_image(view, 200, selected=True)
    view.on_selection_changed()
    assert not actions['group_style'].qaction.isEnabled()
    view.scene.clearSelection()
    make_group(view, [a])
    view.on_selection_changed()
    assert actions['group_style'].qaction.isEnabled()


def test_add_to_group(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a])
    corners = b.corners_scene_coords
    view.scene.clearSelection()
    group.setSelected(True)
    b.setSelected(True)
    assert view.scene.add_selection_to_group()
    assert b.parentItem() is group
    for p1, p2 in zip(corners, b.corners_scene_coords):
        assert_points_equal(p1, p2)
    assert group.bounding_rect_unselected().width() > 300
    view.undo_stack.undo()
    assert b.parentItem() is None


def test_add_to_group_needs_exactly_one_group(view):
    a = make_image(view)
    b = make_image(view, 200)
    view.scene.select_items([a, b])
    assert not view.scene.add_selection_to_group()
    with patch('myRef.widgets.BeeNotification') as notification:
        view.on_action_add_to_group()
        notification.assert_called_once()


def test_remove_from_group(view):
    a = make_image(view)
    b = make_image(view, 200)
    c = make_image(view, 400)
    group = make_group(view, [a, b, c])
    view.scene.select_items([c])
    view.scene.remove_selection_from_group()
    assert c.parentItem() is None
    assert a.parentItem() is group
    assert c.pos() == QtCore.QPointF(400, 0)
    order = view.scene.ordered_children(None)
    assert order.index(c) == order.index(group) + 1
    view.undo_stack.undo()
    assert c.parentItem() is group


def test_remove_from_subgroup_goes_to_outer_group(view):
    a, b, c, inner, outer = make_nested(view)
    view.scene.select_items([a])
    view.scene.remove_selection_from_group()
    assert a.parentItem() is outer
    assert b.parentItem() is inner


def test_remove_from_two_groups_is_one_undo_step(view):
    a, b, c, inner, outer = make_nested(view)
    count = view.undo_stack.count()
    view.scene.select_items([a])
    c.setSelected(True)
    view.scene.remove_selection_from_group()
    assert a.parentItem() is outer
    assert c.parentItem() is None
    assert view.undo_stack.count() == count + 1
    view.undo_stack.undo()
    assert a.parentItem() is inner
    assert c.parentItem() is outer


def test_remove_all_children_deletes_group(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    view.scene.select_items([a, b])
    view.scene.remove_selection_from_group()
    assert group.scene() is None
    view.undo_stack.undo()
    assert group.scene() is view.scene
    assert a.parentItem() is group and b.parentItem() is group


def test_enter_and_exit_group(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    view.scene.enter_group()
    assert group.is_open
    assert set(view.scene.selectedItems(user_only=True)) == {a, b}
    view.scene.exit_group()
    assert view.scene.selectedItems(user_only=True) == [group]
    assert not group.is_open


def test_exit_subgroup_selects_subgroup(view):
    a, b, c, inner, outer = make_nested(view)
    view.scene.select_items([a])
    view.scene.exit_group()
    assert view.scene.selectedItems(user_only=True) == [inner]
    assert outer.is_open
    assert not inner.is_open


def test_group_title_action_renames_parent_group(view):
    a = make_image(view)
    group = make_group(view, [a])
    view.scene.select_items([a])
    with patch('PyQt6.QtWidgets.QInputDialog.getText',
               return_value=('Refs', True)):
        view.on_action_group_title()
    assert group.name == 'Refs'
    view.undo_stack.undo()
    assert group.name == ''


def test_double_click_on_title_renames_group(view):
    a = make_image(view)
    group = make_group(view, [a])
    view.scene.clearSelection()
    pos = group.mapToScene(group.title_rect().center())
    with patch.object(view, 'rename_item') as rename:
        view.scene.mouseDoubleClickEvent(mouse_event((pos.x(), pos.y())))
        rename.assert_called_once_with(group)
    assert not group.is_open


def test_double_click_on_child_still_opens_group(view):
    a = make_image(view)
    group = make_group(view, [a])
    with patch.object(view, 'rename_item') as rename:
        view.scene.mouseDoubleClickEvent(mouse_event((50, 40)))
        rename.assert_not_called()
    assert group.is_open


def test_double_click_on_hidden_title_does_not_rename(view):
    a = make_image(view)
    group = make_group(view, [a])
    group.set_style(title_size=0)
    pos = group.mapToScene(QtCore.QPointF(
        group.bounding_rect_unselected().center().x(),
        group.bounding_rect_unselected().top() + 3))
    with patch.object(view, 'rename_item') as rename:
        view.scene.mouseDoubleClickEvent(mouse_event((pos.x(), pos.y())))
        rename.assert_not_called()


def test_group_opacity_dialog(view):
    a = make_image(view)
    group = make_group(view, [a])
    dialog = ChangeOpacityDialog(view, [group], view.undo_stack)
    dialog.input.setValue(40)
    dialog.accept()
    assert group.opacity() == pytest.approx(0.4)
    view.undo_stack.undo()
    assert group.opacity() == 1


def test_group_style_dialog_preview_and_single_undo_step(view):
    a = make_image(view)
    group = make_group(view, [a])
    count = view.undo_stack.count()
    dialog = GroupStyleDialog(view, [group], view.undo_stack, show=False)
    dialog.border_width_input.setValue(9)
    dialog.border_style_input.setCurrentIndex(
        dialog.border_style_input.findData('dot'))
    dialog.border_color_input.set_color(QtGui.QColor('#ff00ff00'))
    dialog.background_input.set_color(QtGui.QColor('#40ff0000'))
    dialog.opacity_input.setValue(50)
    assert group.style['border_width'] == 9  # live preview
    dialog.accept()
    assert view.undo_stack.count() == count + 1
    assert group.style['border_style'] == 'dot'
    assert group.style['border_color'] == '#ff00ff00'
    assert group.color == '#40ff0000'
    assert group.opacity() == pytest.approx(0.5)
    view.undo_stack.undo()
    assert group.style == group_style.default_style()
    assert group.color is None
    assert group.opacity() == 1


def test_group_style_dialog_cancel_restores(view):
    a = make_image(view)
    group = make_group(view, [a])
    count = view.undo_stack.count()
    dialog = GroupStyleDialog(view, [group], view.undo_stack, show=False)
    dialog.title_size_input.setValue(40)
    assert group.style['title_size'] == 40
    dialog.reject()
    assert group.style == group_style.default_style()
    assert view.undo_stack.count() == count


def test_group_style_dialog_without_changes_adds_no_undo_step(view):
    a = make_image(view)
    group = make_group(view, [a])
    count = view.undo_stack.count()
    GroupStyleDialog(view, [group], view.undo_stack, show=False).accept()
    assert view.undo_stack.count() == count


def test_group_style_dialog_only_applies_changed_values(view):
    a = make_image(view)
    b = make_image(view, 300)
    g1 = make_group(view, [a])
    view.scene.clearSelection()
    b.setSelected(True)
    view.scene.group_selection()
    g2 = b.parentItem()
    g2.set_style(border_width=12)
    dialog = GroupStyleDialog(view, [g1, g2], view.undo_stack, show=False)
    dialog.border_style_input.setCurrentIndex(
        dialog.border_style_input.findData('dash'))
    dialog.accept()
    assert g1.style['border_style'] == g2.style['border_style'] == 'dash'
    assert g1.style['border_width'] == 2
    assert g2.style['border_width'] == 12


def test_on_action_group_style_opens_dialog(view):
    a = make_image(view)
    group = make_group(view, [a])
    with patch('myRef.widgets.groups.GroupStyleDialog') as dialog:
        view.on_action_group_style()
        dialog.assert_called_once_with(view, [group], view.undo_stack)
