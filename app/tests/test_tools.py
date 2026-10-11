from __future__ import annotations

import unittest

from tests.helpers import APP, pixel  # noqa: F401

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor

from backend.Controller.tool_controller import ToolController
from backend.Model.document import Document
from backend.Service.history_service import HistoryService


def make(width: int = 200, height: int = 150) -> tuple[Document, HistoryService, ToolController]:
    document = Document(width=width, height=height)
    history = HistoryService()
    return document, history, ToolController(document, history)


def drag(controller: ToolController, start, end, steps: int = 4, button="primary") -> None:
    controller.pointer_down(QPointF(*start), button)
    for index in range(1, steps + 1):
        t = index / steps
        controller.pointer_move(QPointF(start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t))
    controller.pointer_up(QPointF(*end))


class ShapeToolTests(unittest.TestCase):
    def test_shape_stays_editable_until_click_outside(self) -> None:
        document, history, controller = make()
        controller.set_tool("rectangle")
        drag(controller, (20, 20), (60, 60))
        self.assertTrue(controller.has_pending_shape())
        self.assertEqual(pixel(document, 20, 20).alpha(), 0, "la forma no debe tocar la capa todavía")
        self.assertFalse(history.can_undo())
        # Mover la forma arrastrando desde dentro.
        drag(controller, (40, 40), (90, 70))
        overlay = controller.overlay()
        self.assertEqual(overlay["rect"].topLeft(), QPointF(70, 50))
        # Clic fuera: se confirma y empieza otra forma.
        drag(controller, (5, 140), (6, 141))
        self.assertFalse(controller.has_pending_shape())
        self.assertTrue(history.can_undo())
        self.assertGreater(pixel(document, 70, 70).alpha(), 0)
        self.assertEqual(pixel(document, 20, 20).alpha(), 0)

    def test_resize_handle_scales_shape(self) -> None:
        document, history, controller = make()
        controller.set_tool("ellipse")
        drag(controller, (10, 10), (50, 50))
        drag(controller, (50, 50), (110, 90))
        self.assertEqual(controller.overlay()["rect"], QRectF(10, 10, 100, 80))

    def test_color_change_updates_pending_shape(self) -> None:
        document, history, controller = make()
        controller.set_tool("rectangle")
        document.tool_settings.line_width = 4
        drag(controller, (20, 20), (80, 80))
        document.tool_settings.primary_color = QColor("red")
        controller.refresh_preview()
        controller.commit_pending()
        self.assertEqual(pixel(document, 20, 50).red(), 255)
        self.assertEqual(pixel(document, 20, 50).green(), 0)

    def test_shift_draws_square(self) -> None:
        document, history, controller = make()
        controller.set_tool("rectangle")
        controller.set_modifiers(shift=True)
        drag(controller, (10, 10), (70, 40))
        rect = controller.overlay()["rect"]
        self.assertEqual(rect.width(), rect.height())

    def test_curve_needs_two_bends(self) -> None:
        document, history, controller = make()
        controller.set_tool("curve")
        drag(controller, (10, 100), (190, 100))
        self.assertTrue(controller.has_pending_shape())
        self.assertIsNone(controller.overlay(), "todavía se está doblando")
        drag(controller, (60, 20), (60, 20), steps=1)
        drag(controller, (140, 140), (140, 140), steps=1)
        self.assertIsNotNone(controller.overlay())
        controller.commit_pending()
        self.assertTrue(history.can_undo())

    def test_polygon_closes_on_start_point(self) -> None:
        document, history, controller = make()
        controller.set_tool("polygon")
        document.tool_settings.fill_enabled = True
        document.tool_settings.fill_mode = "solid"
        drag(controller, (20, 20), (120, 20))
        drag(controller, (120, 120), (120, 120), steps=1)
        drag(controller, (20, 120), (20, 120), steps=1)
        drag(controller, (21, 21), (21, 21), steps=1)
        self.assertEqual(controller.overlay()["kind"], "box")
        controller.commit_pending()
        self.assertEqual(pixel(document, 70, 70), QColor("white"))

    def test_switching_tool_commits_shape(self) -> None:
        document, history, controller = make()
        controller.set_tool("line")
        drag(controller, (10, 10), (100, 10))
        controller.set_tool("pencil")
        self.assertFalse(controller.has_pending_shape())
        self.assertGreater(pixel(document, 50, 10).alpha(), 0)

    def test_tiny_click_does_not_create_shape(self) -> None:
        document, history, controller = make()
        controller.set_tool("rectangle")
        drag(controller, (10, 10), (10, 10), steps=1)
        self.assertFalse(controller.has_pending_shape())


