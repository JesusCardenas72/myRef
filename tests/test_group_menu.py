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


def test_ungroup_on_image_in_group_takes_it_out(view):
    a = make_image(view)
    b = make_image(view, 200)
    group = make_group(view, [a, b])
    view.scene.select_items([a])
    view.scene.ungroup_selection()
    assert a.parentItem() is None
    assert b.parentItem() is group
    view.undo_stack.undo()
    assert a.parentItem() is group


def test_ungroup_on_image_in_subgroup_goes_to_outer_group(view):
    a, b, c, inner, outer = make_nested(view)
    view.scene.select_items([a])
    view.scene.ungroup_selection()
    assert a.parentItem() is outer
    assert b.parentItem() is inner
    assert inner.scene() is view.scene


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


def test_double_click_on_title_edits_title(view):
    a = make_image(view)
    group = make_group(view, [a])
    view.scene.clearSelection()
    pos = group.mapToScene(group.title_text_rect().center())
    with patch.object(view, 'edit_group_title_style') as edit:
        view.scene.mouseDoubleClickEvent(mouse_event((pos.x(), pos.y())))
        edit.assert_called_once_with(group)
    assert not group.is_open


def test_double_click_on_child_still_opens_group(view):
    a = make_image(view)
    group = make_group(view, [a])
    with patch.object(view, 'edit_group_title_style') as rename:
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
    with patch.object(view, 'edit_group_title_style') as rename:
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
    before = dict(group.style)
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
    assert group.style == before
    assert group.color is None
    assert group.opacity() == 1


def test_group_style_dialog_cancel_restores(view):
    a = make_image(view)
    group = make_group(view, [a])
    before = dict(group.style)
    count = view.undo_stack.count()
    dialog = GroupStyleDialog(view, [group], view.undo_stack, show=False)
    dialog.title_size_input.setValue(40)
    assert group.style['title_size'] == 40
    dialog.reject()
    assert group.style == before
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


def test_title_positions_margins_and_geometry(view):
    a = make_image(view)
    group = make_group(view, [a])
    group.set_style(title_size=20, border_width=0)
    th = 20 * group.TITLE_LINE_HEIGHT
    pad = group.PADDING
    for position in group_style.TITLE_POSITIONS:
        group.set_style(title_position=position)
        rect = group.bounding_rect_unselected()
        band = group.title_rect()
        text = group.title_text_rect()
        assert rect.contains(band), position
        assert band.adjusted(-0.01, -0.01, 0.01, 0.01).contains(text)
        child = group.mapRectFromScene(a.sceneBoundingRect())
        assert not band.intersects(child.adjusted(1, 1, -1, -1)), position
        side = group_style.title_side(position)
        left, top, right, bottom = group.margins()
        expected = {'top': top, 'bottom': bottom,
                    'left': left, 'right': right}[side]
        assert expected == pytest.approx(pad + th)


def test_drag_title_to_other_place_with_ghost(view):
    a = make_image(view)
    group = make_group(view, [a])
    view.scene.clearSelection()
    scene = view.scene
    start = group.mapToScene(group.title_text_rect().center())
    rect = group.bounding_rect_unselected()
    target = group.mapToScene(rect.bottomLeft())
    scene.mousePressEvent(mouse_event((start.x(), start.y())))
    assert scene.active_mode == scene.TITLE_MODE
    scene.mouseMoveEvent(mouse_event((target.x(), target.y())))
    assert scene.title_ghost is not None
    assert scene.title_ghost.position == 'bottom_left'
    # Nothing changes until the mouse is released
    assert group.style['title_position'] == 'top_right'
    scene.mouseReleaseEvent(mouse_event((target.x(), target.y())))
    assert scene.title_ghost is None
    assert group.style['title_position'] == 'bottom_left'
    view.undo_stack.undo()
    assert group.style['title_position'] == 'top_right'


def test_drag_title_middle_of_side(view):
    a = make_image(view)
    group = make_group(view, [a])
    rect = group.bounding_rect_unselected()
    assert group.title_position_at(
        QtCore.QPointF(rect.left(), rect.center().y())) == 'middle_left'
    assert group.title_position_at(
        QtCore.QPointF(rect.center().x(), rect.bottom())) == 'bottom_center'


def test_escape_cancels_title_drag(view):
    a = make_image(view)
    group = make_group(view, [a])
    scene = view.scene
    start = group.mapToScene(group.title_text_rect().center())
    target = group.mapToScene(group.bounding_rect_unselected().bottomLeft())
    scene.mousePressEvent(mouse_event((start.x(), start.y())))
    scene.mouseMoveEvent(mouse_event((target.x(), target.y())))
    scene.cancel_active_modes()
    assert scene.title_ghost is None
    assert group.style['title_position'] == 'top_right'


def test_click_on_gear_opens_settings(view):
    a = make_image(view)
    group = make_group(view, [a])
    view.scene.clearSelection()
    pos = group.mapToScene(group.gear_rect().center())
    with patch.object(view, 'edit_group_style') as edit:
        view.scene.mousePressEvent(mouse_event((pos.x(), pos.y())))
        edit.assert_called_once_with([group])
    assert group.isSelected()
    assert view.scene.active_mode is None


def test_title_editor_renames_group(view):
    from myRef.widgets.groups import GroupTitleEditor
    a = make_image(view)
    group = make_group(view, [a])
    view.edit_group_title(group)
    editor = view.title_editor
    assert isinstance(editor, GroupTitleEditor)
    assert group.editing_title
    editor.setText('Refs')
    editor.finish()
    assert group.name == 'Refs'
    assert not group.editing_title
    assert view.title_editor is None
    view.undo_stack.undo()
    assert group.name == ''


