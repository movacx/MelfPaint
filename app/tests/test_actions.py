from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import APP, MESSAGES  # noqa: F401

import main
from backend.Service.recovery_service import RecoveryService
from backend.Service.settings_service import SettingsService


class EveryActionTests(unittest.TestCase):
    """Cada acción de los menús debe tener un manejador y no fallar."""

    def test_all_window_actions(self) -> None:
        with tempfile.TemporaryDirectory() as carpeta:
            base = Path(carpeta)
            controller = main.crear_controlador(
                SettingsService(base / "settings.json"),
                RecoveryService(recovery_directory=base / "recovery"),
                autosave_interval_ms=0,
            )
            controller.start([])
            controller.wallpaper_service.apply = lambda *a, **k: base / "fondo.png"
            controller.print_service.imprimir = lambda *a, **k: False
            controller.print_service.vista_previa = lambda *a, **k: None
            controller.print_service.configurar_pagina = lambda *a, **k: False
            mensajes: list[str] = []
            controller.statusChanged.connect(mensajes.append)
            omitidas = {"exit"}
            for action_id in sorted(controller.window.acciones):
                if action_id in omitidas:
                    continue
                MESSAGES.clear()
                with self.subTest(action=action_id):
                    controller.execute_action(action_id)
                    errores = [m for m in MESSAGES if m[0] == "critical"]
                    self.assertFalse(errores, errores)
            controller.set_full_screen(False)
            self.assertFalse([m for m in mensajes if "no disponible" in m], mensajes)
            controller.document.modified = False
            controller.window.hide()


if __name__ == "__main__":
    unittest.main()