class StrokeToolTests(unittest.TestCase):
    def test_translucent_stroke_does_not_accumulate(self) -> None:
        document, history, controller = make()
        document.tool_settings.opacity = 0.5
        document.tool_settings.brush_size = 10
        controller.set_tool("brush")
        # Ida y vuelta sobre el mismo lugar en un solo trazo.
        controller.pointer_down(QPointF(20, 50))
        for x in (60, 100, 60, 20, 100):
            controller.pointer_move(QPointF(x, 50))
        controller.pointer_up(QPointF(100, 50))
        alpha = pixel(document, 60, 50).alpha()
        self.assertTrue(120 <= alpha <= 135, alpha)

    def test_smoothed_stroke_is_continuous(self) -> None:
        document, history, controller = make(700, 500)
        document.tool_settings.brush_size = 8
        controller.set_tool("brush")
        controller.pointer_down(QPointF(100, 300))
        controller.pointer_move(QPointF(400, 100))
        controller.pointer_up(QPointF(600, 400))
        # El vértice de la curva suavizada pasa cerca de (400, 175).
        columna = [pixel(document, 400, y).alpha() for y in range(100, 300)]
        self.assertGreater(max(columna), 200)

    def test_marker_is_translucent(self) -> None:
        document, history, controller = make()
        document.tool_settings.brush_type = "marker"
        document.tool_settings.brush_size = 12
        controller.set_tool("brush")
        drag(controller, (20, 50), (150, 50), steps=20)
        alpha = pixel(document, 80, 50).alpha()
        self.assertTrue(110 <= alpha <= 140, alpha)

    def test_all_brushes_paint(self) -> None:
        for brush in ("round", "calligraphy", "calligraphy_pen", "airbrush", "oil", "crayon", "marker", "natural_pencil", "watercolor"):
            with self.subTest(brush=brush):
                document, history, controller = make()
                document.tool_settings.brush_type = brush
                document.tool_settings.brush_size = 12
                controller.set_tool("brush")
                drag(controller, (20, 50), (150, 60), steps=20)
                self.assertTrue(history.can_undo())

    def test_right_click_eraser_replaces_color1_with_color2(self) -> None:
        document, history, controller = make()
        layer = document.active_layer
        layer.image.fill(QColor("black"))
        painter_region = layer.image.copy()
        for x in range(100, 200):
            for y in range(0, 150):
                layer.image.setPixelColor(x, y, QColor("blue"))
        document.tool_settings.primary_color = QColor("black")
        document.tool_settings.secondary_color = QColor("yellow")
        document.tool_settings.brush_size = 6
        controller.set_tool("eraser")
        drag(controller, (20, 75), (180, 75), steps=20, button="secondary")
        self.assertEqual(pixel(document, 50, 75), QColor("yellow"))
        self.assertEqual(pixel(document, 150, 75), QColor("blue"))
        del painter_region

    def test_left_eraser_clears(self) -> None:
        document, history, controller = make()
        document.active_layer.image.fill(QColor("black"))
        controller.set_tool("eraser")
        drag(controller, (20, 75), (180, 75))
        self.assertEqual(pixel(document, 100, 75).alpha(), 0)

    def test_picker_ignores_transparent_pixels(self) -> None:
        document, history, controller = make()
        document.show_background = False
        document.invalidate()
        document.tool_settings.primary_color = QColor("blue")
        controller.set_tool("eyedropper")
        drag(controller, (5, 5), (5, 5), steps=1)
        self.assertEqual(document.tool_settings.primary_color, QColor("blue"))

    def test_hidden_layer_is_not_painted(self) -> None:
        document, history, controller = make()
        document.active_layer.visible = False
        avisos: list[str] = []
        controller.aviso.connect(avisos.append)
        controller.set_tool("pencil")
        drag(controller, (10, 10), (100, 10))
        self.assertFalse(history.can_undo())
        self.assertEqual(len(avisos), 1)

    def test_picker_returns_to_previous_tool(self) -> None:
        document, history, controller = make()
        document.active_layer.image.fill(QColor("red"))
        controller.set_tool("brush")
        controller.set_tool("eyedropper")
        drag(controller, (5, 5), (5, 5), steps=1)
        self.assertEqual(controller.active_tool_id, "brush")
        self.assertEqual(document.tool_settings.primary_color, QColor("red"))


if __name__ == "__main__":
    unittest.main()
