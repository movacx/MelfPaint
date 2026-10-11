from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QActionGroup, QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from backend.Model.layer import BLEND_MODES
from frontend.Config import metrics as M
from frontend.View.Components.ribbon_buttons import BotonPaint, cargar_icono, tema_oscuro_activo


CAPA_ID_ROLE = Qt.ItemDataRole.UserRole

# Las miniaturas se calculan una vez por contenido: reconstruir el panel en cada
# trazo reescalaba todas las capas completas.
_MINIATURAS: dict[tuple, QPixmap] = {}
_MAX_MINIATURAS = 96


class _FilaCapa(QWidget):
    """Tarjeta de una capa: nombre, opacidad, ojo, menú «⋯» y miniatura."""

    visibilidadCambiada = Signal(str, bool)
    accionSolicitada = Signal(str, str)

    def __init__(self, capa: Any, fondo: QColor | None, es_unica: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.capa_id = str(getattr(capa, "id", ""))
        visible = bool(getattr(capa, "visible", True))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 6, 8)
        layout.setSpacing(4)

        encabezado = QHBoxLayout()
        encabezado.setContentsMargins(0, 0, 0, 0)
        encabezado.setSpacing(2)
        self.nombre = QLabel(str(getattr(capa, "name", "Capa")), self)
        self.nombre.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        encabezado.addWidget(self.nombre, 1)

        bloqueada = bool(getattr(capa, "locked", False))
        mezcla = str(getattr(capa, "blend_mode", "normal"))
        porcentaje = round(float(getattr(capa, "opacity", 1.0)) * 100)
        detalle = []
        if porcentaje < 100:
            detalle.append(f"{porcentaje}%")
        if mezcla != "normal" and mezcla in BLEND_MODES:
            detalle.append(BLEND_MODES[mezcla][0])
        self.opacidad = QLabel(" · ".join(detalle), self)
        self.opacidad.setObjectName("StatusMetric")
        self.tiene_detalle = bool(detalle)
        if bloqueada:
            self.candado = QLabel(self)
            self.candado.setPixmap(cargar_icono("lock", tema_oscuro_activo()).pixmap(14, 14))
            self.candado.setToolTip("Capa bloqueada")
            encabezado.addWidget(self.candado)

        self.visible = BotonPaint(
            "Ocultar capa" if visible else "Mostrar capa",
            "visible" if visible else "hidden",
            28,
            28,
            16,
            parent=self,
        )
        self.visible.clicked.connect(lambda: self.visibilidadCambiada.emit(self.capa_id, not visible))
        encabezado.addWidget(self.visible)

        menu = QMenu(self)
        for texto, accion, icono in (
            ("Ocultar capa" if visible else "Mostrar capa", "toggle_visible", "hidden" if visible else "visible"),
            ("Desbloquear capa" if bloqueada else "Bloquear capa", "lock", "lock"),
            ("Duplicar capa", "duplicate", "duplicate"),
            ("Combinar hacia abajo", "merge", "merge-down"),
            ("Subir capa", "up", "move-up"),
            ("Bajar capa", "down", "move-down"),
            ("Cambiar nombre…", "rename", "rename"),
            ("Eliminar capa", "delete", "delete"),
        ):
            item = menu.addAction(cargar_icono(icono, tema_oscuro_activo()), texto)
            item.triggered.connect(lambda checked=False, value=accion: self.accionSolicitada.emit(self.capa_id, value))
            if accion == "delete" and es_unica:
                item.setText("Borrar contenido")
            if accion == "merge":
                self._agregar_mezcla(menu, mezcla)
        if not es_unica:
            menu.addSeparator()
            acoplar = menu.addAction(cargar_icono("merge-down", tema_oscuro_activo()), "Acoplar imagen")
            acoplar.triggered.connect(lambda checked=False: self.accionSolicitada.emit(self.capa_id, "flatten"))
        self.mas = BotonPaint("Más opciones de capa", "more", 28, 28, 16, menu=menu, parent=self)
        encabezado.addWidget(self.mas)
        layout.addLayout(encabezado)
        if self.tiene_detalle:
            layout.addWidget(self.opacidad)
        else:
            self.opacidad.hide()

        self.miniatura = QLabel(self)
        self.miniatura.setObjectName("LayerThumbnail")
        self.miniatura.setFixedSize(144, M.LAYER_THUMBNAIL)
        self.miniatura.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.miniatura.setPixmap(self._crear_miniatura(capa, fondo))
        if not visible:
            self.miniatura.setEnabled(False)
        layout.addWidget(self.miniatura, 0, Qt.AlignmentFlag.AlignLeft)

    def _agregar_mezcla(self, menu: QMenu, actual: str) -> None:
        submenu = menu.addMenu("Modo de mezcla")
        grupo = QActionGroup(submenu)
        grupo.setExclusive(True)
        for modo, (nombre, _) in BLEND_MODES.items():
            accion = submenu.addAction(nombre)
            accion.setCheckable(True)
            accion.setChecked(modo == actual)
            grupo.addAction(accion)
            accion.triggered.connect(
                lambda checked=False, value=modo: self.accionSolicitada.emit(self.capa_id, f"blend::{value}")
            )

    def _crear_miniatura(self, capa: Any, fondo_documento: QColor | None) -> QPixmap:
        imagen = getattr(capa, "image", None)
        if not isinstance(imagen, QImage) or imagen.isNull():
            return QPixmap()
        clave = (imagen.cacheKey(), fondo_documento.rgba() if fondo_documento is not None else None)
        guardada = _MINIATURAS.get(clave)
        if guardada is not None:
            return guardada
        pixmap = self._dibujar_miniatura(imagen, fondo_documento)
        if len(_MINIATURAS) >= _MAX_MINIATURAS:
            _MINIATURAS.pop(next(iter(_MINIATURAS)))
        _MINIATURAS[clave] = pixmap
        return pixmap

    def _dibujar_miniatura(self, imagen: QImage, fondo_documento: QColor | None) -> QPixmap:
        ancho, alto = 140, M.LAYER_THUMBNAIL - 4
        escalada = imagen.scaled(QSize(ancho, alto), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        resultado = QImage(escalada.size(), QImage.Format.Format_ARGB32_Premultiplied)
        painter = QPainter(resultado)
        if fondo_documento is not None:
            # La capa inferior se muestra sobre el color de fondo.
            painter.fillRect(resultado.rect(), fondo_documento)
        else:
            resultado.fill(QColor("#ffffff"))
            for y in range(0, resultado.height(), 6):
                for x in range(0, resultado.width(), 6):
                    if (x // 6 + y // 6) % 2:
                        painter.fillRect(x, y, 6, 6, QColor("#e3e3e3"))
        painter.drawImage(0, 0, escalada)
        painter.end()
        return QPixmap.fromImage(resultado)


class LayersPanelView(QFrame):
    activarSolicitado = Signal(str)
    agregarSolicitado = Signal()
    eliminarSolicitado = Signal()
    duplicarSolicitado = Signal()
    moverSolicitado = Signal(str, int)
    combinarSolicitado = Signal()
    renombrarSolicitado = Signal(str, str)
    visibilidadSolicitada = Signal(str, bool)
    bloqueoSolicitado = Signal(str, bool)
    mezclaSolicitada = Signal(str, str)
    acoplarSolicitado = Signal()
    opacidadSolicitada = Signal(str, int)
    opacidadInicioSolicitada = Signal(str)
    opacidadFinSolicitada = Signal(str)

    def __init__(self, document: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.documento = document
        self._actualizando = False
        self.setObjectName("LayersPanel")
        self.setFixedWidth(M.LAYERS_PANEL_WIDTH)
        self._construir_interfaz()
        self.actualizar(document)

    def _construir_interfaz(self) -> None:
        principal = QVBoxLayout(self)
        principal.setContentsMargins(10, 10, 8, 10)
        principal.setSpacing(8)

        encabezado = QHBoxLayout()
        titulo = QLabel("Capas", self)
        titulo.setObjectName("PanelTitle")
        encabezado.addWidget(titulo)
        encabezado.addStretch(1)
        self.btn_agregar = BotonPaint("Agregar capa (Ctrl+Mayús+N)", "add", 32, 32, 18, callback=self.agregarSolicitado.emit, parent=self)
        encabezado.addWidget(self.btn_agregar)
        principal.addLayout(encabezado)

        self.lista = QListWidget(self)
        self.lista.setObjectName("LayersList")
        self.lista.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.lista.setAccessibleName("Lista de capas")
        self.lista.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.lista.setSpacing(2)
        self.lista.currentItemChanged.connect(self._activar_item)
        self.lista.itemDoubleClicked.connect(self._pedir_renombrar)
        principal.addWidget(self.lista, 1)

        fila_opacidad = QHBoxLayout()
        etiqueta = QLabel("Opacidad", self)
        etiqueta.setObjectName("StatusMetric")
        fila_opacidad.addWidget(etiqueta)
        self.slider_opacidad = QSlider(Qt.Orientation.Horizontal, self)
        self.slider_opacidad.setRange(0, 100)
        self.slider_opacidad.setValue(100)
        self.slider_opacidad.setAccessibleName("Opacidad de la capa")
        self.slider_opacidad.sliderPressed.connect(self._iniciar_opacidad)
        self.slider_opacidad.valueChanged.connect(self._cambiar_opacidad)
        self.slider_opacidad.sliderReleased.connect(self._terminar_opacidad)
        fila_opacidad.addWidget(self.slider_opacidad, 1)
        self.valor_opacidad = QLabel("100%", self)
        self.valor_opacidad.setObjectName("StatusMetric")
        self.valor_opacidad.setMinimumWidth(36)
        self.valor_opacidad.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        fila_opacidad.addWidget(self.valor_opacidad)
        principal.addLayout(fila_opacidad)
        self.btn_mas = self.btn_agregar  # compatibilidad

    # La vista solo lee el documento para presentar su estado. Cualquier cambio
    # se solicita mediante señales y lo ejecuta un controlador externo.
    def actualizar(self, document: Any | None = None) -> None:
        if document is not None:
            self.documento = document
        self._actualizando = True
        try:
            posicion = self.lista.verticalScrollBar().value()
            self.lista.clear()
            if self.documento is None:
                return
            capas = list(getattr(self.documento, "layers", []))
            activa = str(getattr(self.documento, "active_layer_id", ""))
            fondo = None
            if bool(getattr(self.documento, "show_background", True)):
                fondo = QColor(getattr(self.documento, "background_color", QColor("white")))
            for indice, capa in reversed(list(enumerate(capas))):
                item = QListWidgetItem(self.lista)
                capa_id = str(getattr(capa, "id", ""))
                item.setData(CAPA_ID_ROLE, capa_id)
                fila = _FilaCapa(capa, fondo if indice == 0 else None, len(capas) == 1, self.lista)
                item.setSizeHint(QSize(0, M.LAYER_THUMBNAIL + 50 + (16 if fila.tiene_detalle else 0)))
                fila.visibilidadCambiada.connect(self.visibilidadSolicitada.emit)
                fila.accionSolicitada.connect(self._accion_de_capa)
                self.lista.setItemWidget(item, fila)
                if capa_id == activa:
                    self.lista.setCurrentItem(item)
            self.lista.verticalScrollBar().setValue(posicion)
            self._actualizar_opacidad_activa()
        finally:
            self._actualizando = False

    def set_document(self, document: Any) -> None:
        self.actualizar(document)

    def current_layer_id(self) -> str:
        item = self.lista.currentItem()
        return str(item.data(CAPA_ID_ROLE)) if item is not None else ""

    def _accion_de_capa(self, capa_id: str, accion: str) -> None:
        if accion == "toggle_visible":
            capa = next((c for c in getattr(self.documento, "layers", []) if str(c.id) == capa_id), None)
            self.visibilidadSolicitada.emit(capa_id, not bool(getattr(capa, "visible", True)))
            return
        capa = next((c for c in getattr(self.documento, "layers", []) if str(c.id) == capa_id), None)
        if accion == "lock":
            self.bloqueoSolicitado.emit(capa_id, not bool(getattr(capa, "locked", False)))
            return
        if accion == "flatten":
            self.acoplarSolicitado.emit()
            return
        if accion.startswith("blend::"):
            self.mezclaSolicitada.emit(capa_id, accion.split("::", 1)[1])
            return
        # Las demás acciones actúan sobre la capa activa: se activa primero.
        if capa_id != str(getattr(self.documento, "active_layer_id", "")):
            self.activarSolicitado.emit(capa_id)
        if accion == "duplicate":
            self.duplicarSolicitado.emit()
        elif accion == "merge":
            self.combinarSolicitado.emit()
        elif accion == "up":
            self.moverSolicitado.emit(capa_id, 1)
        elif accion == "down":
            self.moverSolicitado.emit(capa_id, -1)
        elif accion == "rename":
            self._renombrar(capa_id)
        elif accion == "delete":
            self.eliminarSolicitado.emit()

    def _activar_item(self, actual: QListWidgetItem | None, anterior: QListWidgetItem | None) -> None:
        if self._actualizando or actual is None:
            return
        capa_id = str(actual.data(CAPA_ID_ROLE))
        if capa_id:
            self.activarSolicitado.emit(capa_id)
        self._actualizar_opacidad_activa()

    def _actualizar_opacidad_activa(self) -> None:
        capa_id = self.current_layer_id()
        opacidad = 100
        for capa in getattr(self.documento, "layers", []) if self.documento is not None else []:
            if str(getattr(capa, "id", "")) == capa_id:
                opacidad = round(float(getattr(capa, "opacity", 1.0)) * 100)
                break
        self.slider_opacidad.blockSignals(True)
        self.slider_opacidad.setValue(max(0, min(100, opacidad)))
        self.slider_opacidad.blockSignals(False)
        self.valor_opacidad.setText(f"{opacidad}%")

    def _cambiar_opacidad(self, valor: int) -> None:
        self.valor_opacidad.setText(f"{valor}%")
        if self._actualizando:
            return
        capa_id = self.current_layer_id()
        if capa_id:
            self.opacidadSolicitada.emit(capa_id, valor)

    def _iniciar_opacidad(self) -> None:
        capa_id = self.current_layer_id()
        if capa_id:
            self.opacidadInicioSolicitada.emit(capa_id)

    def _terminar_opacidad(self) -> None:
        capa_id = self.current_layer_id()
        if capa_id:
            self.opacidadFinSolicitada.emit(capa_id)

    def _renombrar(self, capa_id: str) -> None:
        capa = next((c for c in getattr(self.documento, "layers", []) if str(c.id) == capa_id), None)
        nombre, aceptado = QInputDialog.getText(
            self, "Cambiar nombre de capa", "Nombre:", text=str(getattr(capa, "name", "Capa"))
        )
        nombre = nombre.strip()
        if aceptado and nombre:
            self.renombrarSolicitado.emit(capa_id, nombre)

    def _pedir_renombrar(self, item: QListWidgetItem) -> None:
        self._renombrar(str(item.data(CAPA_ID_ROLE)))


LayersPanel = LayersPanelView
