from __future__ import annotations

import unittest

from tests.helpers import APP, pixel  # noqa: F401

from PySide6.QtCore import QPointF, QRect
from PySide6.QtGui import QColor, QImage

from backend.Controller.selection_controller import SelectionController
from backend.Controller.tool_controller import ToolController
from backend.Model.document import Document
from backend.Service.history_service import HistoryService
from tests.test_tools import drag


def make() -> tuple[Document, HistoryService, ToolController, SelectionController]:
    document = Document(width=200, height=150)
    history = HistoryService()
    tools = ToolController(document, history)
    selection = SelectionController(document, history, tools, document.tool_settings)
    image = document.active_layer.image
    for x in range(20, 60):
        for y in range(20, 60):
            image.setPixelColor(x, y, QColor("red"))
    return document, history, tools, selection


class SelectionTests(unittest.TestCase):
    def test_move_selection_outside_canvas_clips_on_commit(self) -> None:
        document, history, tools, selection = make()
        tools.set_tool("select")
        drag(tools, (20, 20), (60, 60))
        self.assertTrue(selection.has_selection())
        drag(tools, (40, 40), (-10, 40))
        self.assertEqual(document.selection.current_rect.x(), -30)
        selection.commit()
        self.assertEqual(pixel(document, 5, 30), QColor("red"))
        self.assertEqual(pixel(document, 30, 30).alpha(), 0)

    def test_resize_selection_with_handle(self) -> None:
        document, history, tools, selection = make()
        tools.set_tool("select")
        drag(tools, (20, 20), (60, 60))
        drag(tools, (60, 60), (100, 100))
        self.assertEqual(document.selection.current_rect, QRect(20, 20, 80, 80))
        selection.commit()
        self.assertEqual(pixel(document, 95, 95), QColor("red"))

    def test_resize_at_origin_is_not_lost(self) -> None:
        document = Document(width=100, height=100)
        history = HistoryService()
        tools = ToolController(document, history)
        selection = SelectionController(document, history, tools, document.tool_settings)
        document.active_layer.image.fill(QColor("blue"))
        for x in range(0, 40):
            document.active_layer.image.setPixelColor(x, 0, QColor("red"))
        tools.set_tool("select")
        drag(tools, (0, 0), (40, 40))
        selection.rotate(90)
        selection.commit()
        self.assertTrue(history.can_undo())
        self.assertEqual(pixel(document, 39, 20), QColor("red"))

    def test_ctrl_drag_duplicates(self) -> None:
        document, history, tools, selection = make()
        tools.set_tool("select")
        drag(tools, (20, 20), (60, 60))
        tools.set_modifiers(ctrl=True)
        drag(tools, (40, 40), (140, 40))
        tools.set_modifiers()
        selection.commit()
        self.assertEqual(pixel(document, 30, 30), QColor("red"))
        self.assertEqual(pixel(document, 130, 30), QColor("red"))

    def test_invert_selection(self) -> None:
        document, history, tools, selection = make()
        tools.set_tool("select")
        drag(tools, (20, 20), (60, 60))
        selection.invert()
        self.assertEqual(document.selection.current_rect, QRect(0, 0, 200, 150))
        selection.delete()
        self.assertEqual(pixel(document, 30, 30), QColor("red"))

    def test_paste_keeps_full_image(self) -> None:
        document, history, tools, selection = make()
        image = QImage(300, 50, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor("green"))
        selection.paste(image)
        self.assertEqual(document.selection.current_rect.size().width(), 300)

    def test_transparent_selection_hides_color2(self) -> None:
        document, history, tools, selection = make()
        document.active_layer.image.fill(QColor("white"))
        for x in range(20, 30):
            document.active_layer.image.setPixelColor(x, 20, QColor("red"))
        tools.set_tool("select")
        drag(tools, (10, 10), (40, 40))
        selection.set_transparent(True)
        display = document.selection.display_image()
        self.assertEqual(display.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(display.pixelColor(12, 10), QColor("red"))


if __name__ == "__main__":
    unittest.main()
