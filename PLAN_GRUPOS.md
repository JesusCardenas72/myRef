# Plan: grupos con recuadro, título, borde configurable y operaciones internas

Base: la fase 4 de `PLAN_PUREREF.md` ya entregó grupos (`BeeGroupItem`), jerarquía y arrastrar a grupos. Este plan **extiende** esa base; no hay que rehacerla.

Escala de esfuerzo (la de `PLAN_PUREREF.md`): **S** ≤ 1 día · **M** 2–5 días · **L** 1–2 semanas.

---

## 1. Qué ya existe

| Pieza | Dónde |
|---|---|
| `BeeGroupItem`: fondo con color y alfa, cerrado/abierto (clic en un hijo selecciona el grupo; doble clic lo abre) | `myRef/items.py:1200` |
| El rectángulo se ajusta a los hijos con un margen de 10 px; se recalcula en cada cambio de la escena, de dentro afuera | `items.py:1246` (`fit_to_children`), `scene.py:185` y `scene.py:1079` |
| Agrupar y desagrupar (con undo), borrado automático de grupos vacíos | `commands.py:556` (`GroupItems`), `commands.py:600` (`UngroupItems`), `commands.py:33` |
| Arrastrar items dentro o fuera de un grupo (ajuste `Items/drag_into_groups`) | `scene.py:341` (`drop_target_group`), `scene.py:359` (`items_to_drop`) |
| Cambiar de padre conservando la transformación; orden de la jerarquía; panel de jerarquía | `commands.py:521` (`ChangeHierarchy`), `hierarchy.py`, `widgets/hierarchy.py` |
| Nombre editable (F2 o panel), color de fondo | `commands.py:669`, `commands.py:684`, `view.py:560` |
| Guardado en `.bee` v3: `parent_id`, `sort_order` y `data.color` | `fileio/sql.py:222` |
| Acciones en el menú «Elementos» | `actions/menu_structure.py:113` |

## 2. Requisito → estado → trabajo

| # | Petición | Estado | Falta |
|---|---|---|---|
| 1 | Recuadro alrededor de varias imágenes | Hecho (fondo) | Dibujar el **borde** |
| 2 | Texto arriba a la derecha, editable | Parcial | El nombre existe pero **no se dibuja**. Dibujarlo, editarlo con doble clic |
| 3 | Añadir arrastrando | Hecho | Acción explícita «Añadir al grupo» y pruebas con subgrupos |
| 4 | Sacar imágenes con «desagrupar» | Parcial | Hoy «Desagrupar» disuelve **todo** el grupo. Falta «Quitar del grupo» |
| 5 | Menú «Grupo» | Falta | Las acciones viven en «Elementos» |
| 6 | Alinear, optimizar… dentro del grupo | Falta | Las acciones actúan sobre la selección o sobre los items de nivel superior |
| 7 | Subgrupos | Estructura hecha | Casos borde, pruebas y documentarlo |
| 8 | Color de fondo | Hecho | Integrarlo en el diálogo de estilo |
| 9 | El grupo crece y encoge, siempre rectángulo | Hecho | Pruebas con anidamiento y medir rendimiento |
| 10 | Línea: anchura, punteados, ondulaciones, color | Falta | Todo |
| 11 | Opacidad de todo el grupo | Falta | Qt ya multiplica la opacidad del padre en los hijos. Falta la acción, guardarla y copiarla |

## 3. Decisiones de diseño

