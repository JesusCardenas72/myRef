# Plan: features de imágenes del handbook de PureRef

Fuentes estudiadas (handbook 2.1):

- https://www.pureref.com/handbook/images/
- https://www.pureref.com/handbook/images/organize/
- https://www.pureref.com/handbook/shortcuts/all-shortcuts/

Leyenda: ✅ ya existía · 🆕 implementado en este plan · ⏭ fuera de alcance (motivo).

> **Estado: hecho.** Código en `myRef/image_tools.py` (editar, foco,
> presentación, origen, reemplazar, reenlazar, desbloquear),
> `myRef/drag_tools.py` (arrastres con modificadores y con tecla),
> `myRef/widgets/manage_images.py` y cambios en `scene.py`, `items.py`,
> `fileio/`. Tests en `tests/test_image_features.py`,
> `tests/test_drag_tools.py` y `tests/test_linked_images.py`.

## 1. Comparativa

### Añadir imágenes

| Feature PureRef | Atajo | Estado |
|---|---|---|
| Pegar imagen | Ctrl+V | ✅ |
| Pegar o soltar la URL de una página → importar todas sus imágenes | Ctrl+V / soltar | 🆕 (hoy solo funciona con la URL directa de una imagen) |
| Pegar archivos copiados en el explorador | Ctrl+V | 🆕 |
| Arrastrar y soltar | — | ✅ |
| Abrir imágenes | Ctrl+I | ✅ |
| Incrustar imágenes locales al guardar (ajuste) | — | 🆕 (imágenes enlazadas) |

### Selección y edición

| Feature | Atajo | Estado |
|---|---|---|
| Seleccionar, selección rectangular | Clic / arrastrar | ✅ |
| Añadir a la selección | Mayús+clic | 🆕 (hoy es Ctrl+clic, que pasa a rotar) |
| Selección continua (el rectángulo añade a la selección) | Mayús+arrastrar en vacío | 🆕 |
| Deselección continua | sin atajo | ⏭ PureRef no le da atajo por defecto |
| Seleccionar todo | Ctrl+A | ✅ |
| Editar item (nota o dibujo) | Intro | 🆕 |
| Duplicar | Ctrl+D | ✅ |
| Borrar | Supr | ✅ |
| Comentario | Alt+C | ✅ |
| Bloquear | Alt+L | ✅ |
| Botón de desbloqueo al pulsar un item bloqueado | clic | 🆕 |

### Transformar con ratón + teclas (sobre la imagen, sin usar el gizmo)

| Feature | Atajo | Estado |
|---|---|---|
| Rotar | Ctrl+arrastrar | 🆕 |
| Rotar con snap | Ctrl+Mayús+arrastrar | 🆕 |
| Snap del gizmo de rotación a 45° | Mayús en el gizmo | 🆕 (hoy 15°; ajuste con 45° por defecto) |
| Escalar | Ctrl+Alt+arrastrar (izq./der.) | 🆕 (choca con "mover ventana": pasa a botón derecho, como en PureRef) |
| Escalar desde el centro | Alt en el gizmo | 🆕 |
| Rotar/escalar cada imagen sobre su centro | Mayús+Alt en el gizmo | ✅ |
| Opacidad | Ctrl+Alt+Mayús+arrastrar (izq./der.) | 🆕 |
| Voltear en la dirección del arrastre | Alt+Mayús+arrastrar | 🆕 |
| Voltear horizontal / vertical | Alt+Mayús+H / Alt+Mayús+V | ✅ |
| Mover con snap a ejes | Mayús+arrastrar | ✅ |
| Mover con snap a vecinos | Mayús+Espacio | ✅ (como interruptor) |
| Restablecer transformación | Ctrl+Mayús+T | ✅ |
| Mover ventana | botón derecho + arrastrar | 🆕 |

### Recorte

| Feature | Atajo | Estado |
|---|---|---|
| Recortar con el gizmo | Ctrl+Alt+Mayús+C | ✅ |
| Mantener proporción / cuadrado en el gizmo | Mayús / Mayús+Alt | 🆕 |
| Recortar la selección dibujando un rectángulo | C+arrastrar | 🆕 |
| Desplazar la imagen dentro del recorte | V+arrastrar | 🆕 |
| Zoom dentro del recorte | Mayús+V+arrastrar | 🆕 |
| Restablecer recorte | Ctrl+Mayús+C | ✅ |

### Ver e inspeccionar

