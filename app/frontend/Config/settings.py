from pathlib import Path


APP_NAME = "MelfPaint"
FRONTEND_DIR = Path(__file__).resolve().parents[1]
RESOURCES_DIR = FRONTEND_DIR / "Resources"
ICONS_DIR = RESOURCES_DIR / "icons"


def resource_path(*parts: str) -> Path:
    return RESOURCES_DIR.joinpath(*parts)


def icon_path(name: str) -> Path:
    return ICONS_DIR / f"{name}.svg"
