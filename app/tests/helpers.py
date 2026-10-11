from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication(["melfpaint-tests"])


def pixel(document, x: int, y: int, layer: int = -1):
    return document.layers[layer].image.pixelColor(x, y)


# Los cuadros de mensaje modales bloquearían las pruebas sin pantalla.
from PySide6.QtWidgets import QMessageBox  # noqa: E402

MESSAGES: list[tuple[str, str, str]] = []


def _record(kind: str, answer):
    def show(parent, title, text, *args, **kwargs):  # noqa: ANN001, ANN202
        MESSAGES.append((kind, str(title), str(text)))
        return answer

    return staticmethod(show)


QMessageBox.critical = _record("critical", QMessageBox.StandardButton.Ok)
QMessageBox.warning = _record("warning", QMessageBox.StandardButton.Ok)
QMessageBox.information = _record("information", QMessageBox.StandardButton.Ok)
QMessageBox.question = _record("question", QMessageBox.StandardButton.No)


# Diálogos de archivo, entrada y diálogos propios: se cierran al instante.
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMenu  # noqa: E402

QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getDouble = staticmethod(lambda *a, **k: (0.0, False))
QDialog.exec = lambda self: QDialog.DialogCode.Rejected  # type: ignore[method-assign]
QMenu.exec = lambda self, *a, **k: None  # type: ignore[method-assign]
