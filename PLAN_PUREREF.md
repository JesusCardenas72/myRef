# Plan: llevar myRef a la paridad de features con PureRef 2.1

Base: myRef = fork de BeeRef 0.3.4-dev (Python 3 + PyQt6, formato `.bee` sobre SQLite).
Referencia: handbook de PureRef 2.1 (https://www.pureref.com/handbook/).

> **Correcciones a la comparativa previa** (verificadas en el código):
> - El snap de rotación **ya existe** (múltiplos de 15°, `selection.py:490`), no de 45° como en PureRef.
> - El submenú **File → Open Recent ya existe** (`menu_structure.py`); solo falta el atajo "abrir el último".

Escala de esfuerzo: **S** ≤ 1 día · **M** 2–5 días · **L** 1–2 semanas · **XL** > 2 semanas (una persona, a tiempo parcial-completo).

---

## 0. Reglas transversales (aplican a cada feature)

Cada feature nueva se considera terminada solo si incluye:

1. **Acción** en `beeref/actions/actions.py` + entrada en `actions/menu_structure.py` (así aparece en menú, menú contextual y editor de atajos).
2. **Comando de undo** en `beeref/commands.py` si modifica la escena (`QUndoCommand` con `redo`/`undo`).
3. **Ajustes** nuevos declarados en `BeeSettings.FIELDS` (`config/settings.py`) con default y validación; aparecen en `widgets/settings.py`.
4. **Traducción** de todos los textos nuevos en `beeref/i18n/es.py`.
5. **Documentación** en `beeref/documentation/controls.html` y `controls.es.html`, y entrada en `CHANGELOG.rst`.
6. **Tests** en `tests/` (pytest + pytest-qt) espejando el módulo tocado; `flake8` limpio.
7. **Compatibilidad de archivos**: un `.bee` antiguo debe abrirse siempre. Los atributos nuevos van en la columna JSON `items.data` siempre que sea posible (no requiere migración); los cambios estructurales van en `fileio/schema.py → MIGRATIONS` incrementando `USER_VERSION`.

**Atajos por defecto.** Muchos atajos de PureRef chocan con los actuales de BeeRef (p. ej. `Ctrl+O` abrir vs. optimizar lienzo, `G` escala de grises vs. cuadrícula, `Ctrl+T` texto vs. transparente al ratón). Propuesta: mantener los atajos actuales y asignar a lo nuevo combinaciones libres; en la fase 10 añadir un **preset de atajos "estilo PureRef"** seleccionable en ajustes.

---

## Fase 0 · Preparación y refactors habilitantes ✅ (rama `fase-0`)

> Hecha: 0.1–0.7. El formato `.bee` v3 conserva extensión e identificador (decidido en la fase 4).

| # | Tarea | Esfuerzo | Detalle |
|---|---|---|---|
| 0.1 | Control de versiones | S | El directorio **no es un repo git**. `git init`, primer commit con el estado actual, rama por fase. |
| 0.2 | Línea base de calidad | S | Ejecutar `pytest` y `flake8`; dejar CI (`.github/workflows`) en verde antes de tocar nada. |
| 0.3 | Persistencia genérica de items | M | `SQLiteIO.read()` solo carga `pixmap` (JOIN con `sqlar`) y `text` (consulta aparte, hardcodeada). Generalizar: cargar todos los items de `items` y adjuntar el blob de `sqlar` solo si existe, usando `item_registry` para instanciar por `type`. Requisito para grupos, dibujos y GIF. |
| 0.4 | Esquema v3 | M | Migración `USER_VERSION = 3`: columna `parent_id INTEGER NULL REFERENCES items(id)` y `sort_order REAL`. Al escribir, guardar padres antes que hijos (los `save_id` se asignan al insertar). Tests de migración v2→v3 con `tests/assets/test1item.bee`. |
| 0.5 | Tamaño de undo configurable | S | `view.py` fija `setUndoLimit(100)`. Pasarlo a ajuste `Performance/undo_limit` (PureRef: 200). Ojo: Qt solo permite cambiarlo con la pila vacía; aplicar al crear escena nueva. |
| 0.6 | Contextos de atajos | M | Necesario para notas enriquecidas y dibujo (mismo atajo, distinto significado según modo). Añadir a `Action` un campo `context` (`global`, `text_edit`, `draw`) y activar/desactivar `QAction`s al entrar/salir de cada modo. |
| 0.7 | Utilidad de orden de jerarquía | S | Función única `items_in_order(items)` que hoy delegue en `sort_by_filename` y en la fase 4 use el orden de la jerarquía. Arrange, focus siguiente, slideshow y exportación la usarán. |

---

## Fase 1 · Victorias rápidas (sin cambios de formato) ✅ (rama `fase-1`)

> Hecha. Diferencias con lo previsto: "Normalizar área" ya existía como
> "Tamaño", así que se añadió "Lado más largo" (el "tamaño" de PureRef).
> La plantilla de nombres y el recorte al exportar están en Ajustes >
> Exportar en vez de en un diálogo. El doble clic para abrir solo actúa
> con el lienzo vacío. Arrange por ruta = el actual "por nombre de
> archivo" (ya ordena por ruta completa).

Todo vive en `scene.py`, `view.py`, `commands.py` y `fileio/export.py`, reutilizando `ArrangeItems`, `NormalizeItems` y los exportadores existentes.

| Feature PureRef | Esfuerzo | Implementación |
|---|---|---|
| Zoom in / out / 100% / centrar en (0,0) | S | Nuevas acciones sobre `view.zoom()` y `view.scale()`. |
| Duplicar (Ctrl+D) | S | `create_copy()` ya existe en cada item; `InsertItems` con desplazamiento. |
| Alinear izq./der./arriba/abajo | S | Calcular posiciones con `bounding_rect_unselected` y empujar `ArrangeItems`. |
| Distribuir horizontal/vertical | S | Igual, usando `Items/arrange_gap` como padding. |
| Apilar (stack) | S | Mismo origen para todos, orden por z. |
| Normalizar área y escala | S | Extender `normalize_width_or_height` / `NormalizeItems`. Opción "desde el primero" o "promedio". |
| Arrange por orden de adición / ruta / aleatorio | S | Guardar `added_at` en `data` al insertar; ruta = `filename` completo; aleatorio con inversión al repetir. |
| Si no hay selección, aplicar a todo | S | Hoy las acciones de arrange y normalize exigen selección (`active_when_selection`). Cambiar el grupo y el fallback a "todos los items". |
| Rotar o escalar cada item sobre su propio centro | M | Variante de `RotateItemsBy` / `ScaleItemsBy` con un anchor por item; modificador Shift+Alt en `selection.py`. |
| Move con snap a ejes (Shift) | S | En `SelectableMixin.mouseMoveEvent`, bloquear el eje de menor desplazamiento. |
| Escala de grises de todo el lienzo | S | Flag de vista y aplicar en `paint` de cada pixmap (o efecto sobre el viewport). |
| Interruptor de muestreo bilineal / nearest | S | Ajuste global y toggle por item (`data.sampling`) usado en `BeePixmapItem.paint`. |
| Exportar la selección como escena | S | `SceneExporterBase` con lista de items filtrada. |
| Exportar solo imágenes seleccionadas | S | `ImagesToDirectoryExporter` con lista de items. |
| Plantillas de nombre (`%0 %1 %2 %3`) y "exportar recortado" | S | Extender `get_filename_for_export`; diálogo con campo de plantilla y checkbox. |
| Copiar como archivo | S | PNG temporal + `QMimeData.setUrls()` en el portapapeles. |
| Abrir la escena más reciente (atajo) y "abrir ubicación de la escena" | S | `QDesktopServices.openUrl` sobre la carpeta. |
| Doble clic en lienzo vacío → abrir archivo | S | `scene.mouseDoubleClickEvent`. |

**Entregable:** versión 0.4.0. Estimación de la fase: **M–L**.

---

## Fase 2 · Modos de ventana (lo que define a PureRef) ✅ (rama `fase-2`)

> Hecha. Decisiones tomadas: atajos globales con `RegisterHotKey`
> nativo (sin dependencias nuevas, solo Windows; desactivados por
> defecto, se activan en Ajustes > Ventana para todas las acciones de
> ventana a la vez, no con un checkbox por acción). Click-through en
> Windows con estilos nativos (`WS_EX_TRANSPARENT`) sin recrear la
> ventana. "Siempre encima de una app" no usa `GWLP_HWNDPARENT` (Windows
> destruiría nuestra ventana al cerrarse la otra app): vigila qué app
> está en primer plano. Bloquear ventana impide moverla también desde la
> barra de título (filtro nativo; sobrescribir `nativeEvent` hace caer
> PyQt6). Modos al arrancar: normal, último usado, siempre encima,
> click-through.

Código en `__main__.py` (`BeeRefMainWindow`) y `view.py`.

| Feature | Esfuerzo | Implementación y riesgos |
|---|---|---|
| Opacidad global de la app (±10%) | S | `QWidget.setWindowOpacity`; ajuste persistente. |
| Always on bottom | S | `Qt.WindowType.WindowStaysOnBottomHint` (excluyente con always on top). |
| Bloquear ventana | S | Ignorar el modo mover ventana y el redimensionado mientras esté activo. |
| Ajustar ventana a la selección | S | Calcular el rect de los items en coordenadas de pantalla y aplicar `setGeometry`. |
| Barra de título visible al pasar el ratón | M | Hoy es todo o nada (`show_titlebar`). Ventana sin marco + barra propia que aparece en `enterEvent` y bordes de redimensionado propios (ancho configurable). |
| Maximizar sobre la barra de tareas y bloquear al maximizar | S | Geometría de `QScreen.geometry()` en lugar de `availableGeometry()`. |
| **Transparente al ratón (click-through)** | L | `Qt.WindowType.WindowTransparentForInput`; en Windows es más fiable vía `ctypes` con `WS_EX_LAYERED \| WS_EX_TRANSPARENT`. **Riesgo:** con la ventana transparente no se pueden recibir teclas, así que la salida exige **atajo global** (2.x) o un **icono en la bandeja** (`QSystemTrayIcon`). Hay que hacer las dos cosas. |
| Atajos globales del sistema | L | Opción portable: dependencia `pynput` en un hilo que emite señales Qt. Opción nativa: `RegisterHotKey` en Windows mediante `QAbstractNativeEventFilter`. macOS exige permiso de Accesibilidad. Checkbox "global" por acción en el editor de atajos. |
| Icono en bandeja del sistema | S | Menú con: salir de click-through, always on top, mostrar u ocultar, salir. |
| Always on top **de una app concreta** | L | Solo Windows (`SetWindowLongPtr` con `GWLP_HWNDPARENT` hacia la ventana elegida, enumerada con `EnumWindows`). En macOS y Linux no tiene equivalente fiable: marcarlo como solo Windows. |
| Modo de ventana por defecto al arrancar | S | Ajuste: normal, click-through, overlay o último usado. |
| Escalar la escena al redimensionar la ventana | S | En `resizeEvent`, mantener el rect visible. |
| Aviso emergente al cambiar de modo | S | Reutilizar `BeeNotification`. |

**Entregable:** 0.5.0. Estimación: **L–XL**.

---

## Fase 3 · Cuadrícula, snapping y lienzo ✅ (rama `fase-3`)

> Hecha. Decisiones tomadas: el snapping se hace en
> `BeeGraphicsScene.mouseMoveEvent` corrigiendo el delta (igual que el
> movimiento restringido con Shift), no en `itemChange`, para que todo
> el grupo seleccionado se mueva junto. Se imantan bordes y centros a
> otros items (umbral en píxeles de pantalla, Ajustes > Lienzo); si no
> hay ninguno cerca, los bordes exteriores van a la cuadrícula. Alt
> desactiva el imantado mientras se mueve. La cuadrícula se dibuja en
> `drawBackground` con origen en (0, 0) y dobla su tamaño al alejar
> (nunca menos de 12 px en pantalla); se imanta a la cuadrícula visible.
> Atajos: Ctrl+' (cuadrícula), Ctrl+Shift+' (imantar a cuadrícula),
> Shift+Space (imantar a items). Como el lienzo de BeeRef es infinito,
> "Optimizar lienzo" centra todos los items en el origen (deshacible) y
> "Enfocar lienzo" ajusta la vista al área del lienzo (items + margen).
> El área del lienzo más clara es opcional (desactivada por defecto).

| Feature | Esfuerzo | Implementación |
|---|---|---|
| Cuadrícula de líneas o puntos | M | Sobrescribir `BeeGraphicsView.drawBackground`; tamaño adaptativo según el zoom. |
| Snap a la cuadrícula | M | En `itemChange(ItemPositionChange)` de `BeeItemMixin` o en el `mouseMoveEvent` de selección; también al soltar tras `MoveItemsBy`. |
| Snap a los bordes de otras imágenes (Shift+Space) | M | Índice de bordes de los items no seleccionados; umbral en píxeles de pantalla; guías visuales temporales. |
| Optimizar lienzo y enfocar lienzo | S | Ya existe `recalc_scene_rect`; exponer acciones. |
| Lienzo con área más clara que el fondo | S | Dibujar el rect del lienzo en `drawBackground` con un color distinto. |

**Entregable:** 0.6.0. Estimación: **M**.

---

## Fase 4 · Modelo de escena: grupos, jerarquía, bloqueo y comentarios ✅ (rama `fase-4`)

> Hecha. Decisiones tomadas: el formato sigue siendo `.bee` con el
> mismo `APPLICATION_ID` (los archivos de BeeRef se abren sin
> cambios); queda documentado que BeeRef original perdería grupos e
> hijos al guardar un archivo de myRef. `BeeGroupItem` es un
> `QGraphicsItem` propio (no `QGraphicsItemGroup`): sus hijos dejan de
> ser seleccionables mientras está cerrado, así el clic pasa al grupo;
> el doble clic lo abre y se cierra solo al dejar de haber algo suyo
> seleccionado. Reemparentar conserva la transformación en escena
> (`hierarchy.set_parent_keep_transform`). "Emparentar con el primero
> seleccionado" usa el orden en que se seleccionaron los items. El
> orden de la jerarquía (`sort_order` entre hermanos, padres antes que
> hijos) es independiente del orden z. El panel es un `QTreeWidget` que
> se reconstruye desde la escena cuando cambia la estructura. El
> comentario usa por ahora un `QTextEdit` simple (el editor rico llega
> en la fase 5) y se muestra como tooltip. Bloquear (Alt+L) y
> desbloquear todo (Alt+Shift+L) se pueden deshacer; el candado global
> sigue aparte. Arrastrar a grupos se desactiva en Ajustes > Imágenes
> y elementos.

Es **la fase de mayor riesgo**: introduce relaciones padre-hijo en un código que asume que todos los items son de nivel superior.

| Feature | Esfuerzo | Implementación y riesgos |
|---|---|---|
| Parenting (`P`: emparentar con el primero seleccionado) | L | `QGraphicsItem.setParentItem`. **Riesgo:** `pos()` pasa a ser relativo al padre. Revisar todos los usos de `pos()`, `MultiSelectItem`, `ArrangeItems`, exportadores y `SQLiteIO` (guardar coordenadas locales más `parent_id`). |
| Grupos (`Ctrl+G` / `Ctrl+Shift+G`) | L | Nuevo `BeeGroupItem` registrado en `item_registry`: fondo de color configurable, se ajusta a su contenido, bloqueado por defecto (un clic en un hijo selecciona el grupo), doble clic para entrar. Se borra automáticamente si queda vacío. Comandos `GroupItems` / `UngroupItems`. |
| Panel de jerarquía (`Ctrl+J`) | L | `QDockWidget` con `QTreeView` y un modelo propio sincronizado con la escena. Permite arrastrar para reordenar y reemparentar, renombrar (F2) e iconos de estado (bloqueado, comentado y, en la fase 7, enlazado). |
| Orden de la jerarquía como orden canónico | S | La función de la tarea 0.7 pasa a usar `sort_order` y lo aplican arrange, foco, slideshow y exportación. |
| Bloquear items individuales (Alt+L) | S | Ya existe `BeeItemMixin.set_locked`; persistir `data.locked`, desbloquear desde la jerarquía. Mantener también el candado global actual. |
| Comentarios por item (Alt+C) | M | `data.comment` (HTML); diálogo con el mismo editor rico de la fase 5; icono en la jerarquía. |
| Arrastrar items dentro de grupos | M | Detectar el grupo bajo el cursor al soltar; ajuste para activarlo o desactivarlo. |

**Entregable:** 0.7.0, con formato `.bee` v3. Estimación: **XL**.

---

## Fase 5 · Notas de texto enriquecido ✅ (rama `fase-5`)

> Hecha. Decisiones tomadas: se guardan `data.html` y también
> `data.text` (texto plano) para que BeeRef original y versiones
> anteriores sigan mostrando el texto; `text_width` y `background` son
> opcionales. Nuevo menú **Texto** (acciones de formato en el contexto
> `text_edit` para que Ctrl+B/I/U… no choquen con atajos globales como
> Ctrl+I); copiar/pegar/limpiar formato y ancho fijo son globales.
> Fuera del modo edición, el formato se aplica a todo el texto de todas
> las notas seleccionadas (incluidas las de grupos seleccionados), en un
> único paso de deshacer; en modo edición se aplica a la selección y se
> confirma al salir junto con el texto y el ancho. La barra flotante solo
> aparece en modo edición. Los enlaces se abren con **Ctrl+clic** (un
> clic normal sigue seleccionando y moviendo la nota); los `.bee`
> se abren en la app con la confirmación de cambios sin guardar. Las
> casillas se marcan con clic en modo edición. **Mayús+Intro** crea un
> párrafo nuevo (antes, un salto de línea) para que las listas
> funcionen; Tab/Mayús+Tab cambian la sangría en listas. El ancho fijo
> se cambia arrastrando el borde derecho en modo edición o con
> Texto → Ancho fijo. Al pegar desde fuera se sigue pegando texto plano
> como nota nueva (el HTML de navegadores trae estilos que chocan con el
> lienzo); dentro de una nota, Ctrl+V pega con formato y Ctrl+Mayús+V
> sin él. La exportación SVG sigue usando texto plano; la exportación
> a imagen conserva el formato. Los comentarios usan la misma barra.

`BeeTextItem` (`items.py:645`) hoy guarda `toPlainText()`.

| Feature | Esfuerzo | Implementación |
|---|---|---|
| Guardar HTML | S | `data.html` con `toHtml()` / `setHtml()`; si solo existe `data.text` (archivos antiguos), cargarlo como texto plano. `ChangeText` pasa a comparar HTML. |
| Barra de formato flotante en modo edición | L | Negrita, cursiva, subrayado, tachado, color de texto, fondo y resaltado, fuente y tamaño, alineación. Se aplica con `QTextCharFormat` y `QTextBlockFormat`. |
| Listas con viñetas, numeradas y **checklists** | M | `QTextListFormat`; para checklists, `QTextBlockFormat.setMarker(MarkerType.Checked/Unchecked)` y alternar el marcador con un clic. |
| Enlaces clicables | M | `setOpenExternalLinks` y manejo de `linkActivated`; si apuntan a un `.bee`, abrirlo. |
| Tamaño automático vs. ancho fijo con ajuste de línea | M | `setTextWidth(-1)` frente a un ancho fijo al redimensionar en modo edición. |
| Atajos de texto (Ctrl+B, I, U…) | S | Contexto `text_edit` de la tarea 0.6. |
| Copiar y pegar formato; formato en varias notas a la vez | M | Guardar un `QTextCharFormat` en memoria y aplicarlo a todo el documento de cada nota seleccionada. |
| Pegar sin formato, limpiar formato, indentación | S | |
| Crear una nota con una imagen seleccionada → emparentarla | S | Depende de la fase 4. |

**Entregable:** 0.8.0. Estimación: **L**.

---

## Fase 6 · Dibujo y anotación

| Feature | Esfuerzo | Implementación |
|---|---|---|
| Item de dibujo vectorial | L | Nuevo `BeeDrawingItem` que guarda en `data.shapes` una lista JSON de formas (`pen` con puntos, `rect`, `ellipse`, `line`, `arrow`), cada una con color, grosor y estilo (sólido, punteado o flecha). Se transforma como cualquier item. |
| Modo dibujo (Ctrl+Shift+D) con barra de herramientas | L | Nuevo `active_mode = 'draw'` en la escena; herramientas pen (D), rect (R), elipse (C), línea (L) y borrador (E). Shift para restringir a 45° o a cuadrado/círculo. Esc para salir. Mientras la herramienta siga activa, las formas van al mismo item. |
| Borrador | M | Borrado por trazo completo (elimina las formas que intersecan con el cursor); más sencillo y predecible que recortar trazos. |
| Editar un dibujo existente | S | Doble clic sobre el item o desde la jerarquía. |
| Suavizado del trazo a mano alzada | S | Simplificación tipo Ramer–Douglas–Peucker y curvas cuadráticas. |
| Exportación | S | Rasterizar en `SceneToPixmapExporter`; en `SceneToSVGExporter`, emitir `<path>` nativos. |

**Entregable:** 0.9.0. Estimación: **L–XL**.

---

## Fase 7 · Gestión avanzada de imágenes

| Feature | Esfuerzo | Implementación |
|---|---|---|
| Conservar los bytes originales | M | Hoy `pixmap_to_bytes()` re-codifica a PNG o JPG. Guardar el archivo original en `sqlar` cuando no haya recorte destructivo. Habilita "mantener formato original" al exportar y la reproducción de GIF. |
| **Imágenes enlazadas vs. incrustadas** | L | `data.source_path` y `data.linked`; si está enlazada, no se escribe blob en `sqlar` (la tarea 0.3 lo permite). Ajuste "Incrustar imágenes locales al guardar". |
| Re-enlazar imágenes perdidas | M | Mostrar un `BeeErrorItem` con la ruta; diálogo de reenlace por carpeta que busca por nombre de archivo. |
| Abrir origen (archivo o URL) | S | `data.source_url` al importar desde la web. |
| Reemplazar imagen | S | Conserva la transformación; comando con undo. |
| Diálogo "Gestionar imágenes" | L | Reducir la resolución por encima de un máximo, convertir formato (JPG, PNG, BMP o automático según el alfa), descartar los píxeles recortados y cambiar entre enlazar e incrustar, con vista previa de los afectados. Avisar de que es irreversible. |
| Auto-optimizar al importar | M | Reglas (ancho, alto, área, tamaño o formato) con acción reducir, convertir o preguntar; ajustes con un editor de reglas. |
| Importar todas las imágenes de una URL de página | M | `fileio/image.py` ya usa `lxml` para Pinterest: generalizar a todas las `<img>` y `srcset`, filtrar por tamaño mínimo y descargar en el hilo de `ThreadedIO`. |
| **Reproducción de GIF** | L | `BeeAnimatedItem` (o un modo de `BeePixmapItem`) con `QMovie` sobre `QBuffer`; barra de reproducción con play/pausa, deslizador de fotogramas, velocidad y avance por fotograma. Copiar el fotograma actual como imagen. |
| Recorte: pan y zoom dentro del recorte, bloqueo de proporción y cuadrado | M | Extender el modo de recorte en `items.py` (Shift para la proporción; arrastrar con V para mover el contenido). |
| Cuentagotas completo | M | Mostrar RGB, HSV y HEX con un botón para copiar cada uno; muestrear fuera de la ventana con `QScreen.grabWindow(0)` mientras el botón esté pulsado. |
| Info de imagen y coordenadas de píxel | S | Superposición con nombre, origen, tamaño y coordenada X,Y del píxel bajo el cursor. |
| Perfil de color de la pantalla | M | `QColorSpace` de la imagen convertido al de la pantalla; opcional y desactivado por defecto. |

**Entregable:** 0.10.0. Estimación: **XL**.

---

## Fase 8 · Foco y presentación

| Feature | Esfuerzo | Implementación |
|---|---|---|
| Enfocar la imagen siguiente o anterior (→ / ←) | S | `fit_rect` sobre `items_in_order()`. Puede adelantarse a la fase 1. |
| Slideshow (Alt+S) | M | `QTimer` más una barra inferior derecha (play/pausa, anterior, siguiente) que se desvanece. Orden: ordenado, barajado o aleatorio. Intervalo configurable. La navegación manual lo pausa. |
| Enfocar con Space | S | Hoy solo con doble clic. |

**Entregable:** se integra en la versión de la fase en curso. Estimación: **M**.

---

## Fase 9 · Modo overlay

| Feature | Esfuerzo | Implementación y riesgos |
|---|---|---|
| Overlay (Ctrl+Y) | XL | Al activarlo, crear una ventana `QWidget` sin marco por cada imagen seleccionada (o todas), con `WA_TranslucentBackground` y always on top, que pinte el pixmap con su transformación, recorte, opacidad y escala de grises. Ocultar la ventana principal. Cada ventana se puede mover y escalar, y con click-through combinado se puede calcar encima. Al salir, sincronizar posiciones y escalas de vuelta a los items (todo en un solo comando de undo). **Riesgo:** gestión de foco, de múltiples monitores y con DPI distintos. |

**Entregable:** 0.11.0. Estimación: **XL**.

---

## Fase 10 · Aplicación: guardado, temas, ventanas y comandos

| Feature | Esfuerzo | Implementación y riesgos |
|---|---|---|
| Autoguardado periódico | S | `QTimer` que llama a `do_save` si hay archivo y cambios. |
| Recuperación tras cierre inesperado | M | Volcar la escena sin guardar a un `.bee` temporal en la carpeta de ajustes; ofrecer recuperarla al arrancar. |
| Abrir la última escena al arrancar (Ctrl al iniciar para saltarlo) | S | |
| Comportamiento ante escenas sin guardar | S | Preguntar, descartar o guardar, más "recordar mi elección". Extiende `Save/confirm_close_unsaved`. |
| **Paleta de comandos (Ctrl+Shift+P)** | M | Diálogo con `QLineEdit` y una lista filtrada sobre `actions` (texto sin `&` y en el idioma activo) que ejecuta `qaction.trigger()`. También al teclear con el menú contextual abierto. |
| **Temas** (Oscuro, Claro, Glass y 4 personalizados) | L | Hoy los colores son constantes (`constants.COLORS`) aplicadas al iniciar. Pasarlos a un `ThemeManager` con señal de cambio que regenere la `QPalette` y repinte. Glass = lienzo transparente con `WA_TranslucentBackground`. Editor de 17 colores con alfa y "guardar como preset". Atajos Alt+1…7. |
| Opciones de bordes de imagen | S | Todos, solo seleccionados o ninguno. |
| Ajustes de transform gizmo | S | Visibilidad, tamaño de asas y desvanecer cuando no se usa. |
| **Varias ventanas** (Ctrl+Alt+Shift+N) | L | **Riesgo:** `actions` es un singleton de módulo y cada `Action` guarda un único `qaction`. Hay que refactorizar para que haya `QAction`s por ventana. |
| "Abrir archivos en…" (ventana nueva, actual o la que ya tenga la escena abierta) | M | Instancia única con `QLocalServer` / `QLocalSocket` para reenviar rutas. |
| Importar y exportar ajustes; modo portable | S | Copiar los `.ini`; si hay un `.ini` junto al ejecutable, usarlo. |
| Preset de atajos "estilo PureRef" | S | Un mapa alternativo de atajos aplicado desde el editor de atajos. |
| Rendimiento: caché en disco o en memoria | L | Opcional. Solo si se detectan problemas con escenas grandes; medir antes con perfiles. |

**Entregable:** 1.0.0. Estimación: **XL**.

---

## Fase 11 · Plataforma, automatización e idiomas

| Feature | Esfuerzo | Implementación |
|---|---|---|
| **CLI de automatización** | M | `-c "load;x.bee" -c "exportScene;out.png;1000;1000;false" -c exit` en `config/settings.py` (argparse con `action='append'`). Ejecución sin interfaz con `QT_QPA_PLATFORM=offscreen` y comandos: `load`, `save`, `exportScene`, `exportImages`, `clearScene`, `exit`. |
| Asociación de `.bee` y miniaturas en el Explorador (Windows) | L | Hoy se distribuye como un ejecutable PyInstaller de un solo archivo. Añadir un instalador (Inno Setup o NSIS, con instalación silenciosa `/S`) que registre la extensión. Las miniaturas requieren un *thumbnail handler* COM: guardar una miniatura PNG dentro del `.bee` y escribir el handler aparte (es lo más costoso; puede quedar para el final). |
| Gestos de trackpad (pellizcar y desplazar con dos dedos) | M | `QNativeGestureEvent` (zoom) y `QWheelEvent` con `pixelDelta` para el desplazamiento; ajuste para desactivarlos. |
| Pantallas táctiles | M | `QPinchGesture` y mantener pulsado para abrir el menú. |
| Más idiomas y traducción comunitaria | M | El sistema actual es un diccionario Python (`i18n/es.py`). Para Crowdin conviene migrar a gettext `.po` o Qt `.ts`, manteniendo la API `_()`. Después, añadir FR, JA, KO y ZH. |
| Comprobación de actualizaciones | S | Consultar la API de releases de GitHub; opcional y desactivada por defecto. |
| SpaceMouse 3D | L | Baja prioridad: requiere el SDK de 3Dconnexion. Recomiendo no hacerlo salvo que se necesite. |
| Analítica anónima | — | **Descartada**: no aporta al usuario de un proyecto GPL y añade obligaciones de privacidad. |

**Estimación:** **L–XL**.

---

## Dependencias entre fases

```
Fase 0 ──┬─> Fase 1 (victorias rápidas) ──> Fase 8 (foco y slideshow)
         ├─> Fase 2 (modos de ventana) ──> Fase 9 (overlay)
         ├─> Fase 3 (cuadrícula y snapping)
         └─> Fase 4 (grupos y jerarquía) ──┬─> Fase 5 (notas enriquecidas; comentarios usan su editor)
                                           ├─> Fase 6 (dibujo)
                                           └─> Fase 7 (imágenes; icono de enlazado en la jerarquía)
Fase 10 y Fase 11: en paralelo a partir de la Fase 2 (salvo multi-ventana, que conviene después de la Fase 4)
```

Se pueden trabajar en paralelo, sin tocar los mismos archivos: **Fase 3** (sobre todo `view.py` y `selection.py`), la **paleta de comandos** de la Fase 10 (un widget nuevo) y la **CLI** de la Fase 11 (`config/settings.py` y `__main__.py`).

## Resumen de esfuerzo

| Fase | Esfuerzo | Valor para el usuario | Riesgo técnico |
|---|---|---|---|
| 0 Preparación | M | Indirecto | Bajo |
| 1 Victorias rápidas | M–L | Alto | Bajo |
| 2 Modos de ventana | L–XL | **Muy alto** | Medio (depende del SO) |
| 3 Cuadrícula y snapping | M | Medio | Bajo |
| 4 Grupos y jerarquía | XL | Alto | **Alto** |
| 5 Notas enriquecidas | L | Medio | Bajo |
| 6 Dibujo | L–XL | Alto | Medio |
| 7 Imágenes | XL | Medio–alto | Medio |
| 8 Foco y slideshow | M | Medio | Bajo |
| 9 Overlay | XL | Alto para quien calca | Alto |
| 10 Aplicación | XL | Medio | Medio (multi-ventana) |
| 11 Plataforma | L–XL | Bajo–medio | Medio |

Total aproximado: **6–9 meses** para una persona a tiempo completo. Las fases 0–3 (unas 6–8 semanas) ya cubren la mayor parte de lo que se usa a diario en PureRef.

## Decisiones pendientes

1. **Atajos:** ¿mantener los de BeeRef y añadir un preset "PureRef", o adoptar directamente los de PureRef?
2. **Atajos globales:** ¿aceptar la dependencia `pynput` (portable) o implementarlos de forma nativa solo en Windows?
3. **Plataformas objetivo:** si solo importa Windows, las fases 2, 9 y 11 se simplifican mucho.
4. **Formato** (decidido en la fase 4: se mantiene `.bee` y el `APPLICATION_ID`, aceptando y documentando el riesgo)**:** BeeRef original **sí abre** un `.bee` v3 (`_migrate` acepta versiones mayores sin error), pero lo hace mal: carga solo imágenes y textos, coloca a los hijos en coordenadas locales (posición errónea) e ignora grupos y dibujos. Además, **al guardar borraría** esos items (`write_data` elimina todo lo que no esté en la escena). Opciones: cambiar `APPLICATION_ID` o la extensión (p. ej. `.myref`) para que BeeRef los rechace, o aceptar el riesgo y documentarlo.
