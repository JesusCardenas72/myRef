from PyQt6 import QtGui

from myRef.items import (
    items_in_order, sort_by_filename, BeePixmapItem, BeeTextItem)


def test_sort_by_filename(view):
    item1 = BeePixmapItem(QtGui.QImage())

    item2 = BeePixmapItem(QtGui.QImage())
    item2.filename = 'foo.png'
    item2.save_id = 66

    item3 = BeePixmapItem(QtGui.QImage())
    item3.save_id = 33

    item4 = BeePixmapItem(QtGui.QImage())
    item4.filename = 'bar.png'
    item4.save_id = 77

    item5 = BeePixmapItem(QtGui.QImage())
    item5.save_id = 22

    result = sort_by_filename([item1, item2, item3, item4, item5])
    assert result == [item4, item2, item5, item3, item1]


def test_sort_by_filename_when_only_by_filename(view):
    item1 = BeePixmapItem(QtGui.QImage())
    item1.filename = 'foo.png'
    item2 = BeePixmapItem(QtGui.QImage())
    item2.filename = 'bar.png'
    assert sort_by_filename([item1, item2]) == [item2, item1]


def test_sort_by_filename_when_only_by_save_id(view):
    item1 = BeePixmapItem(QtGui.QImage())
    item1.save_id = 66
    item2 = BeePixmapItem(QtGui.QImage())
    item2.save_id = 33
    assert sort_by_filename([item1, item2]) == [item2, item1]


def test_sort_by_filename_deals_with_text_items(view):
    item1 = BeeTextItem('Foo')
    item2 = BeeTextItem('Bar')
    assert len(sort_by_filename([item1, item2])) == 2


def test_items_in_order_without_sort_order_sorts_by_filename(view):
    item1 = BeePixmapItem(QtGui.QImage(), filename='b.png')
    item2 = BeePixmapItem(QtGui.QImage(), filename='a.png')
    assert items_in_order([item1, item2]) == [item2, item1]


def test_items_in_order_sort_order_first(view):
    item1 = BeePixmapItem(QtGui.QImage(), filename='a.png')
    item2 = BeeTextItem('foo')
    item2.sort_order = 2.0
    item3 = BeeTextItem('bar')
    item3.sort_order = 1.0
    item4 = BeePixmapItem(QtGui.QImage(), filename='b.png')
    result = items_in_order([item1, item2, item3, item4])
    assert result == [item3, item2, item1, item4]


def test_items_in_order_accepts_iterators(view):
    item = BeeTextItem('foo')
    assert items_in_order(iter([item])) == [item]
