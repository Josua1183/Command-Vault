from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

DEBOUNCE_MS = 200


class SearchBar(QWidget):
    """Suchfeld mit verzögertem (entprelltem) ``text_changed``-Signal."""

    text_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._setup_signals()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "Befehle durchsuchen (Titel, Befehl, Beschreibung, Tags) ..."
        )
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setMinimumWidth(320)
        layout.addWidget(self._search_input)

    def _setup_signals(self):
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(lambda: self.text_changed.emit(self.text()))
        self._search_input.textChanged.connect(lambda _text: self._timer.start())

    def text(self) -> str:
        return self._search_input.text()

    def set_text(self, text: str) -> None:
        self._search_input.setText(text)

    def focus_input(self) -> None:
        self._search_input.setFocus()
        self._search_input.selectAll()

    def clear(self) -> None:
        self._search_input.clear()
