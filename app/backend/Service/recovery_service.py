from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hmac import compare_digest
from pathlib import Path
from uuid import uuid4

from backend.Model.document import Document
from backend.Repository.project_repository import CodecError, ProjectRepository
from backend.Service.xdg_service import obtener_carpeta_cache


@dataclass(frozen=True)
class RecoveryMetadata:
    session_id: str
    project_file: Path
    metadata_file: Path
    saved_at: str
    display_name: str
    original_project_path: Path | None
    source_path: Path | None
    width: int
    height: int
    layer_count: int
    document_modified: bool
    metadata_version: int = 1
    process_id: int | None = None
    process_start_token: str | None = None


class RecoveryService:
    """Mantiene una copia atomica por sesion dentro del cache XDG."""

    METADATA_VERSION = 2
    LEGACY_METADATA_VERSION = 1
    MAX_METADATA_SIZE = 64 * 1024
    SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
    MAX_PROCESS_ID = 2_147_483_647
    MAX_PROCESS_TOKEN_LENGTH = 300
    _FALLBACK_PROCESS_TOKEN = uuid4().hex

    def __init__(
        self,
        repository: ProjectRepository | None = None,
        recovery_directory: Path | str | None = None,
        session_id: str | None = None,
    ) -> None:
        self.repository = repository or ProjectRepository()
        self.recovery_directory = Path(
            recovery_directory or (obtener_carpeta_cache() / "recuperacion")
        ).expanduser().absolute()
        self.session_id = self._validate_session_id(session_id or uuid4().hex)
        self.process_id = os.getpid()
        self.process_start_token = self._process_start_token(self.process_id)
        if self.process_start_token is None:
            # El token aleatorio solo permite reconocer otras instancias de este
            # servicio dentro del proceso actual. Para procesos ajenos, una
            # identidad que no se puede verificar se considera obsoleta.
            self.process_start_token = f"fallback:{self._FALLBACK_PROCESS_TOKEN}"

    @classmethod
    def _validate_session_id(cls, session_id: str) -> str:
        value = str(session_id)
        if not cls.SESSION_PATTERN.fullmatch(value):
            raise ValueError("El identificador de sesion no es valido")
        return value

    def _paths(self, session_id: str) -> tuple[Path, Path]:
        identifier = self._validate_session_id(session_id)
        project = self.recovery_directory / f"{identifier}.melfpaint"
        metadata = self.recovery_directory / f"{identifier}.json"
        return project, metadata

    @classmethod
    def _process_start_token(cls, process_id: int) -> str | None:
        """Obtiene una identidad que cambia cuando el sistema reutiliza un PID."""

        try:
            pid = int(process_id)
        except (TypeError, ValueError):
            return None
        if pid < 1 or pid > cls.MAX_PROCESS_ID:
            return None

        try:
            stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            closing_parenthesis = stat_text.rfind(")")
            if closing_parenthesis < 1:
                return None
            stat_fields = stat_text[closing_parenthesis + 1 :].split()
            # Despues del nombre del proceso, el indice 0 corresponde al campo
            # 3 de proc(5); starttime es el campo 22.
            start_time = stat_fields[19]
            if not start_time.isdecimal():
                return None
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
            if not boot_id or len(boot_id) > 100:
                return None
            return f"linux:{boot_id}:{start_time}"
        except (IndexError, OSError, UnicodeError):
            return None

    @staticmethod
    def _path_text(path: Path | None) -> str | None:
        return str(path) if path is not None else None

    @staticmethod
    def _optional_path(value: object) -> Path | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("La ruta guardada no es valida")
        return Path(value).expanduser().absolute()

    def _metadata_data(
        self,
        document: Document,
        session_id: str,
        display_name: str | None,
    ) -> dict[str, object]:
        name = str(display_name or "").strip()
        if not name:
            path = document.project_path or document.source_path
            name = path.stem if path is not None else "Documento sin titulo"
        return {
            "format": "MelfPaint Recovery",
            "version": self.METADATA_VERSION,
            "session_id": session_id,
            "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "display_name": name[:200],
            "original_project_path": self._path_text(document.project_path),
            "source_path": self._path_text(document.source_path),
            "width": document.width,
            "height": document.height,
            "layer_count": len(document.layers),
            "document_modified": document.modified,
            "process_id": self.process_id,
            "process_start_token": self.process_start_token,
        }

    def _write_metadata(self, path: Path, data: dict[str, object]) -> None:
        encoded = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        if len(encoded) > self.MAX_METADATA_SIZE:
            raise CodecError("Los metadatos de recuperacion exceden el limite")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(encoded)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        except OSError as error:
            raise CodecError(f"No se pudieron guardar los metadatos de recuperacion: {error}") from error
        finally:
            temporary.unlink(missing_ok=True)

    def save(
        self,
        document: Document,
        session_id: str | None = None,
        display_name: str | None = None,
    ) -> RecoveryMetadata:
        identifier = self._validate_session_id(session_id or self.session_id)
        project_file, metadata_file = self._paths(identifier)
        self.recovery_directory.mkdir(parents=True, exist_ok=True)

        original_project_path = document.project_path
        original_source_path = document.source_path
        original_export_path = document.last_export_path
        original_modified = document.modified
        data = self._metadata_data(document, identifier, display_name)
        try:
            self.repository.save_recovery(document, project_file)
            self._write_metadata(metadata_file, data)
        finally:
            # Una implementacion de repositorio inyectada tampoco puede cambiar la identidad.
            document.project_path = original_project_path
            document.source_path = original_source_path
            document.last_export_path = original_export_path
            document.modified = original_modified
        return self._metadata_from_data(data, project_file, metadata_file)

    guardar = save
    autosave = save

    def _metadata_from_data(
        self,
        data: object,
        project_file: Path,
        metadata_file: Path,
    ) -> RecoveryMetadata:
        if not isinstance(data, dict) or data.get("format") != "MelfPaint Recovery":
            raise ValueError("Los metadatos no pertenecen a MelfPaint")
        try:
            version = int(data.get("version", 0))
            session_id = self._validate_session_id(str(data["session_id"]))
            saved_at = str(data["saved_at"])
            display_name = str(data.get("display_name", "Documento sin titulo"))
            width = int(data["width"])
            height = int(data["height"])
            layer_count = int(data["layer_count"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Los metadatos de recuperacion son invalidos") from error
        if version not in {self.LEGACY_METADATA_VERSION, self.METADATA_VERSION}:
            raise ValueError("La version de recuperacion no es compatible")
        if metadata_file.stem != session_id or project_file.stem != session_id:
            raise ValueError("La sesion no coincide con sus archivos")
        if width < 1 or height < 1 or layer_count < 1:
            raise ValueError("Las dimensiones de recuperacion son invalidas")

        process_id: int | None = None
        process_start_token: str | None = None
        if version >= 2:
            try:
                raw_process_id = data["process_id"]
                raw_process_token = data["process_start_token"]
                if isinstance(raw_process_id, bool) or not isinstance(raw_process_token, str):
                    raise TypeError
                process_id = int(raw_process_id)
                process_start_token = raw_process_token
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("La identidad del proceso de recuperacion es invalida") from error
            if process_id < 1 or process_id > self.MAX_PROCESS_ID:
                raise ValueError("El proceso de recuperacion no es valido")
            if (
                not process_start_token
                or len(process_start_token) > self.MAX_PROCESS_TOKEN_LENGTH
                or not process_start_token.isprintable()
                or not process_start_token.isascii()
            ):
                raise ValueError("El token del proceso de recuperacion no es valido")
        return RecoveryMetadata(
            session_id=session_id,
            project_file=project_file,
            metadata_file=metadata_file,
            saved_at=saved_at,
            display_name=display_name[:200],
            original_project_path=self._optional_path(data.get("original_project_path")),
            source_path=self._optional_path(data.get("source_path")),
            width=width,
            height=height,
            layer_count=layer_count,
            document_modified=bool(data.get("document_modified", True)),
            metadata_version=version,
            process_id=process_id,
            process_start_token=process_start_token,
        )

    def _read_metadata(self, path: Path) -> RecoveryMetadata:
        if path.stat().st_size > self.MAX_METADATA_SIZE:
            raise ValueError("Los metadatos exceden el limite")
        data = json.loads(path.read_text(encoding="utf-8"))
        project_file, metadata_file = self._paths(path.stem)
        if not project_file.is_file():
            raise ValueError("Falta el proyecto de recuperacion")
        return self._metadata_from_data(data, project_file, metadata_file)

    def list_recoveries(self) -> list[RecoveryMetadata]:
        if not self.recovery_directory.is_dir():
            return []
        recoveries: list[RecoveryMetadata] = []
        for metadata_file in self.recovery_directory.glob("*.json"):
            try:
                recoveries.append(self._read_metadata(metadata_file))
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                continue
        recoveries.sort(key=lambda item: item.saved_at, reverse=True)
        return recoveries

    listar = list_recoveries

    def _is_live(self, recovery: RecoveryMetadata) -> bool:
        if (
            recovery.metadata_version < 2
            or recovery.process_id is None
            or recovery.process_start_token is None
        ):
            return False

        running_token = self._process_start_token(recovery.process_id)
        if running_token is not None:
            return compare_digest(running_token, recovery.process_start_token)

        # Si /proc no esta disponible, solo reconocemos con certeza al proceso
        # propio. Una identidad ajena incierta se muestra como recuperable.
        return recovery.process_id == self.process_id and compare_digest(
            self.process_start_token,
            recovery.process_start_token,
        )

    def list_stale_recoveries(self) -> list[RecoveryMetadata]:
        """Lista copias cuyo proceso propietario ya no puede verificarse vivo."""

        return [recovery for recovery in self.list_recoveries() if not self._is_live(recovery)]

    listar_obsoletas = list_stale_recoveries

    def load(self, recovery: RecoveryMetadata | str | None = None) -> Document:
        if isinstance(recovery, RecoveryMetadata):
            identifier = self._validate_session_id(recovery.session_id)
        else:
            identifier = self._validate_session_id(recovery or self.session_id)
        _, metadata_file = self._paths(identifier)
        try:
            metadata = self._read_metadata(metadata_file)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise CodecError("La recuperacion esta incompleta o danada") from error

        document = self.repository.load_project(metadata.project_file)
        document.project_path = metadata.original_project_path
        document.source_path = metadata.source_path
        document.last_export_path = None
        document.modified = metadata.document_modified
        return document

    recuperar = load

    def discard(self, recovery: RecoveryMetadata | str | None = None) -> bool:
        if isinstance(recovery, RecoveryMetadata):
            identifier = self._validate_session_id(recovery.session_id)
        else:
            identifier = self._validate_session_id(recovery or self.session_id)
        project_file, metadata_file = self._paths(identifier)
        existed = project_file.exists() or metadata_file.exists()
        project_file.unlink(missing_ok=True)
        metadata_file.unlink(missing_ok=True)
        return existed

    descartar = discard

    def discard_all(self) -> int:
        if not self.recovery_directory.is_dir():
            return 0
        identifiers: set[str] = set()
        for pattern in ("*.json", "*.melfpaint"):
            for path in self.recovery_directory.glob(pattern):
                try:
                    identifiers.add(self._validate_session_id(path.stem))
                except ValueError:
                    continue
        for identifier in identifiers:
            self.discard(identifier)
        return len(identifiers)

    descartar_todas = discard_all