1. **Título = `item.name`** (el campo que ya guarda F2 y muestra el panel de jerarquía). Sin campo nuevo. Se dibuja **dentro del recuadro, en la esquina superior derecha**, dentro de la banda del margen (ver decisión 3). Si es más ancho que el grupo, se recorta con «…» (el tooltip lo muestra entero). Tamaño de fuente en unidades de escena, configurable.
2. **Forma y trazo son dos propiedades**: `border_shape` (recto, zigzag, onda, festón, almenado) y `border_style` (continuo, guiones, puntos, guion-punto, guion-punto-punto). Cualquier combinación es válida y el diálogo necesita solo dos desplegables. **Grosor del borde y tamaño del título en unidades de escena**, no en píxeles de pantalla: escalan con el zoom como las imágenes y se exportan tal cual se ven (la línea discontinua del estado «abierto» sigue siendo cosmética, como hoy).
3. **Todo se dibuja dentro del rectángulo lógico.** El área de exportación es `itemsBoundingRect` (`export.py:105`), construida desde `bounding_rect_unselected()`: cualquier decoración fuera de él **se recortaría en PNG, JPG y SVG**. Por eso el borde se dibuja remetido media anchura, la onda oscila hacia dentro desde la línea base y el título va dentro de la esquina. Para que el contenido nunca quede bajo el borde o el título, el margen del grupo (hoy `PADDING = 10` fijo) pasa a ser `PADDING + amplitud + grosor` (+ la altura del título en el lado superior). Ventajas: `boundingRect()` y `shape()` no necesitan sobrescribirse, no hay restos de repintado y la exportación sale correcta sin tocar los exportadores.
4. **Operaciones internas por alcance explícito, no implícito.** Los métodos de `scene.py` aceptan `items=None`. Las acciones del menú «Grupo» pasan los hijos directos del grupo. No se cambia el significado de las acciones actuales, que con un grupo seleccionado siguen organizando grupos entre sí.
5. **Los subgrupos se tratan como una unidad** al organizar el contenido (como Figma). Incluir el contenido de los subgrupos no entra en la primera versión.
6. **Opacidad** = `setOpacity` del grupo. Afecta a fondo, borde, título e hijos, y se multiplica con la opacidad propia de cada imagen. El alfa del color de fondo es independiente.
7. **Formato**: todo va en `items.data` (JSON), sin migrar. Un `.bee` anterior se abre igual. Solo se escriben los valores distintos del predeterminado, como hoy con `color`.

## 4. Fases

Orden recomendado: G1 → G2 → G3 → G4 → G5 → G6. Tras G2 ya hay algo utilizable de punta a punta. G3 y G4 son independientes, pero tocan `scene.py`, `view.py` y `actions.py`, así que van seguidas, no en paralelo.

### G1 · Aspecto básico: borde, título y opacidad (M) — hecha

> Línea base (`tests/perf_groups.py`, 500 imágenes, 20 grupos, offscreen): `fit_groups` 0,36 ms y render 8,0 ms antes; 0,38 ms y 12,6 ms con borde y título.

- Módulo nuevo `myRef/group_style.py`, puro y probable sin interfaz: valores predeterminados, tabla `border_style → patrón de guiones`, validación de lo que viene del `.bee`.
- `BeeGroupItem` gana `border_color`, `border_width`, `border_style`, `title_size` y `title_color`. `get_extra_save_data` y `create_from_data` los leen y escriben, y `opacity` también.
- **`create_copy` hoy solo copia el color.** Debe copiar todo el estilo y la opacidad, o duplicar y pegar pierde el aspecto.
- `paint`: fondo → borde → título. El estado «abierto» sigue con su línea discontinua de selección, ahora distinguible del borde del usuario.
- Comando `ChangeGroupStyle(groups, **props)` con undo (`ChangeGroupColor` pasa a ser un caso particular).
- Opacidad: **`ChangeOpacity` no sirve tal cual** — filtra `item.is_image` (`commands.py:466`) y un grupo tiene `is_image = False`, así que el comando quedaría vacío. Generalizarlo: quitar el filtro del comando y moverlo al callback de imágenes (`view.py:530`). De paso se arregla un bug latente: `old_opacities` se construye sobre la lista **sin filtrar** (`commands.py:468`), con lo que el `zip` del `undo` desalinea items y valores con listas mixtas.
- Como el margen depende ahora del estilo (decisión 3), cambiar grosor o amplitud reencaja el grupo: pasa por `prepareGeometryChange` (ya lo hace `fit_to_children`).
- Línea base de rendimiento: medir `fit_groups` + pintado con ~500 imágenes y 20 grupos **antes** de añadir el pintado nuevo, para comparar en G5.
- Pruebas: ida y vuelta por SQLite (`tests/fileio`), copia, undo, que título y borde queden dentro de `itemsBoundingRect`.

