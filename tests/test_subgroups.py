"""Tests for nested groups (G5)."""

from PyQt6 import QtCore

from myRef import hierarchy
from myRef.items import BeeGroupItem

from .test_groups import drag_item, make_group, make_image


def make_three_levels(view):
    """outer > middle > inner > a, plus b in middle and c in outer.

    Positions: a at 0, b at 300, c at 700 (all at y=0).
    """

    a = make_image(view, 0, 0)
    b = make_image(view, 300, 0)
    c = make_image(view, 700, 0)
    inner = make_group(view, [a])
    view.scene.clearSelection()
    inner.setSelected(True)
    b.setSelected(True)
    view.scene.group_selection()
    middle = inner.parentItem()
    view.scene.clearSelection()
    middle.setSelected(True)
    c.setSelected(True)
    view.scene.group_selection()
    outer = middle.parentItem()
    view.scene.clearSelection()
    return a, b, c, inner, middle, outer


def groups_contain_children(view):
    view.scene.fit_groups()
    for group in view.scene.groups():
        rect = view.scene.itemsBoundingRect(items=[group])
        for child in hierarchy.user_children(group):
            assert rect.contains(view.scene.itemsBoundingRect(
                items=[child])), (group, child)


def test_three_levels(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    assert a.parentItem() is inner
    assert inner.parentItem() is middle
    assert middle.parentItem() is outer
    assert outer.parentItem() is None
    groups_contain_children(view)


def test_create_subgroup_inside_open_group(view):
    a = make_image(view, 0, 0)
    b = make_image(view, 200, 0)
    c = make_image(view, 400, 0)
    group = make_group(view, [a, b, c])
    view.scene.select_items([a, b])
    view.scene.group_selection()
    sub = a.parentItem()
    assert isinstance(sub, BeeGroupItem)
    assert sub.parentItem() is group
    assert c.parentItem() is group
    groups_contain_children(view)


def test_moving_inner_item_grows_all_groups(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    widths = [view.scene.itemsBoundingRect(items=[g]).width()
              for g in (middle, outer)]
    a.moveBy(-500, 0)
    view.scene.fit_groups()
    for group, width in zip((middle, outer), widths):
        assert view.scene.itemsBoundingRect(
            items=[group]).width() > width
    groups_contain_children(view)


def test_select_items_opens_all_levels(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    view.scene.select_items([a])
    assert outer.is_open and middle.is_open and inner.is_open
    assert view.scene.selectedItems(user_only=True) == [a]


def test_close_unused_groups_three_levels(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    view.scene.select_items([a])
    view.scene.select_items([c])
    assert outer.is_open
    assert not middle.is_open
    assert not inner.is_open
    view.scene.clearSelection()
    assert not outer.is_open


def test_click_on_deep_item_selects_outermost_closed_group(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    assert view.scene.effective_item(a) is outer
    view.scene.select_items([c])
    assert view.scene.effective_item(a) is middle


# Dropping

def test_drop_target_is_innermost_open_group(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    new = make_image(view, 2000, 0)
    view.scene.select_items([a])
    view.scene.clearSelection()
    assert inner.is_open is False
    view.scene.open_group(inner)
    target = view.scene.drop_target_group(QtCore.QPointF(10, 10), [new])
    assert target is inner


def test_drop_target_is_outer_group_when_closed(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    new = make_image(view, 2000, 0)
    assert not outer.is_open
    target = view.scene.drop_target_group(QtCore.QPointF(10, 10), [new])
    assert target is outer


def test_drag_new_item_onto_closed_nested_groups(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    new = make_image(view, 2000, 0)
    drag_item(view, new, (2010, 10), (10, 10))
    assert new.parentItem() is outer
    groups_contain_children(view)


def test_drag_item_out_of_subgroup_into_outer_group(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    # From inner (at x=0) to the free area of outer between middle
    # (ends at about x=415) and c (starts at x=700)
    drag_item(view, a, (10, 10), (550, 40))
    assert a.parentItem() is outer
    assert inner.scene() is None  # inner has become empty
    groups_contain_children(view)
    view.undo_stack.undo()
    assert a.parentItem() is inner
    assert inner.scene() is view.scene


def test_drag_item_out_of_all_groups(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    drag_item(view, b, (310, 10), (3000, 3000))
    assert b.parentItem() is None
    assert b.scenePos() == QtCore.QPointF(2990, 2990)
    groups_contain_children(view)


def test_drag_within_own_subgroup_keeps_parent(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    drag_item(view, a, (10, 10), (30, 30))
    assert a.parentItem() is inner


def test_drag_subgroup_into_sibling_group(view):
    a = make_image(view, 0, 0)
    b = make_image(view, 1000, 0)
    g1 = make_group(view, [a])
    view.scene.clearSelection()
    b.setSelected(True)
    view.scene.group_selection()
    g2 = b.parentItem()
    view.scene.clearSelection()
    drag_item(view, g1, (10, 10), (1010, 10))
    assert g1.parentItem() is g2
    assert a.parentItem() is g1


def test_group_not_dropped_into_itself(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    view.scene.open_group(outer)
    target = view.scene.drop_target_group(
        QtCore.QPointF(10, 10), [middle])
    assert target is not middle
    assert target not in hierarchy.descendants(middle)


# Copying

def test_copy_nested_groups_keeps_style(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    inner.set_style(border_shape='wave', border_color='#ff00ff00',
                    opacity=0.5)
    inner.name = 'Inner'
    middle.set_style(border_style='dot', title_size=30)
    copy = outer.copy_with_children()
    copy_middle = [g for g in hierarchy.user_children(copy)
                   if isinstance(g, BeeGroupItem)][0]
    copy_inner = [g for g in hierarchy.user_children(copy_middle)
                  if isinstance(g, BeeGroupItem)][0]
    assert copy_inner.style == inner.style
    assert copy_inner.opacity() == 0.5
    assert copy_inner.name == 'Inner'
    assert copy_middle.style == middle.style
    assert len(hierarchy.descendants(copy)) == len(
        hierarchy.descendants(outer))


def test_duplicate_nested_groups(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    inner.set_style(border_shape='zigzag')
    outer.setSelected(True)
    view.scene.duplicate_selection(QtCore.QPointF(0, 1000))
    groups = view.scene.groups()
    assert len(groups) == 6
    zigzags = [g for g in groups if g.style['border_shape'] == 'zigzag']
    assert len(zigzags) == 2
    groups_contain_children(view)


def test_paste_nested_groups(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    middle.set_style(border_width=9)
    outer.setSelected(True)
    view.scene.copy_selection_to_internal_clipboard()
    view.scene.paste_from_internal_clipboard(QtCore.QPointF(0, 2000))
    widths = sorted(g.style['border_width'] for g in view.scene.groups())
    assert widths.count(9) == 2
    assert len(view.scene.groups()) == 6


def test_ungroup_middle_keeps_inner_group(view):
    a, b, c, inner, middle, outer = make_three_levels(view)
    view.scene.select_items([middle])
    view.scene.ungroup_selection()
    assert middle.scene() is None
    assert inner.parentItem() is outer
    assert b.parentItem() is outer
    assert a.parentItem() is inner
    groups_contain_children(view)
