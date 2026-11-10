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

"""Spanish translations.

The ``&`` marks the keyboard mnemonic of a menu entry, so it needs to
be unique within its menu. Placeholders like ``{filename}`` and ``%s``
have to be kept as they are.
"""

TRANSLATIONS = {
    # Menus
    '&File': '&Archivo',
    'Open &Recent': 'Abrir &reciente',
    '&Edit': '&Editar',
    '&View': '&Ver',
    '&Insert': '&Insertar',
    '&Transform': '&Transformar',
    '&Normalize': '&Normalizar',
    '&Arrange': '&Organizar',
    '&Images': 'I&mágenes',
    '&Settings': '&Configuración',
    '&Help': 'Ay&uda',

    # Actions: File
    '&New Scene': '&Nueva escena',
    '&Open': '&Abrir',
    '&Save': '&Guardar',
    'Save &As...': 'G&uardar como...',
    'E&xport Scene...': 'E&xportar escena...',
    'Export &Images...': 'Exportar &imágenes...',
    '&Quit': '&Salir',

    # Actions: Edit
    '&Undo': '&Deshacer',
    '&Redo': '&Rehacer',
    '&Select All': '&Seleccionar todo',
    'Deselect &All': 'Deseleccionar t&odo',
    'Cu&t': 'Cor&tar',
    '&Copy': '&Copiar',
    '&Paste': '&Pegar',
    '&Delete': '&Eliminar',
    '&Raise to Top': 'Traer al &frente',
    'Lower to Bottom': 'Enviar al fondo',

    # Actions: View
    '&Fit Scene': '&Ajustar escena',
    'Fit &Selection': 'Ajustar &selección',
    '&Fullscreen': '&Pantalla completa',
    '&Always On Top': 'Siempre &encima',
    'Show &Scrollbars': 'Mostrar &barras de desplazamiento',
    'Show &Menu Bar': 'Mostrar barra de &menú',
    'Show &Title Bar': 'Mostrar barra de &título',
    'Ta&blet Mode': 'M&odo tablet',
    '&Lock Images': 'B&loquear imágenes',
    'Move &Window': 'Mover &ventana',

    # Actions: Insert
    '&Images...': '&Imágenes...',
    '&Text': '&Texto',

    # Actions: Transform
    '&Crop': '&Recortar',
    'Flip &Horizontally': 'Voltear &horizontalmente',
    'Flip &Vertically': 'Voltear &verticalmente',
    'Reset &Scale': 'Restablecer &escala',
    'Reset &Rotation': 'Restablecer r&otación',
    'Reset &Flip': 'Restablecer vol&teo',
    'Reset Cro&p': 'Restablecer re&corte',
    'Reset &All': 'Restablecer to&do',

    # Actions: Normalize
    '&Height': '&Altura',
    '&Width': 'A&nchura',
    '&Size': '&Tamaño',

    # Actions: Arrange
    '&Optimal': 'Ó&ptimo',
    '&Horizontal (by filename)': '&Horizontal (por nombre de archivo)',
    '&Vertical (by filename)': '&Vertical (por nombre de archivo)',
    '&Square (by filename)': '&Cuadrado (por nombre de archivo)',

    # Actions: Images
    'Change &Opacity...': 'Cambiar &opacidad...',
    '&Grayscale': 'Escala de &grises',
    'Show &Color Gamut': 'Mostrar g&ama de color',
    'Sample Color': 'Muestrear color',

    # Actions: Settings
    '&Keyboard && Mouse': '&Teclado y ratón',
    '&Open Settings Folder': '&Abrir carpeta de configuración',

    # Actions: Help
    '&About': 'Acerca &de',
    'Show &Debug Log': 'Mostrar &registro de depuración',

    # Actions: Recent files (as listed in the keyboard shortcuts)
    **{f'File {i}': f'Archivo {i}' for i in range(1, 11)},

    # Mouse and mouse wheel actions
    'Zoom': 'Zoom',
    'Zoom (alternative)': 'Zoom (alternativo)',
    'Pan': 'Desplazar',
    'Pan (alternative)': 'Desplazar (alternativo)',
    'Pan horizontally': 'Desplazar en horizontal',
    'Pan horizontally (alternative)': 'Desplazar en horizontal (alternativo)',
    'Pan vertically': 'Desplazar en vertical',
    'Pan vertically (alternative)': 'Desplazar en vertical (alternativo)',
    'Move Window': 'Mover ventana',

    # Modifier keys and mouse buttons
    'No Modifier': 'Sin modificador',
    'Shift': 'Mayús',
    'Ctrl': 'Ctrl',
    'Alt': 'Alt',
    'Meta': 'Meta',
    'Keypad': 'Teclado numérico',
    'Not Configured': 'Sin configurar',
    'Left': 'Izquierdo',
    'Middle': 'Central',
    'Right': 'Derecho',

    # Keyboard and mouse controls dialog
    'Keyboard & Mouse Controls': 'Controles de teclado y ratón',
    'Search...': 'Buscar...',
    '&Keyboard Shortcuts': '&Atajos de teclado',
    '&Mouse': '&Ratón',
    'Mouse &Wheel': 'Rueda del ra&tón',
    '&Restore Defaults': 'Restablecer valores &predeterminados',
    'Restore defaults?': '¿Restablecer valores predeterminados?',
    ('Do you want to restore all keyboard and mouse settings '
     'to their default values?'):
    ('¿Quieres restablecer todos los ajustes de teclado y ratón '
     'a sus valores predeterminados?'),
    'Action': 'Acción',
    'Shortcut': 'Atajo',
    'Alternative': 'Alternativo',
    'Button': 'Botón',
    'Modifiers': 'Modificadores',
    'Inverted': 'Invertido',
    'Yes': 'Sí',
    'No': 'No',
    'Changed from default': 'Modificado respecto al valor predeterminado',
    'Default: {default}': 'Predeterminado: {default}',
    'Not configured': 'Sin configurar',
    'Not set': 'Sin asignar',
    'Mouse Controls for:': 'Controles del ratón para:',
    'MouseWheel Controls for:': 'Controles de la rueda del ratón para:',
    'Mouse Button:': 'Botón del ratón:',
    'Save Shortcut?': '¿Guardar atajo?',
    ('<p>This shortcut is already used for:</p>'
     '<p>{action}</p>'
     '<p>Do you want to remove the other shortcut'
     ' to save this one?</p>'):
    ('<p>Este atajo ya se usa para:</p>'
     '<p>{action}</p>'
     '<p>¿Quieres quitar el otro atajo'
     ' para guardar este?</p>'),
    'Save Controls?': '¿Guardar controles?',
    ('<p>These controls are already used for:</p>'
     '<p>{action}</p>'
     '<p>Do you want to remove the other controls'
     ' to save these ones?</p>'):
    ('<p>Estos controles ya se usan para:</p>'
     '<p>{action}</p>'
     '<p>¿Quieres quitar los otros controles'
     ' para guardar estos?</p>'),

    # Settings dialog
    '{app} Settings': 'Configuración de {app}',
    '&Miscellaneous': '&Varios',
    '&Images && Items': '&Imágenes y elementos',
    ('Do you want to restore all settings to their default values?'):
    ('¿Quieres restablecer todos los ajustes a sus valores predeterminados?'),
    'Language:': 'Idioma:',
    'The language of the user interface.': 'El idioma de la interfaz.',
    'Automatic (system language)': 'Automático (idioma del sistema)',
    ('Use the language of the operating system if available, '
     'otherwise English'):
    ('Usa el idioma del sistema operativo si está disponible; '
     'si no, inglés'),
    'Confirm when closing an unsaved file:':
    'Confirmar al cerrar un archivo sin guardar:',
    ('When about to close an unsaved file, should BeeRef ask for '
     'confirmation?'):
    ('Al ir a cerrar un archivo sin guardar, ¿debe BeeRef pedir '
     'confirmación?'),
    'Confirm when closing': 'Confirmar al cerrar',
    'Image Storage Format:': 'Formato de almacenamiento de imágenes:',
    ('How images are stored inside bee files.'
     ' Changes will only take effect on newly saved images.'):
    ('Cómo se guardan las imágenes dentro de los archivos bee.'
     ' Los cambios solo se aplican a las imágenes que se guarden'
     ' a partir de ahora.'),
    'Best Guess': 'Elección automática',
    ('Small images and images with alpha channel are stored as png,'
     ' everything else as jpg'):
    ('Las imágenes pequeñas y las que tienen canal alfa se guardan'
     ' como png; el resto, como jpg'),
    'Always PNG': 'Siempre PNG',
    'Lossless, but large bee file':
    'Sin pérdida, pero el archivo bee ocupa más',
    'Always JPG': 'Siempre JPG',
    'Small bee file, but lossy and no transparency support':
    'El archivo bee ocupa menos, pero con pérdida y sin transparencia',
    'Maximum Image Size:': 'Tamaño máximo de imagen:',
    ('The maximum image size that can be loaded (in megabytes). '
     'Set to 0 for no limitation.'):
    ('El tamaño máximo de imagen que se puede cargar (en megabytes). '
     'Usa 0 para no poner límite.'),
    'Text Editing': 'Edición de texto',
    'Drawing': 'Dibujo',
    'D&uplicate': 'D&uplicar',
    'Zoom &In': 'A&cercar',
    'Zoom &Out': 'Ale&jar',
    'Act&ual Size': 'Tamaño &real',
    '&Center on Origin': 'Centrar en el ori&gen',
    '&Longest Side': 'Lado más &largo',
    'S&cale': '&Escala',
    'Square (by &time added)': 'Cuadrado (por orden de &inserción)',
    'Square (ran&dom)': 'Cuadrado (&aleatorio)',
    'Align &Left': 'Alinear a la i&zquierda',
    'Align R&ight': 'Alinear a la &derecha',
    'Align To&p': 'Alinear arri&ba',
    'Align &Bottom': 'Alinear aba&jo',
    'Distribute Hori&zontally': 'Distribuir horizontal&mente',
    'Distribute V&ertically': 'Distribuir verticalm&ente',
    'St&ack': 'Api&lar',
    '&Pixelated (No Smoothing)': '&Pixelado (sin suavizado)',
    '&Grayscale Canvas': 'Lienzo en escala de gr&ises',
    'Normalize To:': 'Normalizar respecto a:',
    'Which size the normalize actions use as reference':
    'Qué tamaño usan como referencia las acciones de normalizar',
    'Average': 'Promedio',
    'The average of all affected items':
    'El promedio de todos los elementos afectados',
    'First Item': 'Primer elemento',
    'The first item in hierarchy order':
    'El primer elemento en el orden de la jerarquía',
    'Undo History Size:': 'Tamaño del historial de deshacer:',
    ('How many steps can be undone. Takes effect with the next '
     'new or opened scene. More steps use more memory.'):
    ('Cuántos pasos se pueden deshacer. Se aplica a la siguiente escena '
     'nueva o abierta. Más pasos usan más memoria.'),
    'Arrange Gap:': 'Separación al organizar:',
    'The gap between images when using arrange actions.':
    'La separación entre imágenes al usar las acciones de organizar.',
    'Default Arrange Method:': 'Método de organización predeterminado:',
    'How images are arranged when inserted in batch':
    'Cómo se organizan las imágenes al insertar varias a la vez',
    'Optimal': 'Óptimo',
    'Arrange Optimal': 'Organización óptima',
    'Horizontal (by filename)': 'Horizontal (por nombre de archivo)',
    'Arrange Horizontal (by filename)':
    'Organizar en horizontal (por nombre de archivo)',
    'Vertical (by filename)': 'Vertical (por nombre de archivo)',
    'Arrange Vertical (by filename)':
    'Organizar en vertical (por nombre de archivo)',
    'Square (by filename)': 'Cuadrado (por nombre de archivo)',
    'Arrange Square (by filename)':
    'Organizar en cuadrado (por nombre de archivo)',
    '&Tablet Mode': 'Modo &tablet',
    'Pan:': 'Desplazar:',
    'The mouse controls for panning while tablet mode is on.':
    'Los controles del ratón para desplazar con el modo tablet activado.',
    'Zoom:': 'Zoom:',
    ('The mouse controls for zooming while tablet mode is on. '
     'Drag up or down to zoom.'):
    ('Los controles del ratón para hacer zoom con el modo tablet activado. '
     'Arrastra hacia arriba o hacia abajo para hacer zoom.'),
    'Zoom Direction:': 'Dirección del zoom:',
    'Swap dragging up and down when zooming while tablet mode is on.':
    ('Intercambia arrastrar hacia arriba y hacia abajo al hacer zoom con '
     'el modo tablet activado.'),
    'Inverted': 'Invertido',
    'Title Bar Button:': 'Botón de la barra de título:',
    ('Show a button in the title bar to turn tablet mode on and '
     'off (Windows only). It is also available in the View menu.'):
    ('Muestra un botón en la barra de título para activar y desactivar el '
     'modo tablet (solo en Windows). También está en el menú Ver.'),
    'Show button': 'Mostrar botón',
    '&Lock Icon': '&Candado',
    'Position:': 'Posición:',
    'The corner of the window in which the padlock is shown.':
    'La esquina de la ventana en la que se muestra el candado.',
    'Top left': 'Arriba a la izquierda',
    'Top right': 'Arriba a la derecha',
    'Bottom left': 'Abajo a la izquierda',
    'Bottom right': 'Abajo a la derecha',
    'Size:': 'Tamaño:',
    'The width and height of the padlock.':
    'La anchura y la altura del candado.',
    'Transparency:': 'Transparencia:',
    'How see-through the padlock is. 0 % is fully opaque.':
    'Lo transparente que es el candado. Con 0 % es totalmente opaco.',

    # Other dialogs and widgets
    'Images are locked. Click to unlock.':
    'Las imágenes están bloqueadas. Haz clic para desbloquearlas.',
    'Images are unlocked. Click to lock.':
    'Las imágenes están desbloqueadas. Haz clic para bloquearlas.',
    'Tablet Mode': 'Modo tablet',
    'Cancel': 'Cancelar',
    '{app} Help': 'Ayuda de {app}',
    '&Controls': '&Controles',
    '{app} Debug Log': 'Registro de depuración de {app}',
    'Co&py To Clipboard': '&Copiar al portapapeles',
    'Export Scene to Image': 'Exportar escena a imagen',
    'Width:': 'Anchura:',
    'Height:': 'Altura:',
    'Change Opacity:': 'Cambiar opacidad:',
    'Opacity:': 'Opacidad:',
    'Opacity: {value}%': 'Opacidad: {value}%',
    'File exists': 'El archivo ya existe',
    'File already exists:\n{filename}': 'El archivo ya existe:\n{filename}',
    'Skip this file': 'Omitir este archivo',
    'Skip all existing files': 'Omitir todos los archivos existentes',
    'Overwrite this file': 'Sobrescribir este archivo',
    'Overwrite all existing files':
    'Sobrescribir todos los archivos existentes',
    'Counting pixels...': 'Contando píxeles...',
    'Color Gamut': 'Gama de color',
    'Threshold:': 'Umbral:',

    # Welcome overlay
    '<p>Paste or drop images here.</p><p>Right-click for more options.</p>':
    ('<p>Pega o suelta imágenes aquí.</p>'
     '<p>Haz clic derecho para ver más opciones.</p>'),
    'Recent Files': 'Archivos recientes',

    # Main window
    '[Untitled]': '[Sin título]',
    'Discard unsaved changes?': '¿Descartar los cambios sin guardar?',
    'There are unsaved changes. Are you sure you want to open a new scene?':
    'Hay cambios sin guardar. ¿Seguro que quieres abrir una nueva escena?',
    'There are unsaved changes. Are you sure you want to quit?':
    'Hay cambios sin guardar. ¿Seguro que quieres salir?',
    'Open file': 'Abrir archivo',
    'Save file': 'Guardar archivo',
    '{app} File (*.bee)': 'Archivo de {app} (*.bee)',
    'Image Files (*.png *.jpg *.jpeg *.svg)':
    'Archivos de imagen (*.png *.jpg *.jpeg *.svg)',
    'Export Images': 'Exportar imágenes',
    'Select one or more images to open':
    'Selecciona una o más imágenes para abrir',
    'Images ({formats})': 'Imágenes ({formats})',
    'Loading {filename}': 'Cargando {filename}',
    'Saving {filename}': 'Guardando {filename}',
    'Exporting {filename}': 'Exportando {filename}',
    'Exporting to {directory}': 'Exportando a {directory}',
    'Loading images': 'Cargando imágenes',
    'About {app}': 'Acerca de {app}',
    'BeeRef Reference Image Viewer': 'BeeRef: visor de imágenes de referencia',
    'Visit the {app} website': 'Visita el sitio web de {app}',
    'Text': 'Texto',

    # Notifications
    'No image data or text in clipboard or image too big':
    ('No hay datos de imagen ni texto en el portapapeles, '
     'o la imagen es demasiado grande'),
    'Copied color to clipboard: {name}':
    'Color copiado al portapapeles: {name}',
    'Attempted drop not an image or image too big':
    'Lo que intentas soltar no es una imagen o es demasiado grande',

    # Errors
    'Problem loading file': 'Problema al cargar el archivo',
    ('<p>Problem loading file %s</p>'
     '<p>Not accessible or not a proper bee file</p>'):
    ('<p>Problema al cargar el archivo %s</p>'
     '<p>No se puede acceder a él o no es un archivo bee válido</p>'),
    'Problem saving file': 'Problema al guardar el archivo',
    ('<p>Problem saving file %s</p>'
     '<p>File/directory not accessible</p>'):
    ('<p>Problema al guardar el archivo %s</p>'
     '<p>No se puede acceder al archivo o a la carpeta</p>'),
    'Problem writing file': 'Problema al escribir el archivo',
    '<p>Problem writing file {filename}</p><p>{errors}</p>':
    '<p>Problema al escribir el archivo {filename}</p><p>{errors}</p>',
    'Error writing file': 'Error al escribir el archivo',
    'Problem loading images': 'Problema al cargar las imágenes',
    '{num} image(s) could not be opened.<br/>':
    'No se pudieron abrir {num} imagen(es).<br/>',
    ('Unknown format or too big?\n'
     'Check Settings -> Images & Items -> Maximum Image Size'):
    ('¿Formato desconocido o demasiado grande?\n'
     'Comprueba Configuración -> Imágenes y elementos -> '
     'Tamaño máximo de imagen'),
    'Image could not be loaded: {filename}\n':
    'No se pudo cargar la imagen: {filename}\n',
    'Item of unknown type: {typ}': 'Elemento de tipo desconocido: {typ}',
}