| Feature | Atajo | Estado |
|---|---|---|
| Enfocar selección / volver | Espacio, doble clic | ✅ |
| Enfocar imagen siguiente / anterior (orden de jerarquía) | → / ← | 🆕 |
| Enfocar lienzo | Ctrl+Espacio | ✅ |
| Presentación (slideshow) de la selección, 10 s por defecto | Alt+S | 🆕 |
| Zoom arrastrando | Z+arrastrar | 🆕 |
| Mostrar código de color | S+arrastrar | 🆕 |
| Mostrar coordenadas de la imagen | D+arrastrar | 🆕 |
| Escala de grises | Alt+G | ✅ |
| Lienzo en escala de grises | Ctrl+Alt+G | ✅ |
| Muestreo bilineal / vecino más próximo | Alt+T | ✅ |
| Muestreo por defecto de las imágenes nuevas (ajuste) | — | 🆕 |

### Origen

| Feature | Atajo | Estado |
|---|---|---|
| Abrir origen (archivo o URL) | Ctrl+Mayús+O | 🆕 |
| Reemplazar imagen | sin atajo | 🆕 |
| Re-enlazar imágenes perdidas | Ctrl+Alt+Mayús+R (o doble clic) | 🆕 |
| Gestionar imágenes (reducir, convertir formato, descartar recorte, incrustar/enlazar) | Ctrl+Mayús+J | 🆕 |

### Organizar (subpágina "Arrange & align")

| Feature | Atajo | Estado |
|---|---|---|
| Traer al frente / enviar al fondo | ↑ / ↓ | ✅ |
| Organizar óptimo | Ctrl+P | ✅ |
| Organizar por nombre (nombre del item; si no, nombre de archivo) | Ctrl+Alt+N | 🆕 (hoy Ctrl+Alt+N ordena por ruta) |
| Organizar por ruta | Ctrl+Alt+D | 🆕 (atajo) |
| Organizar por orden de jerarquía | Ctrl+Alt+O | 🆕 |
| Organizar por adición / aleatorio | Ctrl+Alt+A / Ctrl+Alt+R | ✅ |
| Repetir un "organizar por" invierte el orden | — | 🆕 |
| Alinear, distribuir, apilar | Ctrl+flechas, Ctrl+Alt+Mayús+↑/↓, Ctrl+Alt+S | ✅ |
| Normalizar alto / ancho / escala | Ctrl+Alt+← / → / ↓ | ✅ |
| Normalizar tamaño (= lado más largo en PureRef) | Ctrl+Alt+↑ | 🆕 (hoy Ctrl+Alt+↑ iguala el área) |
| Normalizar área | sin atajo | ✅ (se renombra "Área") |
| Origen de la normalización: primero o promedio | — | ✅ |

### Fuera de alcance de este plan

- **Overlay** (Ctrl+Y), **paleta de comandos** (Ctrl+Mayús+P) y **presets de tema** (Alt+1…7): no son de la página de imágenes; siguen en las fases 9 y 10 de `PLAN_PUREREF.md`.
- **Reducción de resolución no destructiva** (solo para rendimiento): myRef no tiene caché de imágenes reducidas; se implementa solo la reducción permanente.
- **Auto-optimizar al importar** con reglas: queda para la fase 7.

## 2. Decisiones

- **Ctrl+clic deja de alternar la selección**: en PureRef Ctrl+arrastrar rota. Añadir/quitar de la selección pasa a Mayús+clic. Ctrl+clic sobre un enlace de una nota sigue abriéndolo.
- **Mover ventana** pasa de Ctrl+Alt+arrastrar a **arrastrar con el botón derecho** (un clic derecho sin arrastrar sigue abriendo el menú). Ctrl+Alt+arrastrar queda para escalar.
- Los arrastres con modificadores (rotar, escalar, opacidad, voltear) son **controles de ratón configurables** en Ajustes → Teclado y ratón. Los arrastres con tecla mantenida (C, V, Mayús+V, Z, S, D) son fijos.
- **Imágenes enlazadas**: con el ajuste "Incrustar imágenes locales" desactivado, las imágenes abiertas desde disco guardan solo la ruta (`data.linked`). Si al abrir la escena falta el archivo, se muestra un aviso en su lugar; doble clic o Ctrl+Alt+Mayús+R para re-enlazar.
- **Gestionar imágenes** es destructivo pero se puede deshacer (el comando guarda el pixmap anterior). Al guardar se reescriben los datos de las imágenes modificadas.