def test_title_editor_escape_discards(view):
    a = make_image(view)
    group = make_group(view, [a])
    view.edit_group_title(group)
    view.title_editor.setText('Refs')
    view.title_editor.cancelled = True
    view.title_editor.finish()
    assert group.name == ''


def test_style_dialog_changes_title_position_live(view):
    a = make_image(view)
    group = make_group(view, [a])
    dialog = GroupStyleDialog(view, [group], view.undo_stack, show=False)
    dialog.title_position_input.setCurrentIndex(
        dialog.title_position_input.findData('bottom_center'))
    assert group.style['title_position'] == 'bottom_center'
    dialog.name_input.setText('Mine')
    assert group.name == 'Mine'
    dialog.accept()
    assert group.name == 'Mine'
    view.undo_stack.undo()
    assert group.name == ''
    assert group.style['title_position'] == 'top_right'


def test_style_dialog_reject_restores_name(view):
    a = make_image(view)
    group = make_group(view, [a])
    dialog = GroupStyleDialog(view, [group], view.undo_stack, show=False)
    dialog.name_input.setText('Mine')
    dialog.reject()
    assert group.name == ''


def test_click_on_title_activates_it_with_panel(view):
    a = make_image(view)
    group = make_group(view, [a])
    view.scene.clearSelection()
    scene = view.scene
    pos = group.mapToScene(group.title_text_rect().center())
    scene.mousePressEvent(mouse_event((pos.x(), pos.y())))
    scene.mouseReleaseEvent(mouse_event((pos.x(), pos.y())))
    assert scene.title_active is group
    assert group.title_active
    # No format window yet; double click opens it
    assert view.title_panel is None
    # The first click only selects the title; the next one puts the
    # cursor
    assert view.title_editor is None
    scene.mousePressEvent(mouse_event((pos.x(), pos.y())))
    scene.mouseReleaseEvent(mouse_event((pos.x(), pos.y())))
    assert view.title_editor is not None
    assert group.editing_title
    view.title_editor.setText('Typed')
    assert group.title_text() == 'Typed'
    view.edit_group_title_style(group)
    assert view.title_panel is not None
    assert view.title_editor is not None
    # Deselecting the group deactivates the title
    scene.clearSelection()
    assert scene.title_active is None
    assert view.title_panel is None
    assert view.title_editor is None
    assert group.name == 'Typed'


def test_title_panel_changes_text_undoable(view):
    a = make_image(view)
    group = make_group(view, [a])
    size = group.style['title_size']
    view.edit_group_title_style(group)
    panel = view.title_panel
    panel.bold_input.setChecked(True)
    panel.size_input.setValue(30)
    assert group.style['title_bold'] and group.style['title_size'] == 30
    view.close_title_panel()
    assert group.style['title_bold']
    view.undo_stack.undo()
    assert not group.style['title_bold']
    assert group.style['title_size'] == size


def test_resize_title_with_handle(view):
    a = make_image(view)
    group = make_group(view, [a])
    group.set_style(title_size=14)
    scene = view.scene
    pos = group.mapToScene(group.title_text_rect().center())
    scene.mousePressEvent(mouse_event((pos.x(), pos.y())))
    scene.mouseReleaseEvent(mouse_event((pos.x(), pos.y())))
    handle = group.title_handle_rects()['tl'].center()
    start = group.mapToScene(handle)
    center = group.mapToScene(group.title_text_rect().center())
    far = center + (start - center) * 2
    scene.mousePressEvent(mouse_event((start.x(), start.y())))
    assert scene.active_mode == scene.TITLE_RESIZE_MODE
    scene.mouseMoveEvent(mouse_event((far.x(), far.y())))
    assert group.style['title_size'] == pytest.approx(28, rel=0.05)
    scene.mouseReleaseEvent(mouse_event((far.x(), far.y())))
    assert scene.active_mode is None
    view.undo_stack.undo()
    assert group.style['title_size'] == 14


def test_new_group_title_readable_when_zoomed_out(view):
    view.scale(0.1, 0.1)
    a = make_image(view)
    group = make_group(view, [a])
    assert group.style['title_size'] == group.TITLE_PIXELS * 10


def test_new_group_title_not_smaller_than_default_when_zoomed_in(view):
    view.scale(10, 10)
    a = make_image(view)
    group = make_group(view, [a])
    assert group.style['title_size'] == 14


def test_gear_has_fixed_screen_size(view):
    a = make_image(view, w=5000, h=5000)
    group = make_group(view, [a])
    view.scale(0.1, 0.1)
    assert group.gear_size() == pytest.approx(group.GEAR_PIXELS * 10)
    view.scale(10, 10)
    assert group.gear_size() == pytest.approx(group.GEAR_PIXELS)


def test_title_panel_changes_show_in_editor(view):
    a = make_image(view)
    group = make_group(view, [a])
    view.edit_group_title(group)
    view.edit_group_title_style(group)
    editor = view.title_editor
    old_width = editor.width()
    view.title_panel.size_input.setValue(40)
    view.title_panel.bold_input.setChecked(True)
    assert editor.font().pixelSize() >= 40
    assert editor.font().bold()
    assert editor.width() > old_width
    view.title_panel.color_input.set_color('#ffff0000')
    assert 'ff0000' in editor.styleSheet()
