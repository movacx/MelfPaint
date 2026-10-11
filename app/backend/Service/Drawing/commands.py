"""Reexporta los comandos oficiales sin duplicar el modelo del historial."""

from backend.Service.history_service import LayerImageCommand

SelectionImageCommand = LayerImageCommand

__all__ = ["LayerImageCommand", "SelectionImageCommand"]
