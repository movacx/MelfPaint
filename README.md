# MelfPaint

MelfPaint is a simple desktop image editor for Linux with a ribbon toolbar, layers, brushes and editable shapes.

## Features

**Menu bar**

- **File:** New, Open, Import to canvas (from a file), Recent images, Save, Save as (PNG, JPEG, BMP, GIF, other formats and layered project), Print (print, page setup, preview), Set as desktop background (fill, tile, center), Image properties, About and Quit.
- **Edit:** Undo, Redo, Cut, Copy, Paste, Paste from, Select all, Invert selection, Delete, Image, Layers and Effects submenus, and Edit colors.
- **View:** Zoom (in, out, 100 %, fit to window), Show (rulers, gridlines, status bar), Layers, hide the ribbon, full screen, theme and settings.

**Ribbon**

- **Clipboard:** paste (and paste from a file), cut and copy.
- **Image:** select (rectangle or free-form, select all, invert selection, delete and transparent selection), crop, resize and skew, rotate 90°/180°/any angle and flip. A selection can be moved (even outside the canvas), resized with its handles and duplicated with Ctrl+drag.
- **Tools:** pencil, fill with tolerance, text (font, size, bold, italic, underline, strikethrough, alignment and background), eraser (right click replaces color 1 with color 2), color picker (goes back to the previous tool) and magnifier (click to zoom in, right click to zoom out).
- **Brushes:** brush, calligraphy brush, calligraphy pen, airbrush, oil brush, crayon, marker, natural pencil and watercolor brush.
- **Shapes:** the 23 available shapes (line, two-bend curve, oval, rectangle, rounded rectangle, polygon, triangles, diamond, pentagon, hexagon, arrows, stars, callouts, heart and lightning bolt). A shape stays editable: you can move it, resize it and change its color, thickness, outline and fill until you click outside it. Outline and fill support solid color, crayon, marker, oil, natural pencil and watercolor. Shift draws squares, circles and lines at 45°.
- **Size:** thickness of 1, 3, 5 and 8 px (Ctrl++ and Ctrl+- to adjust further).
- **Colors:** color 1 and color 2, a 20-color palette, 10 custom colors that are remembered, and "Edit colors".

**Other**

- Layers (View › Layers or F7, or the Layers button on the ribbon) with name, visibility, opacity, order, duplicate, merge, flatten image, lock and blend modes (multiply, screen, overlay, darken and lighten).
- Side sliders for free thickness (1 to 256 px) and opacity. With the fill tool they control tolerance. Pencil and brush strokes are smoothed.
- Resize the canvas by dragging its handles, with a live preview.
- Rulers, gridlines, zoom from 10 % to 800 %, Ctrl+wheel to zoom at the cursor, and a status bar showing pointer position, selection size and canvas size.
- Light, dark or system theme.
- Image properties with units (inches, centimeters, pixels), resolution and black and white conversion.
- Editable `.melfpaint` projects with layers, atomic saving and automatic recovery after an unexpected close.

## Requirements

- Python 3.11 or newer.
- PySide6 6.5 or newer.
- NumPy.

## Structure

```text
MelfPaint/
├── app/
│   ├── backend/
│   ├── frontend/
│   ├── tests/
│   ├── main.py
│   └── version.py
├── scripts/
├── docs/
└── Makefile
```
