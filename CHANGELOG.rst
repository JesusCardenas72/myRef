0.7.0 (2026-11-11)
==================

Added
-----

* Window opacity control in the top right corner of the view. Hover the
  icon to unfold a vertical slider from 100 % (top) to 5 % (bottom). Drag
  or scroll to change the opacity of the whole window; it folds up again
  when the mouse leaves. Moves next to the lock icon if both are in the
  top right corner.

Changed
-------

* The minimum window opacity is now 5 % (was 10 %).

0.6.0 (2026-11-11)
==================

Added
-----

* Image features and shortcuts from PureRef's handbook (see
  ``PLAN_IMAGENES.md``):

  * Transform by dragging anywhere on an item: rotate (Ctrl), snapped
    rotate (Ctrl + Shift), scale (Ctrl + Alt), opacity
    (Ctrl + Alt + Shift) and flip in the drag direction (Alt + Shift).
    Configurable in Settings -> Keyboard & Mouse.
  * Hold a key and drag: C crops the selected images to a rectangle,
    V pans the image inside its crop, Shift + V zooms inside the crop,
    Z zooms the view, S shows the colour and D the pixel coordinates
    under the cursor.
  * Crop handles: Shift keeps the aspect ratio, Shift + Alt makes a
    square. Alt on the scale handles scales from the center.
  * Shift + Click adds to or removes from the selection; Shift + Drag on
    the empty canvas adds to the selection.
  * Return edits the selected note or drawing, or enters the group.
  * Focus next/previous image (Right/Left) and slideshow (Alt + S,
    interval in the settings).
  * Open source (Ctrl + Shift + O), replace image, and a button to
    unlock a locked item by clicking on it.
  * Linked images: with "Embed local images in save file" turned off,
    bee files only store the path of images opened from disk. Missing
    files can be relinked (Ctrl + Alt + Shift + R or double-click).
  * Manage images (Ctrl + Shift + J): downscale, convert the storage
    format, discard cropped pixels, embed or link, with a preview.
  * Pasting or dropping the address of a web page imports all its
    images; pasting files copied in the file browser inserts them.
  * Arrange by name (Ctrl + Alt + N), path (Ctrl + Alt + D) and
    hierarchy order (Ctrl + Alt + O); arranging twice reverses the
    order.
  * Settings for the default image sampling and the rotation snap
    angle (45 degrees by default, as in PureRef).

Changed
-------

* New application icon.
* Files are saved with the ``.mref`` extension instead of ``.bee``. Files
  with the ``.bee`` extension can still be opened; saving one of them
  asks for a new ``.mref`` file name and leaves the original untouched.
* Moving the window is now Right Click + Drag (pans while maximized);
  Ctrl + Alt + Drag scales items instead.
* Ctrl + Click no longer toggles the selection (Ctrl + Drag rotates);
  use Shift + Click.
* Ctrl + Alt + Up normalizes the longest side ("Size" in PureRef);
  normalizing the area is now called "Area" and has no shortcut.

Fixed
-----

* The alternative mouse binding for moving the window had no effect.


0.5.0 (2026-11-10)
==================

Added
-----

* Drawing (Insert -> Draw, Ctrl + Shift + D): Pen, line, arrow,
  rectangle, ellipse and eraser tools (D, L, A, R, C, E) with colour,
  line width and solid, dashed or dotted lines. Hold Shift for 45
  degree lines, squares and circles. Pen strokes get smoothed. The
  eraser removes whole strokes. Drawings are items like images and
  text: they can be moved, scaled, grouped and parented. Double click
  a drawing to continue drawing on it. SVG export writes drawings as
  vector paths.
* Rich text notes, with a new Text menu and a formatting toolbar that
  floats above the note while editing it:

  * Bold, italic, underline, strikethrough, text and highlight colour,
    font and size, alignment, note background colour.
  * Bullet lists, numbered lists and checklists (click the check box
    to tick it); Tab / Shift + Tab change the indentation.
  * Links (Ctrl + K), opened with Ctrl + Click. Links to bee files open
    them in BeeRef.
  * Fixed width with word wrap: drag the right edge of a note while
    editing it.
  * Copy and paste formats (Ctrl + Alt + C / Ctrl + Alt + V), clear
    formatting, paste as plain text (Ctrl + Shift + V).
  * Formatting selected notes without editing them changes all of
    them at once.
  * A note inserted while an image is selected gets attached to it.
  * Comments use the same formatting toolbar.

