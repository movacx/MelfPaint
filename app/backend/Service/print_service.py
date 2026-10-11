from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPageSetupDialog, QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import QWidget


class PrintService:
    """Se encarga de imprimir el resultado visible del documento."""

    def __init__(self) -> None:
        self._impresora: QPrinter | None = None

    def crear_impresora(self) -> QPrinter:
        # Se conserva la misma impresora para que «Configurar página» afecte
        # a la impresión y a la vista previa posteriores.
        if self._impresora is None:
            impresora = QPrinter(QPrinter.PrinterMode.HighResolution)
            impresora.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            impresora.setPageOrientation(QPageLayout.Orientation.Portrait)
            impresora.setFullPage(False)
            self._impresora = impresora
        return self._impresora

    def configurar_pagina(self, parent: QWidget | None = None) -> bool:
        dialogo = QPageSetupDialog(self.crear_impresora(), parent)
        return bool(dialogo.exec())

    def imprimir(self, documento, parent: QWidget | None = None) -> bool:  # noqa: ANN001
        impresora = self.crear_impresora()
        dialogo = QPrintDialog(impresora, parent)
        if not dialogo.exec():
            return False

        self._dibujar_documento(documento, impresora)
        return True

    def vista_previa(self, documento, parent: QWidget | None = None) -> None:  # noqa: ANN001
        impresora = self.crear_impresora()
        dialogo = QPrintPreviewDialog(impresora, parent)
        dialogo.paintRequested.connect(lambda printer: self._dibujar_documento(documento, printer))
        dialogo.exec()

    def _dibujar_documento(self, documento, impresora: QPrinter) -> None:  # noqa: ANN001
        imagen = documento.composite()
        pintor = QPainter(impresora)
        if not pintor.isActive():
            raise OSError("No se pudo iniciar la impresión")

        try:
            pagina = QRectF(impresora.pageRect(QPrinter.Unit.DevicePixel))
            # Tamaño real según la resolución de la imagen; solo se
            # reduce cuando no cabe en la página.
            dpi = max(1, int(getattr(documento, "dpi", 96) or 96))
            escala = impresora.resolution() / dpi
            ancho = imagen.width() * escala
            alto = imagen.height() * escala
            if ancho > pagina.width() or alto > pagina.height():
                factor = min(pagina.width() / ancho, pagina.height() / alto)
                ancho *= factor
                alto *= factor
            pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            # Sin «página completa», el origen del pintor ya es la esquina del área imprimible.
            pintor.drawImage(QRectF(0, 0, ancho, alto), imagen)
        finally:
            pintor.end()

