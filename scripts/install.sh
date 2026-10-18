#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
APP_SRC="$REPO_DIR/app"
PACKAGING_DIR="$REPO_DIR/packaging/common"
APP_ID="io.github.movacx.MelfPaint"
SKIP_DEPS=0
STAGING_DIR=""
OLD_APP_DIR=""

mostrar_ayuda() {
    cat <<'AYUDA'
Instalador local de MelfPaint

Uso:
  scripts/install.sh [--skip-deps]
  PREFIX="$HOME/.local" scripts/install.sh [--skip-deps]
  sudo PREFIX=/usr/local scripts/install.sh

Para instalar como paquete del sistema use los paquetes .deb, .rpm o de
Arch que genera packaging/build-packages.sh.

Opciones:
  --skip-deps   Usa el Python del sistema y no descarga dependencias.
  -h, --help    Muestra esta ayuda.
AYUDA
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-deps) SKIP_DEPS=1 ;;
        -h|--help) mostrar_ayuda; exit 0 ;;
        *) echo "Opcion desconocida: $1" >&2; mostrar_ayuda; exit 2 ;;
    esac
    shift
done

if [[ -z "${PREFIX:-}" ]]; then
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        PREFIX="/usr/local"
    else
        PREFIX="${HOME:?No se pudo determinar HOME}/.local"
    fi
fi

