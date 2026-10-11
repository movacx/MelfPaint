#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ ! -f "$PROJECT_DIR/main.py" ]]; then
    echo "No se encontro el punto de entrada de MelfPaint: $PROJECT_DIR/main.py" >&2
    exit 2
fi

if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "MelfPaint necesita Python 3 y no se encontró en el sistema." >&2
    exit 127
fi

export PYTHONPATH="$PROJECT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON_BIN" "$PROJECT_DIR/main.py" "$@"
