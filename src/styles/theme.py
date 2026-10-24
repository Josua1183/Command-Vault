"""Theme-Verwaltung: Farbpaletten, QSS-Template und Dark/Light-Umschaltung."""

from pathlib import Path
from string import Template

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

QSS_PATH = Path(__file__).with_name("styles.qss")

DARK_THEME: dict[str, str] = {
    # Hintergründe
    "bg_primary": "#1e1e2e",
    "bg_secondary": "#181825",
    "bg_tertiary": "#313244",
    "bg_surface": "#252536",
    "bg_hover": "#45475a",
    "bg_selected": "#3b3d57",
    "bg_input": "#313244",
    "bg_code": "#11111b",
    # Text
    "text_primary": "#cdd6f4",
    "text_secondary": "#a6adc8",
    "text_muted": "#7f849c",
    "text_on_accent": "#1e1e2e",
    "text_code": "#a6e3a1",
    # Akzente
    "accent": "#89b4fa",
    "accent_hover": "#b4befe",
    "accent_active": "#74c7ec",
    # Status
    "success": "#a6e3a1",
    "warning": "#f9e2af",
    "error": "#f38ba8",
    "error_hover": "#eba0ac",
    "info": "#89dceb",
    # Rahmen
    "border": "#45475a",
    # Tags
    "tag_bg": "#45475a",
    "tag_text": "#cdd6f4",
}

LIGHT_THEME: dict[str, str] = {
    "bg_primary": "#eff1f5",
    "bg_secondary": "#e6e9ef",
    "bg_tertiary": "#ccd0da",
    "bg_surface": "#ffffff",
    "bg_hover": "#dce0e8",
    "bg_selected": "#d5def7",
    "bg_input": "#ffffff",
    "bg_code": "#e6e9ef",
    "text_primary": "#4c4f69",
    "text_secondary": "#5c5f77",
    "text_muted": "#7c7f93",
    "text_on_accent": "#ffffff",
    "text_code": "#2f7d1f",
    "accent": "#1e66f5",
    "accent_hover": "#4a84f7",
    "accent_active": "#0b4fd1",
    "success": "#40a02b",
    "warning": "#df8e1d",
    "error": "#d20f39",
    "error_hover": "#e64553",
    "info": "#04a5e5",
    "border": "#bcc0cc",
    "tag_bg": "#ccd0da",
    "tag_text": "#4c4f69",
}

THEMES: dict[str, dict[str, str]] = {"dark": DARK_THEME, "light": LIGHT_THEME}


class _ThemeNotifier(QObject):
    """Benachrichtigt Widgets, die selbst zeichnen, über einen Theme-Wechsel."""

    changed = Signal(str)


notifier = _ThemeNotifier()
_current_theme: str = "dark"


def get_current_theme() -> str:
    return _current_theme


def get_theme_colors(name: str | None = None) -> dict[str, str]:
    return THEMES.get(name or _current_theme, DARK_THEME)


def build_qss(colors: dict[str, str]) -> str:
    """Füllt das QSS-Template (styles.qss) mit den Farben des Themes."""
    template = Template(QSS_PATH.read_text(encoding="utf-8"))
    return template.substitute(colors)


def _build_palette(colors: dict[str, str]) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "bg_primary",
        QPalette.ColorRole.WindowText: "text_primary",
        QPalette.ColorRole.Base: "bg_input",
        QPalette.ColorRole.AlternateBase: "bg_secondary",
        QPalette.ColorRole.ToolTipBase: "bg_surface",
        QPalette.ColorRole.ToolTipText: "text_primary",
        QPalette.ColorRole.Text: "text_primary",
        QPalette.ColorRole.PlaceholderText: "text_muted",
        QPalette.ColorRole.Button: "bg_tertiary",
        QPalette.ColorRole.ButtonText: "text_primary",
        QPalette.ColorRole.BrightText: "accent",
        QPalette.ColorRole.Link: "accent",
        QPalette.ColorRole.Highlight: "accent",
        QPalette.ColorRole.HighlightedText: "text_on_accent",
    }
    for role, key in roles.items():
        palette.setColor(role, QColor(colors[key]))
    return palette


def apply_theme(theme_name: str | None = None) -> None:
    """Wendet ein Theme auf die gesamte Anwendung an."""
    global _current_theme
    theme_name = theme_name or _current_theme
    if theme_name not in THEMES:
        raise ValueError(f"Unbekanntes Theme: {theme_name}")
    _current_theme = theme_name

    colors = THEMES[theme_name]
    app = QApplication.instance()
    if app is not None:
        app.setPalette(_build_palette(colors))
        app.setStyleSheet(build_qss(colors))
    notifier.changed.emit(theme_name)


def toggle_theme() -> str:
    """Wechselt zwischen Dark und Light. Gibt den neuen Theme-Namen zurück."""
    new_theme = "light" if _current_theme == "dark" else "dark"
    apply_theme(new_theme)
    return new_theme


def set_property(widget: QWidget, name: str, value: str) -> None:
    """Setzt eine dynamische Property und lässt das QSS neu auswerten."""
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
