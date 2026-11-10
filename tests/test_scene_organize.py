"""Tests for the organizing actions added for PureRef parity (phase 1):
align, distribute, stack, normalize variants, arrange orders and
duplicate, as well as the "all items when nothing is selected" rule.
"""

from unittest.mock import patch

from pytest import approx
import pytest

from PyQt6 import QtCore, QtGui

from myRef import commands
from myRef.items import BeePixmapItem, BeeTextItem, sort_by_addition


def make_item(view, x, y, width, height, selected=True, **kwargs):
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
    item = BeePixmapItem(img, **kwargs)
    view.scene.addItem(item)
    item.setPos(x, y)
    item.setSelected(selected)
    return item


def rect(view, item):
    return view.scene.itemsBoundingRect(items=[item])


# items_for_action

def test_items_for_action_returns_selection(view):
    item1 = make_item(view, 0, 0, 10, 10, selected=True)
    make_item(view, 0, 0, 10, 10, selected=False)
    assert view.scene.items_for_action() == [item1]


def test_items_for_action_returns_all_when_no_selection(view):
    item1 = make_item(view, 0, 0, 10, 10, selected=False)
    item2 = make_item(view, 0, 0, 10, 10, selected=False)
    assert set(view.scene.items_for_action()) == {item1, item2}


def test_items_for_action_ignores_child_items(view):
    parent = make_item(view, 0, 0, 10, 10, selected=False)
    child = make_item(view, 0, 0, 10, 10, selected=False)
    child.setParentItem(parent)
    assert view.scene.items_for_action() == [parent]


def test_arrange_without_selection_arranges_all(view):
    item1 = make_item(view, 0, 0, 100, 100, selected=False)
    item2 = make_item(view, 0, 0, 100, 100, selected=False)
    view.scene.align('left')  # No-op, all at x=0
    view.scene.arrange()
    assert rect(view, item1).left() != rect(view, item2).left()


# Align

@pytest.mark.parametrize('edge,expected1,expected2',
                         [('left', (10, 0), (10, 300)),
                          ('right', (150, 0), (100, 300)),
                          ('top', (10, 0), (100, 0)),
                          ('bottom', (10, 250), (100, 300))])
def test_align(view, edge, expected1, expected2):
    item1 = make_item(view, 10, 0, 100, 100)
    item2 = make_item(view, 100, 300, 150, 50)
    view.scene.align(edge)
    assert rect(view, item1).topLeft() == QtCore.QPointF(*expected1)
    assert rect(view, item2).topLeft() == QtCore.QPointF(*expected2)


def test_align_is_undoable(view):
    item1 = make_item(view, 10, 0, 100, 100)
    item2 = make_item(view, 100, 300, 150, 50)
    view.scene.align('left')
    view.undo_stack.undo()
    assert item1.pos() == QtCore.QPointF(10, 0)
    assert item2.pos() == QtCore.QPointF(100, 300)


def test_align_needs_two_items(view):
    item = make_item(view, 10, 0, 100, 100)
    view.scene.align('right')
    assert item.pos() == QtCore.QPointF(10, 0)
    assert view.undo_stack.count() == 0


def test_align_unknown_edge(view):
    make_item(view, 10, 0, 100, 100)
    make_item(view, 100, 300, 150, 50)
    with pytest.raises(ValueError):
        view.scene.align('middle')


def test_align_with_rotated_item(view):
    make_item(view, 0, 0, 100, 50)
    item2 = make_item(view, 300, 300, 100, 50)
    item2.setRotation(90)
    view.scene.align('left')
    assert rect(view, item2).left() == approx(0)
    assert rect(view, item2).width() == approx(50)


# Distribute

def test_distribute_horizontal(view):
    item1 = make_item(view, 0, 0, 100, 100)
    item2 = make_item(view, 120, 50, 50, 100)
    item3 = make_item(view, 400, 20, 100, 100)
    view.scene.distribute()
    # Span 0-500, total width 250 => spacing 125
    assert rect(view, item1).topLeft() == QtCore.QPointF(0, 0)
    assert rect(view, item2).topLeft() == QtCore.QPointF(225, 50)
    assert rect(view, item3).topLeft() == QtCore.QPointF(400, 20)