### G2 · Menú «Grupo», diálogo de estilo y quitar/añadir (M) — hecha

> Cambios respecto a lo previsto: `group_toggle_open` y `select_group_contents` se sustituyen por `group_enter` («Entrar en el grupo», selecciona sus hijos) y `group_exit` («Salir del grupo», selecciona el grupo que los contiene). La opacidad forma parte de `ChangeGroupStyle`, así el diálogo de estilo es un solo paso de deshacer. El menú en inglés es «G&roup» porque «&Group» ya es el texto de la acción Agrupar (las traducciones van por texto). La pista emergente con el título completo no se ha hecho.

- Menú de primer nivel `&Group` («&Grupo») entre «Elementos» y «Texto». Se mueven `group_items`, `ungroup_items` y `group_color`; **los ids no cambian**, así que los atajos personalizados se conservan. «Elementos» se queda con parentar, bloquear, comentar y renombrar.
- Acciones nuevas (`actions.py`, callbacks en `view.py`):
  - `add_to_group`: con un grupo y otros items seleccionados, mete los items en el grupo (sin depender del orden de selección, a diferencia de `P`).
  - `remove_from_group`: saca los items seleccionados al padre del grupo, o al nivel superior si no hay otro grupo encima. Se apoya en `scene.move_in_hierarchy`, que ya conserva la transformación, borra grupos vacíos y reencaja.
  - `group_title`, `group_style`, `group_opacity`, `group_toggle_open` («Editar contenido»), `select_group_contents`.
  - «Desagrupar» **conserva su semántica actual** (disuelve el grupo entero): «Quitar del grupo» ya cubre el otro caso, y una versión «inteligente» sería ambigua con selecciones mixtas (un grupo más hijos de otro) y rompería tests de `test_groups.py`.
- Grupo de acciones nuevo `active_when_group`, activado desde `on_selection_changed` (`view.py:1411`) con `scene.target_group()`: el grupo seleccionado o, si hay varios items hijos del mismo grupo, ese grupo.
- `GroupStyleDialog`: color de fondo con alfa, color, anchura, trazo y forma del borde, tamaño y color del título, opacidad. Vista previa en vivo y un único paso de deshacer, con el patrón de `ChangeOpacityDialog` (`widgets/__init__.py:205`). Se aplica a todos los grupos seleccionados.
- Doble clic sobre el título: renombrar. Hoy el doble clic abre el grupo (`scene.py:872`), así que el título tiene prioridad solo en su zona.
- `group_selection` hoy descarta en silencio los items con otro padre (`scene.py:260`): mostrar un `BeeNotification`.
- i18n: `test_translation_exists_for_all_strings`, `test_no_unused_translations` y `test_mnemonics_unique_within_each_menu` exigen traducir todo, no dejar sobrantes y mnemónicos únicos por menú.

### G3 · Operaciones dentro del grupo (M) — hecha

> Las acciones `group_*` reutilizan el texto de la global; el editor de atajos las distingue por la ruta del menú («Grupo > Organizar contenido: …»), así que no hizo falta prefijo. Con varios grupos seleccionados se organiza cada uno por separado en un solo paso de deshacer. `ArrangeItems` y `NormalizeItems` reencajan los grupos al momento (antes esperaban a `scene.changed`). Se aplicaron las opciones recomendadas de las decisiones pendientes 1 y 3: «Optimizar» = «Organizar → Óptimo» y alcance = hijos directos.

- `scene.group_contents(group)` = hijos directos. `items_for_action(items=None)` y los métodos `align`, `distribute`, `stack`, `arrange*` y `normalize*` aceptan `items=None`. Sin cambios de comportamiento por defecto.
- Tabla `SCOPED_ACTIONS` en `actions.py` que genera las acciones `group_*` y sus callbacks en un bucle en `view.py` (`partial(método, items=contenido)`), para no duplicar 20 acciones a mano:
  - Organizar: óptimo, horizontal, vertical, cuadrado, cuadrado por adición, cuadrado aleatorio.
  - Alinear ×4, distribuir ×2, apilar.
  - Normalizar: alto, ancho, tamaño, lado largo, escala.
