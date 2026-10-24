import os

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.database.models import Command, ScheduleInterval


def parse_tags(text: str) -> list[str]:
    """Zerlegt eine kommagetrennte Eingabe in eindeutige, nicht leere Tags."""
    tags: list[str] = []
    for raw in text.split(","):
        tag = raw.strip()
        if tag and tag.casefold() not in (t.casefold() for t in tags):
            tags.append(tag)
    return tags


class CommandEditor(QDialog):
    """Dialog zum Erstellen oder Bearbeiten eines Befehls."""

    def __init__(self, command: Command | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._command = command
        self._setup_ui()
        self._populate_fields()

    @property
    def is_edit_mode(self) -> bool:
        return self._command is not None

    def _setup_ui(self):
        self.setWindowTitle("Befehl bearbeiten" if self.is_edit_mode else "Neuer Befehl")
        self.setModal(True)
        self.setMinimumSize(580, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("z. B. Speicherplatz anzeigen")
        form.addRow("Titel *", self._title_input)

        self._command_input = QPlainTextEdit()
        self._command_input.setObjectName("code")
        self._command_input.setPlaceholderText("z. B. df -h")
        self._command_input.setTabChangesFocus(True)
        self._command_input.setMinimumHeight(100)
        form.addRow("Befehl *", self._command_input)

        self._description_input = QPlainTextEdit()
        self._description_input.setPlaceholderText("Optionale Beschreibung ...")
        self._description_input.setTabChangesFocus(True)
        self._description_input.setMaximumHeight(90)
        form.addRow("Beschreibung", self._description_input)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        self._directory_input = QLineEdit()
        self._directory_input.setPlaceholderText("Leer lassen für das aktuelle Verzeichnis")
        dir_row.addWidget(self._directory_input)
        browse_btn = QPushButton("Durchsuchen ...")
        browse_btn.setProperty("variant", "secondary")
        browse_btn.setAutoDefault(False)
        browse_btn.clicked.connect(self._browse_directory)
        dir_row.addWidget(browse_btn)
        form.addRow("Arbeitsverzeichnis", dir_row)

        self._tags_input = QLineEdit()
        self._tags_input.setPlaceholderText("Kommagetrennt: docker, system, monitoring")
        form.addRow("Tags", self._tags_input)

        self._category_input = QLineEdit()
        self._category_input.setPlaceholderText("z. B. System, Docker, Monitoring")
        form.addRow("Kategorie", self._category_input)

        self._schedule_combo = QComboBox()
        for interval in ScheduleInterval:
            self._schedule_combo.addItem(interval.label, interval.value)
        form.addRow("Automatische Ausführung", self._schedule_combo)

        self._terminal_check = QCheckBox("In einem Terminal-Fenster ausführen")
        self._terminal_check.setChecked(True)
        form.addRow("", self._terminal_check)

        layout.addLayout(form)

        self._error_label = QLabel()
        self._error_label.setObjectName("errorText")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Speichern")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setProperty("variant", "secondary")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_fields(self):
        if self._command is None:
            return
        self._title_input.setText(self._command.title)
        self._command_input.setPlainText(self._command.command)
        self._description_input.setPlainText(self._command.description)
        self._directory_input.setText(self._command.working_directory)
        self._category_input.setText(self._command.category)
        self._tags_input.setText(", ".join(self._command.tags))
        self._terminal_check.setChecked(self._command.open_terminal)
        # Schedule-Intervall setzen
        idx = self._schedule_combo.findData(self._command.schedule_interval)
        if idx >= 0:
            self._schedule_combo.setCurrentIndex(idx)

    def _browse_directory(self):
        start = os.path.expanduser(self._directory_input.text().strip() or "~")
        directory = QFileDialog.getExistingDirectory(self, "Arbeitsverzeichnis wählen", start)
        if directory:
            self._directory_input.setText(directory)

    def validate(self) -> list[str]:
        """Gibt eine Liste von Fehlermeldungen zurück (leer = gültig)."""
        errors = []
        if not self._title_input.text().strip():
            errors.append("Der Titel darf nicht leer sein.")
        if not self._command_input.toPlainText().strip():
            errors.append("Der Befehl darf nicht leer sein.")
        directory = self._directory_input.text().strip()
        if directory and not os.path.isdir(os.path.expanduser(directory)):
            errors.append("Das Arbeitsverzeichnis existiert nicht.")
        return errors

    def _on_accept(self):
        errors = self.validate()
        self._error_label.setText(" ".join(errors))
        if not errors:
            self.accept()

    def get_command(self) -> Command:
        """Baut ein ``Command`` aus den Formulardaten (übernimmt Status/ID beim Bearbeiten)."""
        cmd = Command(
            title=self._title_input.text().strip(),
            command=self._command_input.toPlainText().strip(),
            description=self._description_input.toPlainText().strip(),
            working_directory=self._directory_input.text().strip(),
            category=self._category_input.text().strip(),
            tags=parse_tags(self._tags_input.text()),
            open_terminal=self._terminal_check.isChecked(),
            schedule_interval=str(self._schedule_combo.currentData()),
        )
        if self._command is not None:
            cmd.id = self._command.id
            cmd.last_status = self._command.last_status
            cmd.last_output = self._command.last_output
            cmd.last_scheduled_run = self._command.last_scheduled_run
            cmd.created_at = self._command.created_at
        return cmd