def test_distribute_vertical(view):
    item1 = make_item(view, 0, 0, 100, 100)
    item2 = make_item(view, 20, 110, 100, 10)
    item3 = make_item(view, 30, 300, 100, 100)
    view.scene.distribute(vertical=True)
    # Span 0-400, total height 210 => spacing 95
    assert rect(view, item1).top() == 0
    assert rect(view, item2).topLeft() == QtCore.QPointF(20, 195)
    assert rect(view, item3).top() == 300


def test_distribute_needs_three_items(view):
    make_item(view, 0, 0, 100, 100)
    make_item(view, 500, 0, 100, 100)
    view.scene.distribute()
    assert view.undo_stack.count() == 0


# Stack

def test_stack_centers_items(view):
    item1 = make_item(view, 0, 0, 100, 100)
    item2 = make_item(view, 300, 100, 50, 50)
    view.scene.stack()
    # Common bounding rect: 0,0 - 350,150 => center 175,75
    assert rect(view, item1).center() == QtCore.QPointF(175, 75)
    assert rect(view, item2).center() == QtCore.QPointF(175, 75)


def test_stack_keeps_z_order(view):
    item1 = make_item(view, 0, 0, 100, 100)
    item1.setZValue(5)
    item2 = make_item(view, 300, 100, 50, 50)
    item2.setZValue(1)
    view.scene.stack()
    assert item1.zValue() == 5
    assert item2.zValue() == 1


# Normalize

def test_normalize_longest_side(view):
    item1 = make_item(view, 0, 0, 100, 50)
    item2 = make_item(view, 0, 0, 20, 300)
    view.scene.normalize_longest_side()
    # Average longest side: 200
    assert max(rect(view, item1).width(), rect(view, item1).height()) \
        == approx(200)
    assert max(rect(view, item2).width(), rect(view, item2).height()) \
        == approx(200)


def test_normalize_scale(view):
    item1 = BeeTextItem('foo')
    view.scene.addItem(item1)
    item1.setScale(1)
    item1.setSelected(True)
    item2 = BeeTextItem('bar')
    view.scene.addItem(item2)
    item2.setScale(3)
    item2.setSelected(True)
    view.scene.normalize_scale()
    assert item1.scale() == approx(2)
    assert item2.scale() == approx(2)


def test_normalize_from_first_item(view, settings):
    settings.setValue('Items/normalize_source', 'first')
    item1 = make_item(view, 0, 0, 100, 100, filename='a.png')
    item2 = make_item(view, 0, 0, 100, 300, filename='b.png')
    view.scene.normalize_height()
    assert rect(view, item1).height() == approx(100)
    assert rect(view, item2).height() == approx(100)


def test_normalize_from_average(view, settings):
    item1 = make_item(view, 0, 0, 100, 100, filename='a.png')
    item2 = make_item(view, 0, 0, 100, 300, filename='b.png')
    view.scene.normalize_height()
    assert rect(view, item1).height() == approx(200)
    assert rect(view, item2).height() == approx(200)


def test_normalize_without_selection_affects_all(view):
    item1 = make_item(view, 0, 0, 100, 100, selected=False)
    item2 = make_item(view, 0, 0, 100, 300, selected=False)
    view.scene.normalize_width_or_height('height')
    assert rect(view, item1).height() == approx(200)
    assert rect(view, item2).height() == approx(200)


# Arrange orders

def test_sort_by_addition():
    class Item:
        def __init__(self, added_at, save_id):
            self.added_at = added_at
            self.save_id = save_id

    old2 = Item(None, 2)
    old1 = Item(None, 1)
    new2 = Item(200, None)
    new1 = Item(100, 7)
    assert sort_by_addition([new2, old2, new1, old1]) == [
        old1, old2, new1, new2]