- Dos submenús dentro de «Grupo»: «Organizar contenido» y «Normalizar contenido». Más `group_focus` (encuadrar el grupo, equivalente a «Enfocar lienzo»).
- Sin atajos por defecto en estas acciones, para no chocar con los actuales. Reutilizan los textos existentes, así que las traducciones ya están.
- Las ~20 acciones nuevas aparecen en el editor de atajos y en la futura paleta de comandos: darles textos con prefijo claro («Grupo: organizar óptimo…») para que se distingan de las globales.
- Cada acción es un solo paso de deshacer. `ArrangeItems` ya usa `hierarchy.set_scene_pos`, y el grupo se reencaja solo por `scene.changed`. El contenido conserva su centro.
- Límite conocido: en un grupo rotado, alinear y distribuir usan los ejes de la escena, igual que con imágenes rotadas.
- Pruebas: lo de fuera del grupo no se mueve; el grupo sigue conteniendo todo; deshacer lo restaura; funciona dentro de un subgrupo.

### G4 · Bordes ondulados (M) — hecha

> Las formas se definen como perfiles de un periodo (puntos `(t, f)`) y se dibujan como polilínea (16 puntos por periodo en onda y festón), así el mismo camino sirve para pintar y para el `d` del SVG. Con borde ondulado el fondo se rellena solo por dentro de la onda. En SVG, cada elemento lleva `effectiveOpacity()` (los elementos no se anidan como los items). Medición con 20 grupos de onda y guiones: render 28,7 ms frente a 13,6 ms con borde recto; `fit_groups` sin cambios.

- En `group_style.py`: `border_path(rect, shape, amplitude, wavelength) → QPainterPath` para zigzag, onda (Bézier cuadrática), festón (arcos) y almenado.
- Regla para que las esquinas cierren: cada lado tiene `max(1, round(largo / longitud_de_onda))` periodos enteros y la longitud se ajusta a eso. El trazo arranca y termina sobre la línea base en cada esquina.
- Caché del último camino por (ancho, alto, forma, amplitud, longitud). Se invalida al cambiar el estilo o el rectángulo.
- Uniones redondeadas para ondas; el patrón de guiones se aplica por encima de cualquier forma.
- Amplitud y longitud de onda entran en el diálogo (desactivadas con forma recta). La onda oscila **hacia dentro** desde la línea base (decisión 3): la amplitud no amplía ningún rectángulo, sino que engorda el margen interior del grupo.
- Exportación: con todo el dibujo dentro del rectángulo lógico (decisión 3), PNG y JPG incluyen borde, ondas y título sin tocar los exportadores; añadir una prueba que lo verifique (el área de exportación es `itemsBoundingRect`, `export.py:105`). `fileio/export.py` **no exporta grupos a SVG** hoy (solo imagen, texto y dibujo, `export.py:292-318`): añadir un `<path>` con `stroke-dasharray` y la opacidad del grupo.
- Pruebas: camino cerrado, continuidad en las esquinas, extremos dentro de la amplitud, caché.

### G5 · Subgrupos y robustez (S–M) — hecha

> Destino al soltar: el grupo más interior bajo el cursor, salvo que esté dentro de un grupo cerrado; entonces el grupo cerrado más exterior (`effective_item`, igual que los clics). Pruebas de tres niveles en `tests/test_subgroups.py`. Rendimiento (25 grupos en tres niveles): `fit_groups` 0,44 ms y render 17,4 ms, muy por debajo del umbral de 10 ms por cambio, así que no hizo falta reencajar solo los ancestros.

