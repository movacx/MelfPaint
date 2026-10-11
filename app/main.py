from __future__ import annotations

import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QLibraryInfo, QLocale, QTimer, QTranslator
from PySide6.QtWidgets import QApplication

from backend.Controller.application_controller import ApplicationController
from backend.Controller.document_controller import DocumentController
from backend.Model.document import Document
from backend.Repository.project_repository import ProjectRepository
from backend.Service.document_service import DocumentService
from backend.Service.history_service import HistoryService
from backend.Service.print_service import PrintService
from backend.Service.recovery_service import RecoveryService
from backend.Service.settings_service import SettingsService


from version import APP_ID, CHANNEL, __version__ as APP_VERSION


def crear_argumentos(values: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="melfpaint",
        description="Editor de imágenes de escritorio para Linux",
    )
    parser.add_argument("archivos", nargs="*", help="Imagen o proyecto que se desea abrir")
    parser.add_argument("--smoke", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"MelfPaint {APP_VERSION} ({CHANNEL})")
    arguments, unknown = parser.parse_known_args(values)
    if unknown:
        parser.error(f"argumentos no reconocidos: {' '.join(unknown)}")
    return arguments


def crear_controlador(
    settings_service: SettingsService | None = None,
    recovery_service: RecoveryService | None = None,
    autosave_interval_ms: int = 120_000,
) -> ApplicationController:
    documento = Document()
    historial = HistoryService()
    repositorio = ProjectRepository()
    servicio_documento = DocumentService(historial)
    controlador_documento = DocumentController(
        document=documento,
        history=historial,
        repository=repositorio,
        document_service=servicio_documento,
    )

    return ApplicationController(
        document_controller=controlador_documento,
        settings_service=settings_service,
        print_service=PrintService(),
        recovery_service=recovery_service,
        autosave_interval_ms=autosave_interval_ms,
    )


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    # Ayuda y versión deben funcionar incluso en una terminal sin servidor
    # gráfico. Primero se resuelven los argumentos propios de MelfPaint.
    arguments = crear_argumentos(values)
    app = QApplication(["melfpaint"])
    app.setApplicationName("MelfPaint")
    app.setApplicationDisplayName("MelfPaint")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("MelfPaint")
    app.setDesktopFileName(APP_ID)
    # La interfaz está en español: también los textos propios de Qt (atajos
    # como «Supr», botones «Sí/No» y diálogos estándar).
    traductor = QTranslator(app)
    ruta_traducciones = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if traductor.load(QLocale(QLocale.Language.Spanish), "qtbase", "_", ruta_traducciones):
        app.installTranslator(traductor)

    temporary: TemporaryDirectory[str] | None = None

    try:
        if arguments.smoke:
            temporary = TemporaryDirectory(prefix="melfpaint-smoke-")
            base = Path(temporary.name)
            settings = SettingsService(base / "settings.json")
            recovery = RecoveryService(recovery_directory=base / "recovery")
            controller = crear_controlador(settings, recovery, autosave_interval_ms=0)
            QTimer.singleShot(350, app.quit)
        else:
            controller = crear_controlador()

        controller.start(arguments.archivos)
        return app.exec()
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