def test_arrange_square_by_addition(view):
    item1 = make_item(view, 0, 0, 100, 100)
    item1.added_at = 2
    item2 = make_item(view, 0, 0, 100, 100)
    item2.added_at = 1
    with patch('myRef.scene.commands.ArrangeItems',
               wraps=commands.ArrangeItems) as arrange_mock:
        view.scene.arrange_square(order='addition')
        items = arrange_mock.call_args.args[1]
    assert items == [item2, item1]


def test_arrange_square_random_shuffles(view):
    items = [make_item(view, 0, 0, 100, 100) for i in range(3)]
    with patch('myRef.scene.random.sample',
               return_value=list(reversed(items))) as sample_mock:
        with patch('myRef.scene.commands.ArrangeItems',
                   wraps=commands.ArrangeItems) as arrange_mock:
            view.scene.arrange_square(order='random')
    sample_mock.assert_called_once()
    assert arrange_mock.call_args.args[1] == list(reversed(items))


def test_insert_items_sets_added_at(view):
    item = BeeTextItem('foo')
    with patch('myRef.commands.time.time', return_value=1234.5):
        view.undo_stack.push(commands.InsertItems(view.scene, [item]))
    assert item.added_at == 1234.5


def test_insert_items_keeps_existing_added_at(view):
    item = BeeTextItem('foo')
    item.added_at = 10
    view.undo_stack.push(commands.InsertItems(view.scene, [item]))
    assert item.added_at == 10


def test_added_at_is_saved_and_loaded(view, tmpfile):
    from myRef.fileio.sql import SQLiteIO
    item = BeeTextItem('foo')
    item.added_at = 1234.5
    view.scene.addItem(item)
    io = SQLiteIO(tmpfile, view.scene, create_new=True)
    io.write()
    del io
    view.scene.clear()

    io = SQLiteIO(tmpfile, view.scene, readonly=True)
    io.read()
    view.scene.add_queued_items()
    assert view.scene.items()[0].added_at == 1234.5


# Duplicate

def test_duplicate_selection(view):
    item = make_item(view, 10, 20, 100, 100)
    item.setScale(2)
    view.scene.duplicate_selection(QtCore.QPointF(5, 5))
    items = view.scene.user_items()
    assert len(items) == 2
    copy = [i for i in items if i is not item][0]
    assert copy.scale() == 2
    assert copy.pos() == QtCore.QPointF(15, 25)
    assert copy.isSelected() is True
    assert item.isSelected() is False


def test_duplicate_selection_is_undoable(view):
    make_item(view, 10, 20, 100, 100)
    view.scene.duplicate_selection(QtCore.QPointF(5, 5))
    view.undo_stack.undo()
    assert len(view.scene.user_items()) == 1


def test_duplicate_without_selection_does_nothing(view):
    make_item(view, 10, 20, 100, 100, selected=False)
    view.scene.duplicate_selection(QtCore.QPointF(5, 5))
    assert len(view.scene.user_items()) == 1
    assert view.undo_stack.count() == 0


def test_view_duplicate_offset_independent_of_zoom(view):
    make_item(view, 0, 0, 100, 100)
    view.scale(2, 2)
    with patch.object(view.scene, 'duplicate_selection') as dup_mock:
        view.on_action_duplicate()
    dup_mock.assert_called_once_with(QtCore.QPointF(10, 10))


# Zoom

def test_zoom_in_and_out(view):
    make_item(view, 0, 0, 100, 100)
    view.on_action_zoom_in()
    assert view.get_scale() == approx(1.25)
    view.on_action_zoom_out()
    assert view.get_scale() == approx(1)


def test_zoom_actual_resets_scale(view):
    make_item(view, 0, 0, 100, 100)
    view.scale(3, 3)
    view.on_action_zoom_actual()
    assert view.get_scale() == 1


def test_center_origin(view):
    make_item(view, -500, -500, 1000, 1000)
    view.scale(2, 2)
    view.on_action_center_origin()
    center = view.mapToScene(view.viewport().rect().center())
    assert center.x() == approx(0, abs=1)
    assert center.y() == approx(0, abs=1)
