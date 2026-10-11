from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import APP, pixel  # noqa: F401

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage

import main
from backend.Repository.project_repository import writable_formats
from backend.Service.recovery_service import RecoveryService
from backend.Service.settings_service import SettingsService


class ApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.base = base
        self.controller = main.crear_controlador(
            SettingsService(base / "settings.json"),
            RecoveryService(recovery_directory=base / "recovery"),
            autosave_interval_ms=0,
        )
        self.controller.start([])
        self.document = self.controller.document

    def tearDown(self) -> None:
        self.controller.document.modified = False
        self.controller.window.hide()
        self.controller.window.deleteLater()
        self.temporary.cleanup()

    def test_ai_actions_are_gone(self) -> None:
        acciones = self.controller.window.acciones
        self.assertFalse(any("copilot" in action_id for action_id in acciones))
        self.assertFalse(hasattr(self.controller.window.ribbon, "grupo_tools"))

    def test_save_formats(self) -> None:
        self.document.active_layer.image.fill(QColor("orange"))
        for extension, formato in ((".png", "PNG"), (".jpg", "JPEG"), (".bmp", "BMP"), (".gif", "GIF"), (".tiff", "TIFF"), (".ico", "ICO"), (".webp", "WEBP")):
            if formato not in writable_formats():
                continue
            with self.subTest(formato=formato):
                target = self.base / f"imagen{extension}"
                self.assertTrue(self.controller.save_as(target))
                self.assertTrue(target.exists() and target.stat().st_size > 0)

    def test_pending_shape_is_committed_before_save(self) -> None:
        tools = self.controller.tool_controller
        self.controller.select_shape("rectangle")
        tools.pointer_down(QPointF(10, 10))
        tools.pointer_move(QPointF(80, 80))
        tools.pointer_up(QPointF(80, 80))
        self.assertTrue(tools.has_pending_shape())
        target = self.base / "forma.png"
        self.assertTrue(self.controller.save_as(target))
        self.assertFalse(tools.has_pending_shape())
        saved = QImage(str(target))
        self.assertEqual(saved.pixelColor(10, 40).black(), 255)

    def test_undo_removes_pending_shape(self) -> None:
        tools = self.controller.tool_controller
        self.controller.select_shape("ellipse")
        tools.pointer_down(QPointF(10, 10))
        tools.pointer_move(QPointF(80, 80))
        tools.pointer_up(QPointF(80, 80))
        self.controller.execute_action("undo")
        self.assertFalse(tools.has_pending_shape())
        self.assertFalse(self.controller.history.can_undo())

    def test_paste_bigger_image_enlarges_canvas(self) -> None:
        self.controller.window.preguntar_ampliar_lienzo = lambda: True
        image = QImage(self.document.width + 100, 50, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor("green"))
        self.assertTrue(self.controller.paste_image(image))
        self.assertEqual(self.controller.document.width, image.width())

    def test_image_properties_black_and_white(self) -> None:
        self.document.active_layer.image.fill(QColor(200, 30, 30))
        self.controller.image_properties(
            {"width": self.document.width, "height": self.document.height, "dpi": 96, "transparent": False, "background": QColor("white"), "black_white": True}
        )
        color = pixel(self.controller.document, 5, 5)
        self.assertIn(color.red(), (0, 255))
        self.assertEqual(color.red(), color.green())

    def test_theme_modes(self) -> None:
        self.controller.set_theme_mode("oscuro")
        self.assertTrue(self.controller.window.tema_oscuro)
        self.controller.set_theme_mode("claro")
        self.assertFalse(self.controller.window.tema_oscuro)
        self.assertEqual(self.controller.settings_service.obtener("tema"), "claro")

    def test_edit_colors_adds_custom_color(self) -> None:
        self.controller.window.seleccionar_color_personalizado = lambda inicial: QColor("#123456")
        self.controller.edit_colors()
        self.assertEqual(self.controller.document.tool_settings.primary_color, QColor("#123456"))
        self.assertIn("#ff123456", self.controller.settings_service.obtener("colores_personalizados"))

    def test_every_menu_action_is_handled(self) -> None:
        sin_dialogo = {
            "undo", "redo", "zoom_in", "zoom_out", "zoom_100", "fit_window", "toggle_grid", "toggle_rulers",
            "toggle_statusbar", "toggle_layers", "toggle_ribbon", "size_increase", "size_decrease",
            "rotate_right", "rotate_left", "rotate_180", "flip_horizontal", "flip_vertical", "select_all",
            "invert_selection", "deselect", "delete_selection", "layer_add", "layer_duplicate",
            "layer_move_up", "layer_move_down", "layer_merge_down", "layer_delete", "filter_invert",
            "filter_grayscale", "filter_black_white", "filter_sepia", "filter_blur", "filter_sharpen",
            "filter_edge", "filter_coloring_book", "copy", "cut", "crop",
        }
        mensajes: list[str] = []
        self.controller.statusChanged.connect(mensajes.append)
        for action_id in sorted(sin_dialogo):
            with self.subTest(action=action_id):
                self.controller.execute_action(action_id)
        self.assertFalse([m for m in mensajes if "no disponible" in m], mensajes)


if __name__ == "__main__":
    unittest.main()
