# Arquitectura de MelfPaint

MelfPaint sigue la misma idea usada en el proyecto de Biblioteca Comunitaria: el archivo `main.py` solamente crea las dependencias y pone a funcionar el programa.

La aplicación de escritorio está separada en dos partes:

```text
MelfPaint/
├── backend/
│   ├── Model/
│   ├── Repository/
│   ├── Service/
│   └── Controller/
├── frontend/
│   ├── Config/
│   ├── Resources/
│   └── View/
└── main.py
```

## Backend

- `Model`: representa documentos, capas, selecciones, formato de texto y configuración de herramientas.
- `Repository`: abre y guarda imágenes o proyectos editables. No contiene decisiones de interfaz.
- `Service`: aplica transformaciones, historial, dibujo, impresión, configuración y recuperación.
- `Controller`: recibe una acción de la interfaz, valida el flujo y llama al servicio correspondiente.

## Frontend

La carpeta `View` está dividida por lo que muestra cada módulo:

- `Main`: ventana principal y composición visual.
- `Canvas`: lienzo, regla, cuadrícula, zoom y selección.
- `Ribbon`: barra de herramientas y sus grupos.
- `Panels`: capas, texto y barra de estado.
- `Dialogs`: nuevo documento, tamaño, propiedades, colores y acerca de.
- `Components`: botones, muestras de color y figuras reutilizables.


## Herramientas con estado editable

Las formas no se pintan en la capa al soltar el ratón. `ShapeTool` las guarda
como puntos y genera una vista previa; mientras están pendientes se pueden
mover, redimensionar y cambiar de estilo. `ToolController.commit_pending()` las
fija en la capa (y crea la entrada del historial) al hacer clic fuera, cambiar
de herramienta, guardar, imprimir o deshacer.

Los trazos a mano alzada (`_StrokeTool`) se dibujan opacos en un búfer propio y
se mezclan con la capa original usando la opacidad elegida, para que un trazo
semitransparente no se oscurezca donde se superpone consigo mismo.

## Empaquetado

`Makefile` define una única instalación (`make install DESTDIR=… PREFIX=/usr`)
que reutilizan el `PKGBUILD` de Arch, el `.spec` de RPM y el constructor de
`.deb` en `packaging/build-packages.sh`. La versión se lee de `app/version.py`.
