from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

MAX_LINES = 10_000


class OutputPanel(QWidget):
    """Zeigt die Ausgabe eines Befehls (streamend, mit Scroll-Limit)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel("Ausgabe")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()

        self._copy_btn = QPushButton("Kopieren")
        self._copy_btn.setProperty("variant", "secondary")
        self._copy_btn.setProperty("compact", "true")
        self._copy_btn.clicked.connect(self._copy_output)
        header.addWidget(self._copy_btn)
        layout.addLayout(header)

        self._output_edit = QPlainTextEdit()
        self._output_edit.setObjectName("output")
        self._output_edit.setReadOnly(True)
        self._output_edit.setMaximumBlockCount(MAX_LINES)
        self._output_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._output_edit.setPlaceholderText("Noch keine Ausgabe.")
        layout.addWidget(self._output_edit)

    def append_text(self, text: str) -> None:
        """Hängt einen Textblock an (ohne zusätzlichen Zeilenumbruch)."""
        scrollbar = self._output_edit.verticalScrollBar()
        follow = scrollbar.value() >= scrollbar.maximum() - 4

        cursor = self._output_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)

        if follow:
            scrollbar.setValue(scrollbar.maximum())

    def clear(self) -> None:
        self._output_edit.clear()

    def set_text(self, text: str) -> None:
        self._output_edit.setPlainText(text)

    def get_text(self) -> str:
        return self._output_edit.toPlainText()

    def _copy_output(self) -> None:
        QApplication.clipboard().setText(self.get_text())
