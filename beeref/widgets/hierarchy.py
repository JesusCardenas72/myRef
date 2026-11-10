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

"""The hierarchy panel and the comment dialog."""

import logging

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from beeref import commands
from beeref import hierarchy
from beeref.i18n import _
from beeref.widgets.textformat import EditorTarget, TextFormatToolbar


logger = logging.getLogger(__name__)

ITEM_ROLE = Qt.ItemDataRole.UserRole
LOCK_SYMBOL = '\U0001F512'
COMMENT_SYMBOL = '\U0001F4AC'


class HierarchyTree(QtWidgets.QTreeWidget):
    """Tree of all items in the scene.

    Selecting tree items selects them in the scene and vice versa.
    Dragging tree items changes parents and order; double clicking
    renames; clicking the lock or comment columns toggles the lock or
    edits the comment.
    """

    COL_NAME = 0
    COL_LOCK = 1
    COL_COMMENT = 2

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.signature = None
        self.syncing = False
        self.setColumnCount(3)
        self.setHeaderHidden(True)
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(
            QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked
            | QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            self.COL_NAME, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for col in (self.COL_LOCK, self.COL_COMMENT):
            header.setSectionResizeMode(
                col, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.itemChanged.connect(self.on_item_changed)
        self.itemClicked.connect(self.on_item_clicked)

        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.refresh)
        self.connect_scene()

    @property
    def scene(self):
        return self.view.scene

    def connect_scene(self):
        self.scene.changed.connect(self.schedule_refresh)
        self.scene.selectionChanged.connect(self.on_scene_selection_changed)
        self.view.undo_stack.indexChanged.connect(self.schedule_refresh)

    def schedule_refresh(self, *args):
        if self.isVisible():
            self.timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def scene_item(self, tree_item):
        return tree_item.data(self.COL_NAME, ITEM_ROLE)

    def structure(self):
        """The items in tree order: List of (item, depth)."""

        result = []

        def add(items, depth):
            for item in items:
                result.append((item, depth))
                add(self.scene.ordered_children(item), depth + 1)

        add(self.scene.ordered_children(None), 0)
        return result

    def compute_signature(self, structure):
        return [(id(item), depth, item.display_name(), item.locked,
                 bool(item.comment))
                for item, depth in structure]

    def refresh(self, force=False):
        """Rebuild the tree if the scene's hierarchy has changed."""

        structure = self.structure()
        signature = self.compute_signature(structure)
        if signature == self.signature and not force:
            self.sync_selection_from_scene()
            return
        self.signature = signature
        logger.trace('Rebuilding hierarchy tree')

        expanded = {id(self.scene_item(item))
                    for item in self.iter_tree_items() if item.isExpanded()}
        self.syncing = True
        self.blockSignals(True)
        self.clear()
        tree_items = {}
        for item, depth in structure:
            tree_item = QtWidgets.QTreeWidgetItem()
            tree_item.setData(self.COL_NAME, ITEM_ROLE, item)
            tree_item.setText(self.COL_NAME, item.display_name())
            tree_item.setText(self.COL_LOCK, LOCK_SYMBOL if item.locked
                              else '')
            tree_item.setText(self.COL_COMMENT,
                              COMMENT_SYMBOL if item.comment else '')
            tree_item.setToolTip(self.COL_LOCK, _('Click to lock or unlock'))
            tree_item.setToolTip(self.COL_COMMENT,
                                 _('Click to edit the comment'))
            tree_item.setFlags(tree_item.flags()
                               | Qt.ItemFlag.ItemIsEditable)
            parent = item.parentItem()
            if parent in tree_items:
                tree_items[parent].addChild(tree_item)
            else:
                self.addTopLevelItem(tree_item)
            tree_items[item] = tree_item
        for item, tree_item in tree_items.items():
            if id(item) in expanded or item.isSelected():
                tree_item.setExpanded(True)
        self.blockSignals(False)
        self.syncing = False
        self.sync_selection_from_scene()

    def iter_tree_items(self):
        iterator = QtWidgets.QTreeWidgetItemIterator(self)
        while iterator.value():
            yield iterator.value()
            iterator += 1

    def sync_selection_from_scene(self):
        self.syncing = True
        self.blockSignals(True)
        for tree_item in self.iter_tree_items():
            selected = self.scene_item(tree_item).isSelected()
            if selected:
                parent = tree_item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
            tree_item.setSelected(selected)
        self.blockSignals(False)
        self.syncing = False
        self.viewport().update()

    def on_scene_selection_changed(self):
        if self.isVisible() and not self.syncing:
            self.sync_selection_from_scene()

    def on_tree_selection_changed(self):
        if self.syncing:
            return
        items = [self.scene_item(t) for t in self.selectedItems()]
        self.syncing = True
        self.scene.select_items(items)
        self.syncing = False

    def on_item_changed(self, tree_item, column):
        if self.syncing or column != self.COL_NAME:
            return
        item = self.scene_item(tree_item)
        name = tree_item.text(self.COL_NAME).strip()
        if name == item.default_name():
            name = ''
        if name != item.name:
            self.view.undo_stack.push(commands.RenameItem(item, name))
        self.schedule_refresh()

    def on_item_clicked(self, tree_item, column):
        item = self.scene_item(tree_item)
        if column == self.COL_LOCK:
            self.view.undo_stack.push(
                commands.SetItemsLocked([item], not item.locked))
            self.refresh()
        elif column == self.COL_COMMENT:
            self.view.edit_comment([item])
            self.refresh()

    def dropEvent(self, event):
        """Apply drag and drop to the scene's hierarchy; the tree gets
        rebuilt from the scene afterwards."""

        target = self.itemAt(event.position().toPoint())
        indicator = self.dropIndicatorPosition()
        Indicator = QtWidgets.QAbstractItemView.DropIndicatorPosition
        items = [self.scene_item(t) for t in self.selectedItems()]
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        if not items:
            return

        if target is None or indicator == Indicator.OnViewport:
            parent, index = None, None
        elif indicator == Indicator.OnItem:
            parent, index = self.scene_item(target), None
        else:
            target_item = self.scene_item(target)
            parent = target_item.parentItem()
            siblings = self.scene.ordered_children(parent)
            index = siblings.index(target_item)
            if indicator == Indicator.BelowItem:
                index += 1
        self.scene.move_in_hierarchy(items, parent, index)
        self.refresh(force=True)

    def selected_scene_items(self):
        return hierarchy.top_most(
            [self.scene_item(t) for t in self.selectedItems()])


class HierarchyDock(QtWidgets.QDockWidget):
    """Dock widget holding the hierarchy tree."""

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.setObjectName('HierarchyDock')
        self.tree = HierarchyTree(view, self)
        self.setWidget(self.tree)
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(_('Hierarchy'))

    def closeEvent(self, event):
        super().closeEvent(event)
        self.tree.view.on_hierarchy_closed()


class CommentDialog(QtWidgets.QDialog):
    """Dialog for editing an item's comment."""

    def __init__(self, parent, comment=''):
        super().__init__(parent)
        self.setWindowTitle(_('Comment'))
        layout = QtWidgets.QVBoxLayout(self)
        self.editor = QtWidgets.QTextEdit()
        self.editor.setAcceptRichText(True)
        self.editor.setHtml(comment or '')
        self.toolbar = TextFormatToolbar(
            EditorTarget(self.editor), self, for_notes=False)
        self.editor.cursorPositionChanged.connect(self.toolbar.update_state)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.editor)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(max(400, self.toolbar.sizeHint().width() + 20), 250)
        self.editor.setFocus()

    def comment(self):
        """The edited comment as HTML, or an empty string if there's no
        text."""

        if not self.editor.toPlainText().strip():
            return ''
        return self.editor.toHtml()
