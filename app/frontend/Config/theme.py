from frontend.Config.settings import icon_path


FONT_FAMILY = "'Segoe UI Variable Text', 'Segoe UI', 'Noto Sans', 'Cantarell', sans-serif"


def colors(dark: bool = False) -> dict[str, str]:
    return _dark_colors() if dark else _light_colors()


def stylesheet(dark: bool = False) -> str:
    c = colors(dark)
    sufijo = "-dark" if dark else ""
    chevron = icon_path("chevron-down" + sufijo).as_posix()
    chevron_up = icon_path("chevron-up" + sufijo).as_posix()
    chevron_right = icon_path("chevron-right" + sufijo).as_posix()
    check = icon_path("check" + sufijo).as_posix()
    check_indicador = icon_path("check-black" if dark else "check-white").as_posix()

    return f"""
    QMainWindow, QDialog {{
        background: {c['window']};
        color: {c['text']};
    }}
    QWidget {{
        color: {c['text']};
        font-family: {FONT_FAMILY};
        font-size: 12px;
    }}

    QFrame#PaintTitleBar, QFrame#AppBar {{ background: {c['chrome']}; border: none; }}
    QLabel#TitleBarText {{ background: transparent; color: {c['title_text']}; font-size: 12px; }}
    QLabel#TitleBarIcon {{ background: transparent; }}

    QToolButton#TopMenuButton {{
        background: transparent;
        border: none;
        border-radius: 4px;
        color: {c['menu_text']};
        font-size: 14px;
        padding: 0 12px;
    }}
    QToolButton#TopMenuButton:hover {{ background: {c['hover']}; }}
    QToolButton#TopMenuButton:pressed, QToolButton#TopMenuButton:open {{ background: {c['pressed']}; }}
    QToolButton#TopMenuButton::menu-indicator {{ image: none; width: 0; }}
    QFrame#AppBarSeparator {{ background: {c['separator']}; border: none; }}

    QFrame#PaintRibbon {{ background: {c['ribbon']}; border: none; }}
    QFrame#RibbonGroups {{ background: {c['ribbon']}; border: none; border-bottom: 1px solid {c['ribbon_border']}; }}
    QFrame#RibbonGroup {{ background: transparent; border: none; }}
    QFrame#RibbonGroupPopup {{ background: {c['ribbon']}; border: 1px solid {c['menu_border']}; border-radius: 8px; }}
    QLabel#RibbonGroupTitle {{ background: transparent; color: {c['label']}; font-size: 12px; }}

    QWidget#PaintWorkspace, QFrame#CanvasView,
    QScrollArea#CanvasScrollArea, QScrollArea#CanvasScrollArea > QWidget > QWidget {{
        background: {c['workspace']};
        border: none;
    }}
    QFrame#PaintStatusBar {{
        background: {c['chrome']};
        border: none;
        border-top: 1px solid {c['status_border']};
    }}
    QLabel#StatusMetric {{ background: transparent; color: {c['status_text']}; font-size: 12px; }}

    QToolButton {{
        border: 1px solid transparent;
        border-radius: 4px;
        background: transparent;
        padding: 0;
    }}
    QToolButton:hover {{ background: {c['hover']}; }}
    QToolButton:pressed {{ background: {c['pressed']}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {{
        background: {c['input']};
        color: {c['text']};
        border: 1px solid {c['input_border']};
        border-bottom: 1px solid {c['input_bottom']};
        border-radius: 4px;
        padding: 4px 8px;
        min-height: 22px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QComboBox:focus, QFontComboBox:focus {{ border-bottom: 2px solid {c['accent']}; }}
    QSpinBox, QDoubleSpinBox {{ padding-right: 26px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-origin: border; subcontrol-position: top right;
        width: 24px; border: none; background: transparent; border-top-right-radius: 4px;
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border; subcontrol-position: bottom right;
        width: 24px; border: none; background: transparent; border-bottom-right-radius: 4px;
    }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {c['hover']}; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({chevron_up}); width: 12px; height: 12px; }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}
    QLabel#DialogTitle {{ font-size: 20px; font-weight: 600; background: transparent; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{
        background: {c['menu']};
        color: {c['text']};
        selection-background-color: {c['hover']};
        selection-color: {c['text']};
        border: 1px solid {c['menu_border']};
        outline: none;
    }}

    QPushButton {{
        background: {c['button']};
        color: {c['text']};
        border: 1px solid {c['input_border']};
        border-bottom: 1px solid {c['input_bottom']};
        border-radius: 4px;
        padding: 6px 16px;
        min-height: 20px;
    }}
    QPushButton:hover {{ background: {c['button_hover']}; }}
    QPushButton:pressed {{ background: {c['pressed']}; color: {c['label']}; }}
    QPushButton#PrimaryButton, QPushButton:default {{
        background: {c['accent']};
        color: {c['accent_text']};
        border: 1px solid {c['accent']};
    }}
    QPushButton#PrimaryButton:hover, QPushButton:default:hover {{ background: {c['accent_hover']}; }}

    QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; min-height: 22px; }}
    QRadioButton::indicator {{
        width: 18px; height: 18px; border-radius: 10px;
        border: 1px solid {c['input_bottom']}; background: {c['input']};
    }}
    QRadioButton::indicator:hover {{ background: {c['hover']}; }}
    QRadioButton::indicator:checked {{
        border: 5px solid {c['accent']}; width: 10px; height: 10px; background: {c['accent_text']};
    }}
    QRadioButton::indicator:disabled {{ border-color: {c['disabled']}; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px; border-radius: 4px;
        border: 1px solid {c['input_bottom']}; background: {c['input']};
    }}
    QCheckBox::indicator:hover {{ background: {c['hover']}; }}
    QCheckBox::indicator:checked {{
        border: 1px solid {c['accent']}; background: {c['accent']}; image: url({check_indicador});
    }}
    QCheckBox::indicator:disabled {{ border-color: {c['disabled']}; }}
    QGroupBox {{
        border: 1px solid {c['separator']};
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 10px;
        background: transparent;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}

    QListWidget {{
        background: {c['panel']};
        color: {c['text']};
        border: 1px solid {c['separator']};
        border-radius: 6px;
        outline: none;
        padding: 3px;
    }}
    QListWidget::item {{ border-radius: 4px; padding: 2px; }}
    QListWidget::item:selected {{ background: {c['hover']}; color: {c['text']}; }}
    QLabel#Toast {{
        background: {c['menu']};
        color: {c['text']};
        border: 1px solid {c['menu_border']};
        border-radius: 6px;
        padding: 0 16px;
        font-size: 13px;
    }}
    QLabel#PanelTitle {{ font-size: 14px; font-weight: 600; background: transparent; }}
    QListWidget#LayersList {{ background: transparent; border: none; padding: 0; }}
    QListWidget#LayersList::item {{ border-radius: 6px; border: 1px solid transparent; }}
    QListWidget#LayersList::item:hover {{ background: {c['hover']}; }}
    QListWidget#LayersList::item:selected {{ background: {c['checked_bg']}; border: 1px solid {c['checked_border']}; }}
    QFrame#LayersPanel {{ background: {c['panel']}; border: none; border-left: 1px solid {c['separator']}; }}
    QLabel#LayerThumbnail {{ background: {c['input']}; border: 1px solid {c['separator']}; border-radius: 4px; }}

    QFrame#TextToolbarHost {{ background: transparent; border: none; }}
    QFrame#TextToolbarSurface {{
        background: {c['menu']};
        border: 1px solid {c['menu_border']};
        border-radius: 8px;
    }}
    QFrame#TextToolbarSeparator {{ background: {c['separator']}; border: none; }}
    QToolButton#TextFormatButton:checked {{ background: {c['pressed']}; }}
    QCheckBox#BackgroundFillCheck {{ spacing: 7px; }}
    QFrame#StrokeSizeRail {{ background: transparent; border: none; }}
    QFrame#RailPill {{ background: {c['menu']}; border: 1px solid {c['menu_border']}; border-radius: 14px; }}
    QFrame#RailPill QLabel {{ background: transparent; border: none; }}
    QLabel#RailPreview, QLabel#RailValue {{ background: transparent; font-size: 10px; }}

    QSlider::groove:horizontal {{ height: 4px; background: {c['slider']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: {c['accent']};
        width: 10px; height: 10px; margin: -6px 0;
        border: 3px solid {c['menu']};
        border-radius: 8px;
    }}
    QSlider::groove:vertical {{ width: 4px; background: {c['slider']}; border-radius: 2px; }}
    QSlider::add-page:vertical {{ background: {c['accent']}; border-radius: 2px; }}
    QSlider::handle:vertical {{
        background: {c['accent']};
        width: 10px; height: 10px; margin: 0 -6px;
        border: 3px solid {c['menu']};
        border-radius: 8px;
    }}

    QMenu {{
        background: {c['menu']};
        color: {c['text']};
        border: 1px solid {c['menu_border']};
        border-radius: 8px;
        padding: 4px;
        font-size: 14px;
    }}
    QMenu::item {{
        min-height: 22px;
        padding: 6px 36px 6px 12px;
        border-radius: 4px;
        margin: 1px 0;
    }}
    QMenu::item:selected {{ background: {c['hover']}; }}
    QMenu::item:disabled {{ color: {c['disabled']}; }}
    QMenu::icon {{ padding-left: 12px; }}
    QMenu::separator {{ height: 1px; background: {c['separator']}; margin: 4px 0; }}
    QMenu::right-arrow {{ image: url({chevron_right}); width: 14px; height: 14px; margin-right: 6px; }}
    QMenu::indicator {{ width: 16px; height: 16px; margin-left: 8px; }}
    QMenu::indicator:checked {{ image: url({check}); }}
    QMenu::item:checked {{ padding-left: 12px; }}

    QScrollBar:vertical, QScrollBar:horizontal {{ background: transparent; border: none; margin: 0; }}
    QScrollBar:vertical {{ width: 12px; }}
    QScrollBar:horizontal {{ height: 12px; }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {c['scroll_thumb']};
        border: 4px solid transparent;
        border-radius: 6px;
        min-width: 28px;
        min-height: 28px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QToolTip {{
        background: {c['menu']};
        color: {c['text']};
        border: 1px solid {c['menu_border']};
        padding: 4px 8px;
    }}
    QTabWidget::pane {{ border: 1px solid {c['separator']}; }}
    QTabBar::tab {{ background: {c['button']}; border: 1px solid {c['separator']}; padding: 6px 14px; }}
    QTabBar::tab:selected {{ background: {c['hover']}; }}
    """