* New Items menu:

  * Parenting (P / Shift + P): Children move, scale and rotate along
    with their parent.
  * Lock single items (Alt + L) and unlock all of them (Alt + Shift + L).
  * Comments on items (Alt + C), shown as tooltip.
  * Rename items (F2).

* New Group menu:

  * Groups (Ctrl + G / Ctrl + Shift + G): Drawn as a coloured area
    behind their items. Clicking an item in a group selects the
    group; double click to select items inside it. Moving items onto
    a group puts them into it (can be turned off in the settings).
    Empty groups are removed.
  * Groups have a border and show their name as title in the top
    right corner. Double click the title to rename the group.
  * Group Style: background colour, border colour, width, line style
    (solid, dashes, dots, dash-dot, dash-dot-dot) and shape (straight,
    zigzag, wave, scallops, battlements, with adjustable wave height
    and length), title colour and size, and opacity of the whole
    group. Live preview; one undo step. Border and title are drawn
    inside the group's area, so they are included when exporting.
  * Add to Group and Remove from Group (taking items out of a
    subgroup puts them into the outer group).
  * Enter Group / Exit Group, Group Title, Group Colour, Group
    Opacity, Focus Group.
  * Arrange Contents / Normalize Contents: All arrange, align,
    distribute, stack and normalize actions for the items inside the
    selected group; subgroups count as one item.
  * Subgroups: Group items inside an open group. Items dropped onto a
    closed group with subgroups go into the closed group.
  * Grouping items with different parents now tells which items have
    been left out.

* SVG export includes groups (background, border, title), and the
  opacity of groups applies to their items.
* New hierarchy panel (View -> Hierarchy, Ctrl + J): Shows all items
  as a tree. Drag to reorder and to change parents, double click to
  rename, click the lock and comment columns to lock or comment.
  Exporting uses the order of the hierarchy.
