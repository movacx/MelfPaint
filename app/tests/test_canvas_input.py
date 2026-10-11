from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import APP, MESSAGES, pixel  # noqa: F401

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtTest import QTest

import main
from backend.Service.recovery_service import RecoveryService
from backend.Service.settings_service import SettingsService


class CanvasInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.carpeta = tempfile.TemporaryDirectory()
        base = Path(self.carpeta.name)
        self.c = main.crear_controlador(
            SettingsService(base / "settings.json"),
            RecoveryService(recovery_directory=base / "recovery"),
            autosave_interval_ms=0,
        )
        self.c.start([])
        self.c.new_document({"width": 400, "height": 300})
        self.canvas = self.c.window.canvas
        self.canvas.resize(self.canvas.sizeHint())

    def tearDown(self) -> None:
        self.c.document.modified = False
        self.c.tool_controller.discard_pending_shape()
        self.c.window.hide()
        self.carpeta.cleanup()

    def _pantalla(self, x: float, y: float) -> QPoint:
        return self.canvas.document_to_screen(QPointF(x, y)).toPoint()

    def _arrastrar(self, a, b, boton=Qt.MouseButton.LeftButton, modificadores=Qt.KeyboardModifier.NoModifier) -> None:
        inicio, fin = self._pantalla(*a), self._pantalla(*b)
        QTest.mousePress(self.canvas, boton, modificadores, inicio)
        for paso in range(1, 6):
            punto = inicio + (fin - inicio) * paso / 5
            evento = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(punto), QPointF(self.canvas.mapToGlobal(punto)), Qt.MouseButton.NoButton, boton, modificadores)
            APP.sendEvent(self.canvas, evento)
        QTest.mouseRelease(self.canvas, boton, modificadores, fin)

    def test_pencil_with_mouse(self) -> None:
        self.c.select_tool("pencil")
        self._arrastrar((20, 20), (200, 20))
        self.assertEqual(pixel(self.c.document, 100, 20).alpha(), 255)
        self.assertTrue(self.c.history.can_undo())

    def test_right_button_uses_color_2(self) -> None:
        self.c.set_secondary_color(QColor("red"))
        self.c.select_tool("pencil")
        self._arrastrar((20, 50), (200, 50), Qt.MouseButton.RightButton)
        self.assertEqual(pixel(self.c.document, 100, 50), QColor("red"))

    def test_shape_then_click_outside_commits(self) -> None:
        self.c.select_shape("rectangle")
        self._arrastrar((50, 50), (150, 120))
        self.assertTrue(self.c.tool_controller.has_pending_shape())
        self._arrastrar((300, 250), (301, 251))
        self.assertFalse(self.c.tool_controller.has_pending_shape())
        self.assertGreater(pixel(self.c.document, 50, 80).alpha(), 0)

    def test_selection_drag_moves_pixels(self) -> None:
        self.c.document.active_layer.image.fill(QColor(0, 0, 0, 0))
        for x in range(10, 40):
            for y in range(10, 40):
                self.c.document.active_layer.image.setPixelColor(x, y, QColor("blue"))
        self.c.select_tool("select")
        self._arrastrar((10, 10), (40, 40))
        self.assertTrue(self.c.selection_controller.has_selection())
        self._arrastrar((25, 25), (125, 25))
        self.c.confirm_pending_edits()
        self.assertEqual(pixel(self.c.document, 120, 20), QColor("blue"))
        self.assertEqual(pixel(self.c.document, 20, 20).alpha(), 0)

    def test_right_click_with_select_tool_opens_menu_without_drawing(self) -> None:
        abiertos: list[QPoint] = []
        self.canvas.menuContextualSolicitado.connect(abiertos.append)
        self.c.select_tool("select")
        QTest.mouseClick(self.canvas, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, self._pantalla(30, 30))
        self.assertEqual(len(abiertos), 1)
        self.assertFalse(self.c.history.can_undo())

    def test_fill_and_eyedropper(self) -> None:
        self.c.set_primary_color(QColor("#22b14c"))
        self.c.select_tool("fill")
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self._pantalla(5, 5))
        self.assertEqual(pixel(self.c.document, 300, 200), QColor("#22b14c"))
        self.c.set_primary_color(QColor("black"))
        self.c.select_tool("eyedropper")
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self._pantalla(5, 5))
        self.assertEqual(self.c.document.tool_settings.primary_color, QColor("#22b14c"))
        self.assertEqual(self.c.tool_controller.active_tool_id, "fill")

    def test_size_is_remembered_per_tool(self) -> None:
        self.c.select_tool("pencil")
        self.c.set_tool_size(4)
        self.c.select_tool("eraser")
        self.assertEqual(self.c.document.tool_settings.brush_size, 8)
        self.c.select_tool("pencil")
        self.assertEqual(self.c.document.tool_settings.brush_size, 4)

    def test_ribbon_groups_fold_in_narrow_window(self) -> None:
        ribbon = self.c.window.ribbon
        ventana = self.c.window
        # Se cambia el ancho de la ventana (como haría el usuario): el layout
        # ignora un resize directo de la cinta.
        ventana.resize(1100, 760)
        APP.processEvents()
        ribbon._ajustar_plegado()
        plegado = dict(ribbon._plegables)[ribbon.colores]
        self.assertTrue(plegado.isVisibleTo(ventana))
        self.assertFalse(ribbon.colores.isVisibleTo(ventana))
        plegado.mostrar()
        self.assertIs(ribbon.colores.parentWidget(), plegado.ventana)
        plegado.ventana.hide()
        ventana.resize(1920, 760)
        APP.processEvents()
        ribbon._ajustar_plegado()
        self.assertTrue(ribbon.colores.isVisibleTo(ventana))
        self.assertIs(ribbon.colores.parentWidget(), ribbon.contenedor_grupos)

    def test_opacity_from_size_menu(self) -> None:
        tamano = self.c.window.ribbon.tamano
        self.c.select_tool("brush")
        tamano.opacidad.slider.setValue(40)
        self.assertAlmostEqual(self.c.document.tool_settings.opacity, 0.4)
        self.c.select_tool("eraser")
        tamano.opacidad.slider.setValue(70)
        self.assertAlmostEqual(self.c.document.tool_settings.eraser_opacity, 0.7)
        self.assertAlmostEqual(self.c.document.tool_settings.opacity, 0.4)

    def test_side_rail_sets_free_eraser_size_and_opacity(self) -> None:
        rail = self.c.window.stroke_size_rail
        self.c.select_tool("eraser")
        self.assertFalse(rail.isHidden())
        rail._barra_tamano._mover(77)
        self.assertEqual(self.c.document.tool_settings.tool_sizes["eraser"], 77)
        self.assertEqual(self.c.document.tool_settings.brush_size, 77)
        rail._barra_secundaria._mover(1)
        self.assertAlmostEqual(self.c.document.tool_settings.eraser_opacity, 0.01)
        self.c.select_tool("pencil")
        self.assertEqual(self.c.document.tool_settings.brush_size, 1)
        self.assertEqual(rail._barra_tamano.valor(), 1)
        self.c.select_tool("fill")
        rail._barra_secundaria._mover(90)
        self.assertEqual(self.c.document.tool_settings.fill_tolerance, 90)
        self.c.select_tool("select")
        self.assertTrue(rail.isHidden())

    def test_ribbon_layers_button_toggles_panel(self) -> None:
        boton = self.c.window.ribbon.capas.btn_capas
        visible = self.c.window.layers_panel.isHidden()
        boton.click()
        self.assertEqual(self.c.window.layers_panel.isHidden(), not visible)
        self.assertEqual(boton.isChecked(), visible)
        boton.click()
        self.assertEqual(self.c.window.layers_panel.isHidden(), visible)

    def test_free_eraser_size_erases_that_width(self) -> None:
        self.c.document.active_layer.image.fill(QColor("black"))
        self.c.select_tool("eraser")
        self.c.window.stroke_size_rail._barra_tamano._mover(60)
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=self._pantalla(200, 150))
        imagen = self.c.document.active_layer.image
        self.assertEqual(imagen.pixelColor(200, 150).alpha(), 0)
        self.assertEqual(imagen.pixelColor(225, 150).alpha(), 0)
        self.assertEqual(imagen.pixelColor(240, 150).alpha(), 255)

    def test_eraser_is_square(self) -> None:
        self.c.document.active_layer.image.fill(QColor("black"))
        self.c.select_tool("eraser")
        self.c.set_tool_size(10)
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self._pantalla(100, 100))
        # Las esquinas del cuadrado también se borran (no es un círculo).
        self.assertEqual(pixel(self.c.document, 96, 96).alpha(), 0)

    def test_text_tool_commits_text(self) -> None:
        self.c.select_tool("text")
        self._arrastrar((40, 40), (240, 100))
        editor = self.c.window.text_editor
        self.assertTrue(editor.isVisible() or not editor.isHidden())
        editor.insertPlainText("Hola")
        self.c.select_tool("pencil")
        self.assertTrue(self.c.history.can_undo())


if __name__ == "__main__":
    unittest.main()