def _light_colors() -> dict[str, str]:
    return {
        "window": "#f3f3f3",
        "chrome": "#f3f3f3",
        "ribbon": "#f9f9f9",
        "ribbon_border": "#ebebeb",
        "workspace": "#f8f8f8",
        "panel": "#fbfbfb",
        "menu": "#f9f9f9",
        "menu_border": "#e0e0e0",
        "text": "#1a1a1a",
        "title_text": "#1a1a1a",
        "menu_text": "#262626",
        "status_text": "#242424",
        "label": "#6b6b6b",
        "disabled": "#a0a0a0",
        "separator": "#e5e5e5",
        "status_border": "#ebebeb",
        "hover": "#ededed",
        "pressed": "#e6e6e6",
        "checked_bg": "#ffffff",
        "checked_border": "#8db4a2",
        "input": "#ffffff",
        "input_border": "#e5e5e5",
        "input_bottom": "#8a8a8a",
        "button": "#fdfdfd",
        "button_hover": "#f6f6f6",
        "accent": "#00b45e",
        "accent_hover": "#00a254",
        "accent_text": "#ffffff",
        "slider": "#8a8a8a",
        "scroll_thumb": "#8a8a8a",
        "gallery": "#fafafa",
        "gallery_border": "#efefef",
        "icon": "#424242",
        "swatch_border": "#b3b3b3",
        "canvas_border": "#e3e3e3",
        "handle_border": "#6f6f6f",
    }