* New View -> Canvas menu:

  * Show a grid of lines or dots (Ctrl + '). It gets coarser when
    zooming out.
  * Snap to grid (Ctrl + Shift + ') and snap to the edges and centers
    of other items (Shift + Space) while moving items, with guide
    lines. Hold Alt to not snap.
  * Focus canvas: Fits the view to all items plus the canvas margin.
  * Optimize canvas: Moves all items to the origin, which keeps
    zooming and panning precise in scenes that have drifted far away.

* New settings tab "Canvas": grid size and style, snap distance,
  highlighting the canvas area and its margin.
* New View -> Window menu with window modes:

  * Click-through (Ctrl + Alt + T): The window stays visible, but
    mouse clicks go to the windows behind it. Turn it off via the tray
    icon or a global shortcut.
  * Window opacity (Ctrl + Alt + Up/Down).
  * Always on bottom, and always on top of a chosen application
    (Windows only).
  * Lock window: The window can't be moved or resized.
  * Fit window to selection: Resizes the window around the selected
    items (or all items) without moving them on screen.
  * Maximize, optionally covering the taskbar and locking the size.
  * Show the title bar only while hovering over the top of the window.

* Windows without title bar can be resized by dragging their border.
* New settings tab "Window": opacity, window mode on startup, notices
  on mode changes, tray icon, global shortcuts (Windows only), scaling
  the scene when resizing the window, resize border width.
* Align items left/right/top/bottom (Ctrl + Arrow Keys), distribute
  them evenly and stack them (Arrange menu).
* Normalize by longest side and by scale; normalize either to the
  average or to the first item (Settings -> Images & Items).
* Arrange in a square grid by time added or randomly.
* Arrange, normalize and align now apply to all items when nothing
  is selected.
* Duplicate (Ctrl + D), Zoom In/Out (Ctrl + Plus/Minus), Actual Size
  (0) and Center on Origin.
* Hold Shift while moving to move only horizontally or vertically.
* Hold Shift + Alt while scaling or rotating several items to
  transform each around its own center.
* View -> Grayscale Canvas (Ctrl + Alt + G) shows all images in
  grayscale without changing them.
* Images -> Pixelated (Alt + T) turns off smoothing for selected
  images, e.g. for pixel art.
* File -> Export Selection as Scene and File -> Export Selected Images.
* File name templates and cropped export for exported images
  (Settings -> Export).
* Edit -> Copy as File copies images as PNG files for pasting into
  file browsers.
* File -> Open Last Scene (Ctrl + Shift + L), File -> Show in File
  Browser (Ctrl + Alt + L), and double-click the empty canvas to open
  a scene.
* The undo history size is now configurable
  (Settings -> Settings -> Miscellaneous -> Undo History Size).
* Keyboard shortcuts can now belong to a context (e.g. text editing).
  While editing a text item, shortcuts of that context take precedence
  over global ones; the shortcut editor only reports conflicts within
  the same context.
* Bee file format version 3: items can reference a parent item and
  store their position in the hierarchy (preparation for groups).
  Older bee files are migrated automatically when opened.
* Items of any type are now loaded from bee files; unknown item types
  are shown as error items instead of being silently skipped.
* Added a tablet mode: Pan with the right mouse button and zoom with
  Ctrl + right mouse button. Right-clicking without dragging still opens
  the context menu. Turn it on with the button in the title bar
  (Windows only) or via View -> Tablet Mode. The controls are
  configurable (Settings -> Settings -> Tablet Mode).
* Added a padlock in the corner of the window which locks all items
  against selecting, moving and editing, also available via
  View -> Lock Images. Its corner, size and transparency are
  configurable (Settings -> Settings -> Lock Icon).
* Added Spanish translation and a language setting
  (Settings -> Settings -> Miscellaneous). By default, BeeRef uses the
  language of the operating system if available.
* Added a setting to change the default memory limit for individual
  images. If a big image won't load, increase this limit. This
  setting can be overridden by Qt's default environment variable
  QT_IMAGEIO_MAXALLOC
* Display error messages when images can't be loaded from bee files
* Added option to export all images from scene (File -> Export Images)
* Added a confirmation dialog when attempting to close unsaved files.
  The confirmation dialog can be disalbed in:
  Settings -> Miscellaneous -> Confirm when closing an unsaved file
* Add option to arrange by filename (Arrange -> Square (by filename))
* Added a setting to choose the default arrange method on importing
  images in batch.
  (Settings -> Settings -> Images & Items -> Default Arrange Method).
* Added the ability to open image files from command line. If the
  first command line arg is a bee file, it will be opened and all
  further files will be ignored, as previously. If the first argument
  isn't a bee file, all files will be treated as images and inserted
  as if opened with "Insert -> Images".

Fixed
-----

* Snapped rotations are now also snapped when undoing/redoing them.
* Fixed a random crash when exporting the scene: The scene is now only
  accessed in the main thread, the image is written in the background.
* Fixed "Confirm when closing an unsaved file" being turned on again
  after restarting BeeRef.
* Fixed SVG export failing when the scene contains images that couldn't
  be loaded. These placeholders are now left out of the SVG.
* Fixed a case where adding/importing an image would hang when the image
  contained unsupported exif data (#111)
* Fixed a hang when saving an open bee file that had been removed
  since being opened
* Shortcuts now only trigger once when holding down the key
  combination to avoid inconstistend program states and potential
  crashes (by DarkDefender)
* Fixed a crash when pressing the crop shortcut while dragging an image
  (by DarkDefender)


Changed
-------

* Text is saved with its formatting (as HTML). The plain text is still
  saved as well, so older versions can show it.
* Shift + Enter while editing text starts a new paragraph (or list
  item) instead of a line break.
* File -> Export Images now exports images in a deterministic order
  (by filename).
* Arrange Horiszontal/Vertical now also sort by filename instead of
  the previous seemingly random behaviour


0.3.3 - 2024-05-05
==================

Added
-----

* Moving the window from within BeeRef now changes to a diffent cursor from
  the default arrow cursor.
* Added a color sampler which can copy colors from images to the
  clipboard in hex format (Images -> Sample Color)
* Added notification when attempting to paste from an empty or
  unusable clipboard
* Added panning via scrollwheel:
  * Scroll wheel + Shift + Ctrl: pan vertically
  * Scroll wheel + Shift: pan horizontally
* Make mouse and mouse wheel controls configurable
  (Settings -> Keyboard & Mouse)


Fixed
-----

* Fixed a crash when pressing the keyboard shortcut for New Scene
  while in the process of doing a rubberband selection.
* The checkmark of the menu entry Images -> Grayscale is now updating
  correctly depending on the selected images.
* Removed black line under marching ants outline of crop mode, which
  would scale with the image and get potentially very thick.
* Fixed a crash when importing images with unsupported exif orientation info
* Fixed threading issue when importing images (causing potential
  hangs/weird behaviour)
* Fixed an intermittent crash when invoking New Scene
* Fixed bee files hanging on to disk space of deleted images (issue #99)
* Fixed Drag @ Drop from pinterest feed (by Randommist)
* Fixed pasted items being inserted behind existing items



0.3.2 - 2024-01-21
==================

Added
-----

* For arranging, a gap between images can now be configured in the
  settings.
* The opacity of images can be changed (Images -> Change Opacity).
* Images can be set to display as grayscale (Images -> Grayscale).
* The scene can now also be exported as SVG
* Keyboard shortcuts can now be edited from within BeeRef (Settings ->
  Keyboard Shortcuts). The KeyboardSettings.ini file will now only
  store values which are changed from the default, since it's no longer
  needed as a reference.
* Settings dialog now displays icons to indicate changes from default
  values


Fixed
-----

* Scene Export: Fix output image size and margins when scene had been
  scaled or moved.
* Scene Export: Selecting filename without file extension now
  automatically appends the extension from the selected filter instead
  of resulting in a confusing error message.
* The exemption from antialias/smoothing for images displayed at large
  zoom now also works on images that are flipped horizontally


Changed
-------

* Improved performance of Select All/Deselect All



0.3.1 - 2023-12-10
==================

Added
-----

* Images can now be stored JPG or PNG inside the bee file. By default,
  small images and images with an alpha channel will be stored as PNG,
  the rest as JPG. In the newly created settings dialog, this
  behaviour can be changed to always use PNG (the former behaviour) or
  always JPG. To apply this behaviour to already saved images in
  existing bee files, you can save them as new files.
* Enabled antialiasing/smoothing. Images that are being displayed at a
  large zoom factor are exempt to make sure that icons, pixel sprites
  etc can be viewed correctly.
* A scene can now be exported to a single image (File -> Export Scene...)
* Alternative way to move the BeeRef window without the title bar:
  View -> Move Window (or press "M")


Changed
-------

* Editing of text items will now be undoable after leaving edit mode
* Empty text items will be deleted after leaving edit mode
* Text edit mode can now be aborted with Escape
* "Save as" will now open pre-select the folder of the currently opened file
* "Save" and "Save as" are now inactive when the scene is empty


Fixed
-----

* Fixed a bug where the binary data of deleted images would still hang
  around in the bee file.
* The shortcut to move the BeeRef window (Ctrl + Alt + Drag)
  now works on an empty scene
* Crash when copying an item from a bee file, opening a new scene and
  pasting the image into it.


0.3.0 - 2023-11-23
==================

Added
-----

* Image cropping (Go to "Transform -> Crop", or press Shift + C)
* Show list of recent files on welcome screen
* Keyboard shortcuts can now be configured via a settings file.
  Go to "Settings -> Open Settings Folder" and edit KeyboardSettings.ini
* Remember window geometry when closing (by David Andrs)

Fixed
-----

* Various typos (by luzpaz)
* Ensure that small items always have an area in the middle for
  moving/editing that doesn't trigger transform actions
* Ensure that the first click to select an item doesn't immediately trigger
  transform actions


0.2.0 - 2021-09-06
==================

Note that bee files from version 0.2.0 won't open in BeeRef 0.1.x.

Added
-----

* You can now add plain text notes and paste text from the clipboard
* You can now open bee files from finder on MacOS (by David Andrs)
* Dragging bee files onto an empty scene will now open them
* Adding the first image(s) to a new scene centers the view

Changed
-------

* Make debug log file less verbose
* The program is now bundled as a single executable file (issue #4)

Fixed
-----

* Hovering over the scale handles of very narrow items now displays
  correct cursor orientation
* Fix a rare crash while displaying selection handles


0.1.1 - 2021-07-18
==================

Changed
-------

* Flipping an image now happens on mouse press instead of mouse release
* About dialog points to new website beeref.org
* Menus and dialogs now have a dark style to match the optics of the canvas

Fixed
-----

* Double click to zoom an item and double-clicking again should now always
  correctly go back to the previous position
* The outline of the rubberband selection now stays the same size
  regardless of zoom


0.1.0 - 2021-07-10
==================

First release!
