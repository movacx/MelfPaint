from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import APP, MESSAGES, pixel  # noqa: F401

from PySide6.QtCore import QPointF, QRect
from PySide6.QtGui import QColor, QImage

import main
from backend.Repository.project_repository import ProjectRepository
from backend.Service.recovery_service import RecoveryService
from backend.Service.settings_service import SettingsService


class LayersAndStrokesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.carpeta = tempfile.TemporaryDirectory()
        base = Path(self.carpeta.name)
        self.c = main.crear_controlador(
            SettingsService(base / "settings.json"),
            RecoveryService(recovery_directory=base / "recovery"),
            autosave_interval_ms=0,
        )
        self.c.start([])
        self.c.new_document({"width": 300, "height": 200})
        self.tc = self.c.tool_controller

    def tearDown(self) -> None:
        self.c.document.modified = False
        self.c.window.hide()
        self.carpeta.cleanup()

    def _trazo(self, puntos: list[tuple[float, float]]) -> None:
        self.tc.pointer_down(QPointF(*puntos[0]))
        for x, y in puntos[1:]:
            self.tc.pointer_move(QPointF(x, y))
        self.tc.pointer_up(QPointF(*puntos[-1]))

    def test_stroke_history_stores_only_the_touched_rectangle(self) -> None:
        self.c.select_tool("pencil")
        self.c.set_tool_size(3)
        self._trazo([(20, 20), (60, 40), (90, 30)])
        comando = self.c.history.undo_stack[-1]
        self.assertIsNotNone(comando.rect)
        self.assertLess(comando.before.width() * comando.before.height(), 300 * 200 // 4)
        self.assertEqual(comando.before.size(), comando.rect.size())

    def test_undo_redo_of_patch_restores_pixels_and_composite_cache(self) -> None:
        doc = self.c.document
        self.c.select_tool("brush")
        self.c.set_tool_size(8)
        doc.composite()  # llena el caché para probar la recomposición por región
        self._trazo([(30, 100), (120, 90), (200, 110)])
        self.assertGreater(pixel(doc, 120, 90).alpha(), 0)
        self.assertEqual(doc.composite().pixelColor(120, 90), QColor("black"))
        self.c.execute_action("undo")
        self.assertEqual(pixel(doc, 120, 90).alpha(), 0)
        self.assertEqual(doc.composite().pixelColor(120, 90), QColor("white"))
        self.c.execute_action("redo")
        self.assertGreater(pixel(doc, 120, 90).alpha(), 0)
        self.assertEqual(doc.composite().pixelColor(120, 90), QColor("black"))

    def test_region_cache_matches_full_recomposition(self) -> None:
        doc = self.c.document
        self.c.select_tool("pencil")
        self.c.set_tool_size(5)
        doc.composite()
        self._trazo([(10, 10), (150, 120), (280, 30)])
        incremental = doc.composite()
        doc.invalidate()
        self.assertEqual(incremental, doc.composite())

    def test_pencil_curve_ends_on_cursor_and_click_marks_pixel(self) -> None:
        doc = self.c.document
        self.c.select_tool("pencil")
        self.c.set_tool_size(1)
        self._trazo([(50, 50), (51, 50)])
        self.assertGreater(pixel(doc, 50, 50).alpha(), 0)
        self._trazo([(100, 100), (140, 100), (180, 100)])
        self.assertGreater(pixel(doc, 180, 100).alpha(), 0)
        self.assertGreater(pixel(doc, 140, 100).alpha(), 0)

    def test_locked_layer_blocks_drawing(self) -> None:
        doc = self.c.document
        self.assertTrue(self.c.set_layer_locked(doc.active_layer.id, True))
        self.c.select_tool("pencil")
        self._trazo([(10, 10), (40, 40)])
        self.assertEqual(pixel(doc, 25, 25).alpha(), 0)
        self.assertTrue(self.c.set_layer_locked(doc.active_layer.id, False))
        self._trazo([(10, 10), (40, 40)])
        self.assertGreater(pixel(doc, 25, 25).alpha(), 0)

    def test_blend_mode_changes_composite_and_can_be_undone(self) -> None:
        doc = self.c.document
        doc.layers[0].image.fill(QColor(200, 100, 50))
        self.c.add_layer()
        doc.active_layer.image.fill(QColor(128, 128, 128))
        normal = doc.composite().pixelColor(5, 5)
        self.assertTrue(self.c.set_layer_blend_mode(doc.active_layer.id, "multiply"))
        multiplicado = doc.composite().pixelColor(5, 5)
        self.assertLess(multiplicado.red(), normal.red())
        self.c.execute_action("undo")
        self.assertEqual(doc.active_layer.blend_mode, "normal")
        self.assertEqual(doc.composite().pixelColor(5, 5), normal)
        self.assertFalse(self.c.set_layer_blend_mode(doc.active_layer.id, "inexistente"))

    def test_flatten_merges_visible_layers(self) -> None:
        doc = self.c.document
        doc.layers[0].image.fill(QColor(255, 0, 0))
        self.c.add_layer()
        doc.active_layer.image.fill(QColor(0, 0, 255))
        self.assertTrue(self.c.flatten_layers())
        self.assertEqual(len(doc.layers), 1)
        self.assertEqual(pixel(doc, 5, 5), QColor(0, 0, 255))
        self.c.execute_action("undo")
        self.assertEqual(len(doc.layers), 2)

    def test_project_roundtrip_keeps_lock_and_blend_mode(self) -> None:
        doc = self.c.document
        self.c.add_layer()
        self.c.set_layer_locked(doc.active_layer.id, True)
        self.c.set_layer_blend_mode(doc.active_layer.id, "screen")
        ruta = Path(self.carpeta.name) / "prueba.melfpaint"
        repo = ProjectRepository()
        repo.save_project(doc, ruta)
        cargado = repo.load_project(ruta)
        self.assertTrue(cargado.layers[-1].locked)
        self.assertEqual(cargado.layers[-1].blend_mode, "screen")
        self.assertFalse(cargado.layers[0].locked)

    def test_copy_is_enabled_right_after_selecting_with_the_mouse(self) -> None:
        acciones = self.c.window.acciones
        self.c.select_tool("select")
        self.assertFalse(acciones["copy"].isEnabled())
        self.tc.pointer_down(QPointF(10, 10))
        self.tc.pointer_move(QPointF(60, 50))
        self.tc.pointer_up(QPointF(60, 50))
        self.assertTrue(self.c.selection_controller.has_selection())
        for accion in ("copy", "cut", "deselect", "crop"):
            self.assertTrue(acciones[accion].isEnabled(), accion)

    def test_copy_paste_moves_content_and_undoes_in_one_step(self) -> None:
        doc = self.c.document
        for x in range(20, 60):
            for y in range(20, 60):
                doc.layers[0].image.setPixelColor(x, y, QColor("red"))
        self.c.select_tool("select")
        self.tc.pointer_down(QPointF(10, 10))
        self.tc.pointer_move(QPointF(80, 80))
        self.tc.pointer_up(QPointF(80, 80))
        self.c.window.acciones["copy"].trigger()
        self.c.window.acciones["paste"].trigger()
        rect = doc.selection.current_rect
        centro = rect.center()
        destino = QPointF(centro.x() + 150, centro.y() + 90)
        self.tc.pointer_down(QPointF(centro))
        self.tc.pointer_move(destino)
        self.tc.pointer_up(destino)
        self.c.execute_action("deselect")
        self.assertEqual(pixel(doc, 40, 40, 0), QColor("red"))
        self.assertEqual(pixel(doc, 40 + 150, 40 + 90), QColor("red"))
        self.c.execute_action("undo")
        self.assertEqual(pixel(doc, 40 + 150, 40 + 90).alpha(), 0)
        self.assertEqual(pixel(doc, 40, 40, 0), QColor("red"))

    def test_drawing_over_an_opened_image_goes_to_its_own_layer(self) -> None:
        doc = self.c.document
        self.c._image_layer_ids.add(doc.layers[0].id)
        doc.layers[0].image.fill(QColor("blue"))
        self.c.select_tool("pencil")
        self.tc.pointer_down(QPointF(10, 10))
        self.tc.pointer_move(QPointF(40, 10))
        self.tc.pointer_up(QPointF(40, 10))
        self.assertEqual(len(doc.layers), 2)
        self.c.select_tool("eraser")
        self.tc.pointer_down(QPointF(5, 10))
        self.tc.pointer_move(QPointF(45, 10))
        self.tc.pointer_up(QPointF(45, 10))
        self.assertEqual(doc.layers[0].image.pixelColor(20, 10), QColor("blue"))

    def test_eraser_only_removes_the_drawing_over_a_pasted_image(self) -> None:
        doc = self.c.document
        imagen = QImage(60, 60, QImage.Format.Format_ARGB32_Premultiplied)
        imagen.fill(QColor("blue"))
        self.assertTrue(self.c.paste_image(imagen))
        self.c.execute_action("deselect")
        self.assertEqual(len(doc.layers), 2)
        self.c.select_tool("pencil")
        self.tc.pointer_down(QPointF(10, 10))
        self.tc.pointer_move(QPointF(40, 10))
        self.tc.pointer_up(QPointF(40, 10))
        self.assertEqual([capa.name for capa in doc.layers], ["Capa 1", "Imagen", "Dibujo"])
        self.c.select_tool("eraser")
        self.tc.pointer_down(QPointF(5, 10))
        self.tc.pointer_move(QPointF(45, 10))
        self.tc.pointer_up(QPointF(45, 10))
        imagen_capa = doc.layers[1].image
        self.assertEqual(imagen_capa.pixelColor(20, 10), QColor("blue"))
        self.assertEqual(doc.layers[2].image.pixelColor(20, 10).alpha(), 0)

    def test_full_layer_commands_are_compacted_to_changed_area(self) -> None:
        doc = self.c.document
        doc.layers[0].image.fill(QColor("black"))
        # Un cambio pequeño sí se reduce a su rectángulo.
        antes = doc.layers[0].image.copy()
        doc.layers[0].image.setPixelColor(100, 100, QColor("red"))
        from backend.Service.history_service import LayerImageCommand
        self.c.history.push(LayerImageCommand(doc.layers[0].id, antes, doc.layers[0].image.copy(), "punto"))
        compacto = self.c.history.undo_stack[-1]
        self.assertEqual(compacto.rect, QRect(100, 100, 1, 1))
        self.c.execute_action("undo")
        self.assertEqual(pixel(doc, 100, 100), QColor("black"))
        self.c.execute_action("redo")
        self.assertEqual(pixel(doc, 100, 100), QColor("red"))

    def test_undo_goes_back_more_than_a_hundred_strokes(self) -> None:
        doc = self.c.document
        self.c.select_tool("pencil")
        for i in range(150):
            self._trazo([(10 + i, 20), (10 + i, 30)])
        self.assertGreaterEqual(len(self.c.history.undo_stack), 150)
        for _ in range(150):
            self.c.execute_action("undo")
        self.assertEqual(pixel(doc, 10, 25).alpha(), 0)
        self.assertEqual(pixel(doc, 100, 25).alpha(), 0)

    def _nuevo_controlador(self):  # noqa: ANN202
        base = Path(self.carpeta.name)
        controlador = main.crear_controlador(
            SettingsService(base / "settings.json"),
            RecoveryService(recovery_directory=base / "recovery2"),
            autosave_interval_ms=0,
        )
        controlador.start([])
        return controlador

    def test_tool_sizes_are_remembered_between_sessions(self) -> None:
        self.c.select_tool("pencil")
        self.c.set_tool_size(7)
        self.c.select_tool("eraser")
        self.c.set_tool_size(40)
        self.assertTrue(self.c._size_save_timer.isActive())
        self.c._save_tool_sizes()
        guardado = SettingsService(Path(self.carpeta.name) / "settings.json").obtener("tamanos_herramienta")
        self.assertEqual(guardado["pencil"], 7)
        self.assertEqual(guardado["eraser"], 40)

        otro = self._nuevo_controlador()
        try:
            otro.select_tool("pencil")
            self.assertEqual(otro.document.tool_settings.brush_size, 7)
            self.assertEqual(otro.window.stroke_size_rail._barra_tamano.valor(), 7)
            otro.select_tool("eraser")
            self.assertEqual(otro.document.tool_settings.brush_size, 40)
            otro.select_tool("brush")
            self.assertEqual(otro.document.tool_settings.brush_size, 3)  # sin guardar: valor inicial
        finally:
            otro.document.modified = False
            otro.window.hide()

    def test_new_document_keeps_the_chosen_size(self) -> None:
        self.c.select_tool("pencil")
        self.c.set_tool_size(9)
        self.c.new_document({"width": 120, "height": 90})
        self.c.select_tool("pencil")
        self.assertEqual(self.c.document.tool_settings.brush_size, 9)

    def test_saved_tool_sizes_are_sanitized(self) -> None:
        ajustes = SettingsService(Path(self.carpeta.name) / "otro.json")
        ajustes.cambiar("tamanos_herramienta", {"pencil": 9999, "brush": "abc", "x": 3, "eraser": 0})
        self.assertEqual(ajustes.obtener("tamanos_herramienta"), {"pencil": 256.0, "eraser": 1.0})


if __name__ == "__main__":
    unittest.main()