def _dark_colors() -> dict[str, str]:
    return {
        "window": "#202020",
        "chrome": "#202020",
        "ribbon": "#2b2b2b",
        "ribbon_border": "#1d1d1d",
        "workspace": "#191919",
        "panel": "#272727",
        "menu": "#2c2c2c",
        "menu_border": "#3a3a3a",
        "text": "#ffffff",
        "title_text": "#ffffff",
        "menu_text": "#f2f2f2",
        "status_text": "#e6e6e6",
        "label": "#a8a8a8",
        "disabled": "#6e6e6e",
        "separator": "#3a3a3a",
        "status_border": "#1d1d1d",
        "hover": "#383838",
        "pressed": "#323232",
        "checked_bg": "#3a3a3a",
        "checked_border": "#3f8f68",
        "input": "#2d2d2d",
        "input_border": "#3a3a3a",
        "input_bottom": "#9a9a9a",
        "button": "#2d2d2d",
        "button_hover": "#323232",
        "accent": "#2ed37f",
        "accent_hover": "#28be72",
        "accent_text": "#000000",
        "slider": "#9a9a9a",
        "scroll_thumb": "#9a9a9a",
        "gallery": "#2f2f2f",
        "gallery_border": "#363636",
        "icon": "#e6e6e6",
        "swatch_border": "#6a6a6a",
        "canvas_border": "#2f2f2f",
        "handle_border": "#bdbdbd",
    }
