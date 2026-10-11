from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QToolButton, QWidget

from frontend.Config import metrics as M
from frontend.Config.settings import icon_path
from frontend.View.Components.ribbon_buttons import tema_oscuro_activo


class BotonVentana(QToolButton):
    """Botones de título: minimizar, maximizar/restaurar y cerrar."""

    def __init__(self, tipo: str, tooltip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tipo = tipo
        self.setObjectName("TitleBarButton")
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setFixedSize(M.TITLE_BUTTON_WIDTH, M.TITLE_BAR_HEIGHT)

    def paintEvent(self, event) -> None:
        oscuro = tema_oscuro_activo()
        painter = QPainter(self)
        cerrar = self.tipo == "close"
        activo = self.underMouse() or self.isDown()
        if activo:
            if cerrar:
                fondo = QColor("#c42b1c") if not self.isDown() else QColor("#c83c31")
            else:
                fondo = QColor(255, 255, 255, 18 if self.isDown() else 26) if oscuro else QColor(0, 0, 0, 14 if self.isDown() else 9)
            painter.fillRect(self.rect(), fondo)
        color = QColor("#ffffff") if (cerrar and activo) or oscuro else QColor("#1a1a1a")
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, self.tipo in {"close", "restore"})
        lapiz = QPen(color, 1)
        painter.setPen(lapiz)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() / 2, self.height() / 2
        if self.tipo == "minimize":
            painter.drawLine(QPointF(cx - 5, cy + 0.5), QPointF(cx + 5, cy + 0.5))
        elif self.tipo == "maximize":
            painter.drawRoundedRect(QRectF(cx - 5 + 0.5, cy - 5 + 0.5, 10, 10), 1.5, 1.5)
        elif self.tipo == "restore":
            painter.drawRoundedRect(QRectF(cx - 5, cy - 3, 8, 8), 1.5, 1.5)
            painter.drawPolyline([QPointF(cx - 3, cy - 3), QPointF(cx - 3, cy - 4.5), QPointF(cx + 3.5, cy - 4.5), QPointF(cx + 5, cy - 4.5), QPointF(cx + 5, cy + 3), QPointF(cx + 3, cy + 3)])
        else:
            painter.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx + 5, cy + 5))
            painter.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx - 5, cy + 5))
        painter.end()


class PaintTitleBarView(QFrame):
    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.window = window
        self._posicion_arrastre: QPoint | None = None
        self.setObjectName("PaintTitleBar")
        self.setFixedHeight(M.TITLE_BAR_HEIGHT)
        self._construir_interfaz()

    def _construir_interfaz(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(21, 0, 0, 0)
        layout.setSpacing(0)

        self.icono = QLabel(self)
        self.icono.setObjectName("TitleBarIcon")
        self.icono.setFixedSize(M.TITLE_ICON, M.TITLE_ICON)
        self.icono.setPixmap(QPixmap(str(icon_path("melfpaint"))).scaled(
            M.TITLE_ICON,
            M.TITLE_ICON,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        layout.addWidget(self.icono)
        layout.addSpacing(23)

        self.titulo = QLabel("Sin título - MelfPaint", self)
        self.titulo.setObjectName("TitleBarText")
        layout.addWidget(self.titulo, 1)

        self.btn_minimizar = BotonVentana("minimize", "Minimizar", self)
        self.btn_minimizar.clicked.connect(self.window.showMinimized)
        layout.addWidget(self.btn_minimizar)

        self.btn_maximizar = BotonVentana("maximize", "Maximizar", self)
        self.btn_maximizar.clicked.connect(self.alternar_maximizado)
        layout.addWidget(self.btn_maximizar)

        self.btn_cerrar = BotonVentana("close", "Cerrar", self)
        self.btn_cerrar.clicked.connect(self.window.close)
        layout.addWidget(self.btn_cerrar)

    def set_title(self, title: str) -> None:
        self.titulo.setText(str(title))

    def alternar_maximizado(self) -> None:
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()
        self.actualizar_estado()

    def actualizar_estado(self) -> None:
        maximizada = self.window.isMaximized()
        self.btn_maximizar.tipo = "restore" if maximizada else "maximize"
        self.btn_maximizar.update()
        accion = "Restaurar" if maximizada else "Maximizar"
        self.btn_maximizar.setToolTip(accion)
        self.btn_maximizar.setAccessibleName(accion)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.alternar_maximizado()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        handle = self.window.windowHandle()
        if handle is not None and handle.startSystemMove():
            event.accept()
            return
        self._posicion_arrastre = (
            event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
        )
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._posicion_arrastre is None or self.window.isMaximized():
            super().mouseMoveEvent(event)
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self._posicion_arrastre)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._posicion_arrastre = None
        super().mouseReleaseEvent(event)


class WindowResizeHandle(QWidget):
    def __init__(
        self,
        window: QMainWindow,
        edges: Qt.Edge,
        cursor: Qt.CursorShape,
    ) -> None:
        super().__init__(window)
        self.window = window
        self.edges = edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window.windowHandle()
            if handle is not None and handle.startSystemResize(self.edges):
                event.accept()
                return
        super().mousePressEvent(event)
