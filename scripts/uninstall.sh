#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/$(basename -- "${BASH_SOURCE[0]}")"
YES=0
DRY_RUN=0
PURGE_DATA=0

mostrar_ayuda() {
    cat <<'AYUDA'
Desinstalador local de MelfPaint

Uso:
  ./uninstall.sh [opciones]
  PREFIX="$HOME/.local" ./uninstall.sh [opciones]

Opciones:
  -y, --yes       No pide confirmacion.
  --dry-run       Muestra que quitaria, sin borrar nada.
  --purge-data    Borra preferencias y cache internos de MelfPaint.
  -h, --help      Muestra esta ayuda.

Las imagenes y proyectos guardados por el usuario nunca se eliminan.
AYUDA
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes) YES=1 ;;
        --dry-run) DRY_RUN=1 ;;
        --purge-data) PURGE_DATA=1 ;;
        -h|--help) mostrar_ayuda; exit 0 ;;
        *) echo "Opcion desconocida: $1" >&2; mostrar_ayuda; exit 2 ;;
    esac
    shift
done

if [[ -z "${PREFIX:-}" ]]; then
    if [[ "$SCRIPT_PATH" == */share/melfpaint/uninstall.sh ]]; then
        PREFIX="${SCRIPT_PATH%/share/melfpaint/uninstall.sh}"
    elif [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        PREFIX="/usr/local"
    else
        PREFIX="${HOME:?No se pudo determinar HOME}/.local"
    fi
fi

normalizar_base() {
    local recibido="$1"
    if [[ "$recibido" != /* || "$recibido" == *$'\n'* || "$recibido" == *$'\r'* ]]; then
        echo "Ruta base invalida: $recibido" >&2
        exit 2
    fi
    if ! command -v realpath >/dev/null 2>&1; then
        echo "Se necesita realpath para validar la desinstalacion." >&2
        exit 127
    fi
    recibido="$(realpath -m -- "$recibido")"
    if [[ -z "$recibido" || "$recibido" == "/" ]]; then
        echo "No se permite usar la raiz como prefijo." >&2
        exit 2
    fi
    printf '%s\n' "$recibido"
}

PREFIX="$(normalizar_base "$PREFIX")"
APP_DIR="$PREFIX/share/melfpaint"
BIN_FILE="$PREFIX/bin/melfpaint"
DESKTOP_FILE="$PREFIX/share/applications/io.github.melfpaint.MelfPaint.desktop"
ICON_FILE="$PREFIX/share/icons/hicolor/scalable/apps/io.github.melfpaint.MelfPaint.svg"
DOC_DIR="$PREFIX/share/doc/melfpaint"
MIME_FILE="$PREFIX/share/mime/packages/io.github.melfpaint.MelfPaint.xml"
MARKER="$APP_DIR/.melfpaint-install"

validar_padre() {
    local ruta="$1"
    local base="$2"
    local padre
    padre="$(realpath -m -- "$(dirname -- "$ruta")")"
    case "$padre" in
        "$base"|"$base"/*) ;;
        *) echo "Se cancela: el padre de $ruta escapa de $base." >&2; exit 1 ;;
    esac
}

for objetivo in "$APP_DIR" "$BIN_FILE" "$DESKTOP_FILE" "$ICON_FILE" "$DOC_DIR" "$MIME_FILE"; do
    validar_padre "$objetivo" "$PREFIX"
done

if [[ ! -f "$MARKER" ]] || ! grep -Fqx 'MELFPAINT_INSTALL_V1' "$MARKER" \
    || ! grep -Fqx "PREFIX=$PREFIX" "$MARKER"; then
    echo "Se cancela: $APP_DIR no contiene una instalacion registrada de MelfPaint." >&2
    exit 1
fi

CONFIG_DIR=""
DATA_DIR=""
CACHE_DIR=""
if [[ "$PURGE_DATA" -eq 1 ]]; then
    CONFIG_BASE="$(normalizar_base "${XDG_CONFIG_HOME:-${HOME:?}/.config}")"
    DATA_BASE="$(normalizar_base "${XDG_DATA_HOME:-${HOME:?}/.local/share}")"
    CACHE_BASE="$(normalizar_base "${XDG_CACHE_HOME:-${HOME:?}/.cache}")"
    CONFIG_DIR="$CONFIG_BASE/melfpaint"
    DATA_DIR="$DATA_BASE/melfpaint"
    CACHE_DIR="$CACHE_BASE/melfpaint"
fi

es_objetivo_permitido() {
    local ruta="$1"
    case "$ruta" in
        "$APP_DIR"|"$BIN_FILE"|"$DESKTOP_FILE"|"$ICON_FILE"|"$DOC_DIR"|"$MIME_FILE") return 0 ;;
        "$CONFIG_DIR"|"$DATA_DIR"|"$CACHE_DIR") [[ "$PURGE_DATA" -eq 1 && -n "$ruta" ]] ; return ;;
        *) return 1 ;;
    esac
}

quitar() {
    local ruta="$1"
    if ! es_objetivo_permitido "$ruta"; then
        echo "Objetivo no permitido; se cancela: $ruta" >&2
        exit 1
    fi
    if [[ -e "$ruta" || -L "$ruta" ]]; then
        echo "Quitando: $ruta"
        if [[ "$DRY_RUN" -eq 0 ]]; then
            rm -rf -- "$ruta"
        fi
    fi
}

cat <<INFO
== Desinstalacion local de MelfPaint ==
Prefijo: $PREFIX

Se quitaran unicamente:
- $APP_DIR
- $BIN_FILE
- $DESKTOP_FILE
- $ICON_FILE
- $DOC_DIR
- $MIME_FILE
INFO

if [[ "$PURGE_DATA" -eq 1 ]]; then
    cat <<INFO

Tambien se quitaran datos internos de la aplicacion:
- $CONFIG_DIR
- $DATA_DIR
- $CACHE_DIR
INFO
fi

if [[ "$YES" -ne 1 && "$DRY_RUN" -ne 1 ]]; then
    read -r -p "Escribe MELFPAINT para continuar: " CONFIRMACION
    if [[ "$CONFIRMACION" != "MELFPAINT" ]]; then
        echo "Desinstalacion cancelada."
        exit 0
    fi
fi

quitar "$BIN_FILE"
quitar "$DESKTOP_FILE"
quitar "$ICON_FILE"
quitar "$DOC_DIR"
quitar "$MIME_FILE"
if [[ "$PURGE_DATA" -eq 1 ]]; then
    quitar "$CONFIG_DIR"
    quitar "$DATA_DIR"
    quitar "$CACHE_DIR"
fi
quitar "$APP_DIR"

if [[ "$DRY_RUN" -eq 0 ]]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$PREFIX/share/applications" >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true
    fi
    if command -v update-mime-database >/dev/null 2>&1; then
        update-mime-database "$PREFIX/share/mime" >/dev/null 2>&1 || true
    fi
fi

echo "Desinstalacion terminada. Los documentos personales se conservaron."