normalizar_prefijo() {
    local recibido="$1"
    if [[ "$recibido" != /* || "$recibido" == *$'\n'* || "$recibido" == *$'\r'* ]]; then
        echo "Error: PREFIX debe ser una ruta absoluta sin saltos de linea." >&2
        exit 2
    fi
    if ! command -v realpath >/dev/null 2>&1; then
        echo "Error: se necesita realpath para validar la ruta de instalacion." >&2
        exit 127
    fi
    recibido="$(realpath -m -- "$recibido")"
    if [[ -z "$recibido" || "$recibido" == "/" ]]; then
        echo "Error: no se permite instalar directamente sobre la raiz del sistema." >&2
        exit 2
    fi
    printf '%s\n' "$recibido"
}

PREFIX="$(normalizar_prefijo "$PREFIX")"
APP_DIR="$PREFIX/share/melfpaint"
BIN_DIR="$PREFIX/bin"
DESKTOP_DIR="$PREFIX/share/applications"
ICON_DIR="$PREFIX/share/icons/hicolor/scalable/apps"
DOC_DIR="$PREFIX/share/doc/melfpaint"
MIME_DIR="$PREFIX/share/mime/packages"
LAUNCHER="$BIN_DIR/melfpaint"
DESKTOP_FILE="$DESKTOP_DIR/$APP_ID.desktop"
ICON_FILE="$ICON_DIR/$APP_ID.svg"
MIME_FILE="$MIME_DIR/$APP_ID.xml"

validar_componentes() {
    local destino="$1"
    local relativo="${destino#"$PREFIX"/}"
    local actual="$PREFIX"
    local parte
    if [[ "$destino" != "$PREFIX/"* ]]; then
        echo "Error: el destino escapa de PREFIX: $destino" >&2
        exit 2
    fi
    IFS='/' read -r -a partes <<< "$relativo"
    for parte in "${partes[@]}"; do
        actual="$actual/$parte"
        if [[ -L "$actual" ]]; then
            echo "Error: no se escribe a traves de enlaces simbolicos: $actual" >&2
            exit 2
        fi
    done
}

for destino in "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR" "$DOC_DIR" "$MIME_DIR"; do
    validar_componentes "$destino"
done

if [[ -e "$APP_DIR" ]]; then
    if [[ ! -f "$APP_DIR/.melfpaint-install" ]] \
        || ! grep -qx 'MELFPAINT_INSTALL_V1' "$APP_DIR/.melfpaint-install"; then
        echo "Error: $APP_DIR ya existe y no pertenece a este instalador." >&2
        echo "Mueva esa carpeta manualmente antes de instalar para no sobrescribir datos ajenos." >&2
        exit 2
    fi
fi

limpiar_temporales() {
    local estado=$?
    if [[ -n "$STAGING_DIR" && -e "$STAGING_DIR" ]]; then
        rm -rf -- "$STAGING_DIR"
    fi
    if [[ -n "$OLD_APP_DIR" && -e "$OLD_APP_DIR" ]]; then
        rm -rf -- "$OLD_APP_DIR"
    fi
    return "$estado"
}
trap limpiar_temporales EXIT

ARCHIVOS_REQUERIDOS=(
    "$APP_SRC/main.py"
    "$APP_SRC/version.py"
    "$APP_SRC/requirements.txt"
    "$REPO_DIR/README.md"
    "$SCRIPT_DIR/uninstall.sh"
    "$PACKAGING_DIR/$APP_ID.desktop"
    "$PACKAGING_DIR/$APP_ID.xml"
    "$APP_SRC/frontend/Resources/app-icons/melfpaint.svg"
)

for archivo in "${ARCHIVOS_REQUERIDOS[@]}"; do
    if [[ ! -f "$archivo" ]]; then
        echo "Error: falta un archivo requerido: $archivo" >&2
        exit 1
    fi
done
if [[ ! -d "$APP_SRC/backend" || ! -d "$APP_SRC/frontend" ]]; then
    echo "Error: la estructura frontend/backend de MelfPaint esta incompleta." >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: MelfPaint necesita Python 3.11 o superior." >&2
    exit 127
fi
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else "MelfPaint necesita Python 3.11 o superior")'

install -dm755 "$PREFIX/share" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR" "$DOC_DIR" "$MIME_DIR"
STAGING_DIR="$(mktemp -d "$PREFIX/share/.melfpaint-stage.XXXXXX")"
STAGING_APP="$STAGING_DIR/melfpaint"
install -dm755 "$STAGING_APP"

cp -a -- "$APP_SRC/backend" "$STAGING_APP/backend"
cp -a -- "$APP_SRC/frontend" "$STAGING_APP/frontend"
find "$STAGING_APP" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
find "$STAGING_APP" -type d -name '__pycache__' -empty -delete

install -m644 "$APP_SRC/main.py" "$STAGING_APP/main.py"
install -m644 "$APP_SRC/version.py" "$STAGING_APP/version.py"
install -m644 "$APP_SRC/requirements.txt" "$STAGING_APP/requirements.txt"
install -m755 "$SCRIPT_DIR/uninstall.sh" "$STAGING_APP/uninstall.sh"

if [[ "$SKIP_DEPS" -eq 0 ]]; then
    if ! python3 -m venv --system-site-packages "$STAGING_APP/.venv"; then
        echo "No se pudo crear el entorno virtual. Instala python3-venv o usa --skip-deps." >&2
        exit 1
    fi
    if ! "$STAGING_APP/.venv/bin/python" -c 'import PySide6, numpy' >/dev/null 2>&1; then
        echo "Instalando dependencias de MelfPaint en su entorno local..."
        "$STAGING_APP/.venv/bin/python" -m pip install --disable-pip-version-check -r "$STAGING_APP/requirements.txt"
    fi
    APP_PYTHON="$STAGING_APP/.venv/bin/python"
else
    APP_PYTHON="$(command -v python3)"
fi

PYTHONDONTWRITEBYTECODE=1 "$APP_PYTHON" -m compileall -q "$STAGING_APP/backend" "$STAGING_APP/frontend" "$STAGING_APP/main.py" "$STAGING_APP/version.py"
{
    printf '%s\n' 'MELFPAINT_INSTALL_V1'
    printf 'PREFIX=%s\n' "$PREFIX"
} > "$STAGING_APP/.melfpaint-install"
chmod 644 "$STAGING_APP/.melfpaint-install"

if [[ -e "$APP_DIR" || -L "$APP_DIR" ]]; then
    OLD_APP_DIR="$(mktemp -d "$PREFIX/share/.melfpaint-old.XXXXXX")"
    rmdir -- "$OLD_APP_DIR"
    mv -- "$APP_DIR" "$OLD_APP_DIR"
fi
mv -- "$STAGING_APP" "$APP_DIR"
rm -rf -- "$STAGING_DIR"
STAGING_DIR=""
if [[ -n "$OLD_APP_DIR" ]]; then
    rm -rf -- "$OLD_APP_DIR"
    OLD_APP_DIR=""
fi

launcher_temp="$(mktemp "$BIN_DIR/.melfpaint-launcher.XXXXXX")"
{
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' 'set -euo pipefail'
    printf 'APP_DIR=%q\n' "$APP_DIR"
    printf '%s\n' 'if [[ -x "$APP_DIR/.venv/bin/python" ]]; then'
    printf '%s\n' '    exec "$APP_DIR/.venv/bin/python" "$APP_DIR/main.py" "$@"'
    printf '%s\n' 'fi'
    printf '%s\n' 'exec python3 "$APP_DIR/main.py" "$@"'
} > "$launcher_temp"
chmod 755 "$launcher_temp"
mv -fT -- "$launcher_temp" "$LAUNCHER"

escapar_argumento_desktop() {
    local entrada="$1"
    local salida=""
    local caracter
    local indice
    for ((indice = 0; indice < ${#entrada}; indice++)); do
        caracter="${entrada:indice:1}"
        case "$caracter" in
            '\') salida+='\\\\' ;;
            '"') salida+='\\"' ;;
            '$') salida+='\\$' ;;
            '`') salida+='\\`' ;;
            '%') salida+='%%' ;;
            *) salida+="$caracter" ;;
        esac
    done
    printf '%s' "$salida"
}

desktop_path="$(escapar_argumento_desktop "$LAUNCHER")"
desktop_temp="$(mktemp "$DESKTOP_DIR/.melfpaint-desktop.XXXXXX")"
while IFS= read -r linea_desktop || [[ -n "$linea_desktop" ]]; do
    if [[ "$linea_desktop" == Exec=melfpaint\ %F ]]; then
        printf 'Exec="%s" %%F\n' "$desktop_path"
    elif [[ "$linea_desktop" == Exec=melfpaint ]]; then
        printf 'Exec="%s"\n' "$desktop_path"
    elif [[ "$linea_desktop" == TryExec=* ]]; then
        printf 'TryExec=%s\n' "$desktop_path"
    else
        printf '%s\n' "$linea_desktop"
    fi
done < "$PACKAGING_DIR/$APP_ID.desktop" > "$desktop_temp"
chmod 644 "$desktop_temp"
mv -- "$desktop_temp" "$DESKTOP_FILE"

instalar_archivo_atomico() {
    local origen="$1"
    local destino="$2"
    local modo="$3"
    local temporal
    temporal="$(mktemp "$(dirname -- "$destino")/.melfpaint-file.XXXXXX")"
    install -m"$modo" "$origen" "$temporal"
    mv -fT -- "$temporal" "$destino"
}

instalar_archivo_atomico "$APP_SRC/frontend/Resources/app-icons/melfpaint.svg" "$ICON_FILE" 644
instalar_archivo_atomico "$PACKAGING_DIR/$APP_ID.xml" "$MIME_FILE" 644
instalar_archivo_atomico "$REPO_DIR/README.md" "$DOC_DIR/README.md" 644

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true
fi
if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database "$PREFIX/share/mime" >/dev/null 2>&1 || true
fi

echo "MelfPaint fue instalado correctamente en: $APP_DIR"
echo "Ejecutable: $LAUNCHER"
echo "Desinstalar: $APP_DIR/uninstall.sh"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "Nota: $BIN_DIR no esta en PATH. Puedes ejecutar $LAUNCHER directamente." ;;
esac