- «Subgrupo» no necesita acción nueva: `group_items` con un grupo abierto y varios items hijos suyos crea uno. Se documenta, y el panel de jerarquía ya muestra la sangría.
- `drop_target_group` devuelve el grupo más profundo bajo el cursor (los hijos se apilan sobre el padre). Decidir y probar: si el grupo exterior está cerrado, ¿el destino es él o el subgrupo? Propuesta: el exterior.
- Sacar un item de un subgrupo al soltarlo fuera: destino correcto (grupo exterior o nivel superior).
- Copiar, pegar y duplicar grupos anidados conservan estilo (`copy_with_children`, `items.py:201`).
- `close_unused_groups` y `select_items` con tres niveles.
- **Rendimiento:** `fit_groups` corre en cada `scene.changed` y cuesta O(grupos × hijos). Repetir la medición de la línea base de G1 con el pintado nuevo y anidamiento; si pasa de ~10 ms por cambio, reencajar solo los ancestros de lo que cambió.

### G6 · Cierre (S) — hecha

> `controls.html` / `controls.es.html` separan «Grupos (menú Grupo)» de «Jerarquía (menú Elementos)»; CHANGELOG y nota en `PLAN_PUREREF.md` actualizados; `flake8 .` (7.0.0) limpio. `tests/render_groups_sample.py` pinta una escena de ejemplo a PNG para revisar el aspecto. Pendiente: la comprobación manual interactiva de abajo (menús, diálogo, arrastrar, doble clic) en la aplicación real.

- `controls.html` y `controls.es.html`, `CHANGELOG.rst`, nota en `PLAN_PUREREF.md` (fase 4).
- `flake8` limpio, `pytest` completo en verde y lista de comprobación manual (abajo).

**Total:** unas 2–3 semanas a tiempo parcial.

## 5. Comprobación manual al final

1. Agrupar 4 imágenes: aparece el recuadro con título arriba a la derecha.
2. Doble clic en el título, cambiarlo, deshacer y rehacer.
3. Arrastrar una quinta imagen dentro: el recuadro crece. Arrastrar otra fuera: encoge.
4. «Quitar del grupo» y «Desagrupar» con un hijo seleccionado.
5. Crear un subgrupo dentro de un grupo abierto; mover una imagen del subgrupo y ver crecer los dos recuadros.
6. «Organizar contenido → Óptimo» en el grupo exterior: el subgrupo se mueve como una pieza.
7. Cambiar color, anchura, trazo y forma del borde; guardar, cerrar y reabrir.
8. Opacidad al 50 %: se atenúa todo, subgrupos incluidos.
9. Duplicar el grupo (Ctrl+D) y exportar a PNG y a SVG.

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| Amplitudes o grosores grandes se comen el espacio interior | El margen crece con amplitud, grosor y título (decisión 3); limitar los rangos en el diálogo |
| Un grupo grande y transparente captura los clics que antes iban al rubberband | `shape()` recto; opción futura de «transparente al clic» si molesta |
| Título ilegible al alejar el zoom | Fuente en unidades de escena (escala con el grupo). Si molesta, tamaño mínimo en pantalla |
| Título al revés en un grupo girado 180° | Igual que cualquier item; aceptado |
| Opacidad del grupo × opacidad de cada imagen | Documentarlo; es el comportamiento natural de Qt |
| BeeRef original pierde estos datos al guardar | Ya aceptado y documentado en la decisión 4 de `PLAN_PUREREF.md` |
| El árbol de trabajo tiene el renombrado `beeref → myRef` sin confirmar | Confirmarlo antes de crear ramas `grupos-N` |

## 7. Decisiones pendientes

> Resueltas tras el análisis: la posición del título (dentro del recuadro, esquina superior derecha, decisión 1 — fuera del rectángulo lógico se recortaría al exportar) y las unidades del grosor del borde (unidades de escena, decisión 2).

1. **«Optimizar»:** se interpretó como «Organizar → Óptimo» dentro del grupo, más «Enfocar grupo». Si pensabas en otra cosa, dilo antes de G3.
2. **Formas de onda:** zigzag, onda, festón y almenado. ¿Quieres otras (por ejemplo nube)?
3. **Alcance de las operaciones internas:** hijos directos con los subgrupos como piezas (recomendado) o también el contenido de los subgrupos.
4. **Estilo por defecto de los grupos nuevos:** el actual, o recordar el último usado.
