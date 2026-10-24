from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.database.models import STATUS_RUNNING, Command, ScheduleInterval, StatusKind
from src.styles.theme import set_property
from src.ui.output_panel import OutputPanel


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


class CommandDetail(QWidget):
    """Detailansicht eines Befehls inklusive Aktionen und Ausgabe."""

    edit_requested = Signal()
    delete_requested = Signal()
    run_requested = Signal()  # startet bzw. stoppt (je nach Laufzustand)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._command: Command | None = None
        self._is_running = False
        self._setup_ui()
        self.clear()

    # ---------------------------------------------------------------- aufbau

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        # Leerer Zustand
        self._empty_widget = QWidget()
        empty_layout = QVBoxLayout(self._empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title = QLabel("Kein Befehl ausgewählt")
        empty_title.setObjectName("emptyTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint = QLabel("Wähle links einen Befehl aus oder lege mit Strg+N einen neuen an.")
        empty_hint.setObjectName("muted")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_hint)
        layout.addWidget(self._empty_widget)

        # Detailbereich
        self._detail_frame = QFrame()
        detail = QVBoxLayout(self._detail_frame)
        detail.setContentsMargins(0, 0, 0, 0)
        detail.setSpacing(14)

        title_row = QHBoxLayout()
        self._title_label = QLabel()
        self._title_label.setObjectName("title")
        self._title_label.setWordWrap(True)
        title_row.addWidget(self._title_label, 1)
        self._status_dot = QLabel("●")
        self._status_dot.setObjectName("statusDot")
        title_row.addWidget(self._status_dot)
        self._status_label = QLabel()
        self._status_label.setObjectName("statusText")
        title_row.addWidget(self._status_label)
        detail.addLayout(title_row)

        self._tags_layout = QHBoxLayout()
        self._tags_layout.setSpacing(6)
        detail.addLayout(self._tags_layout)

        detail.addWidget(_section_label("Beschreibung"))
        self._description_label = QLabel()
        self._description_label.setWordWrap(True)
        self._description_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail.addWidget(self._description_label)

        command_header = QHBoxLayout()
        command_header.addWidget(_section_label("Befehl"))
        command_header.addStretch()
        copy_btn = QPushButton("Kopieren")
        copy_btn.setProperty("variant", "secondary")
        copy_btn.setProperty("compact", "true")
        copy_btn.clicked.connect(self._copy_command)
        command_header.addWidget(copy_btn)
        detail.addLayout(command_header)

        self._command_edit = QPlainTextEdit()
        self._command_edit.setObjectName("code")
        self._command_edit.setReadOnly(True)
        self._command_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._command_edit.setMaximumHeight(130)
        detail.addWidget(self._command_edit)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(24)
        dir_col = QVBoxLayout()
        dir_col.addWidget(_section_label("Arbeitsverzeichnis"))
        self._directory_label = QLabel()
        self._directory_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dir_col.addWidget(self._directory_label)
        meta_row.addLayout(dir_col, 1)
        cat_col = QVBoxLayout()
        cat_col.addWidget(_section_label("Kategorie"))
        self._category_label = QLabel()
        cat_col.addWidget(self._category_label)
        meta_row.addLayout(cat_col, 1)
        mode_col = QVBoxLayout()
        mode_col.addWidget(_section_label("Ausführung"))
        self._mode_label = QLabel()
        mode_col.addWidget(self._mode_label)
        meta_row.addLayout(mode_col, 1)
        detail.addLayout(meta_row)

        # Schedule-Info
        schedule_row = QHBoxLayout()
        schedule_row.addWidget(_section_label("Automatische Ausführung"))
        schedule_row.addStretch()
        self._schedule_label = QLabel()
        self._schedule_label.setObjectName("muted")
        schedule_row.addWidget(self._schedule_label)
        detail.addLayout(schedule_row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._run_btn = QPushButton("▶  Ausführen")
        self._run_btn.setToolTip("Befehl ausführen (F5)")
        self._run_btn.clicked.connect(self.run_requested.emit)
        actions.addWidget(self._run_btn)
        self._edit_btn = QPushButton("Bearbeiten")
        self._edit_btn.setProperty("variant", "secondary")
        self._edit_btn.clicked.connect(self.edit_requested.emit)
        actions.addWidget(self._edit_btn)
        self._delete_btn = QPushButton("Löschen")
        self._delete_btn.setProperty("variant", "danger")
        self._delete_btn.clicked.connect(self.delete_requested.emit)
        actions.addWidget(self._delete_btn)
        actions.addStretch()
        detail.addLayout(actions)

        self._output_panel = OutputPanel()
        detail.addWidget(self._output_panel, 1)

        layout.addWidget(self._detail_frame, 1)

    # --------------------------------------------------------------- öffentlich

    @property
    def command(self) -> Command | None:
        return self._command

    def set_command(self, command: Command, show_output: bool = True) -> None:
        """Zeigt einen Befehl an. ``show_output=False`` lässt das Ausgabefeld unverändert."""
        self._command = command
        self._empty_widget.hide()
        self._detail_frame.show()

        self._title_label.setText(command.title)
        self._apply_status(command.last_status, command.status_kind)

        self._clear_tags()
        for tag in command.tags:
            label = QLabel(tag)
            label.setObjectName("tag")
            self._tags_layout.addWidget(label)
        self._tags_layout.addStretch()

        self._set_optional_text(self._description_label, command.description, "Keine Beschreibung")
        self._command_edit.setPlainText(command.command)
        self._set_optional_text(
            self._directory_label, command.working_directory, "Aktuelles Verzeichnis"
        )
        self._set_optional_text(self._category_label, command.category, "Keine Kategorie")
        self._mode_label.setText(
            "Im Terminal-Fenster" if command.open_terminal else "In der App (Ausgabe unten)"
        )
        # Schedule-Info
        try:
            interval = command.schedule
        except ValueError:
            interval = ScheduleInterval.NONE
        self._schedule_label.setText(interval.label)
        if command.last_scheduled_run:
            run_str = command.last_scheduled_run.strftime("Letzter Lauf: %d.%m.%Y %H:%M")
            self._schedule_label.setText(f"{interval.label} — {run_str}")

        if show_output:
            self._output_panel.set_text(command.last_output)

    def clear(self) -> None:
        self._command = None
        self._empty_widget.show()
        self._detail_frame.hide()
        self._output_panel.clear()
        self._clear_tags()

    def set_running(self, running: bool) -> None:
        self._is_running = running
        self._run_btn.setText("■  Stoppen" if running else "▶  Ausführen")
        self._run_btn.setToolTip("Ausführung abbrechen" if running else "Befehl ausführen (F5)")
        self._edit_btn.setEnabled(not running)
        self._delete_btn.setEnabled(not running)
        if running:
            self._apply_status(STATUS_RUNNING, StatusKind.RUNNING)

    def append_output(self, text: str) -> None:
        self._output_panel.append_text(text)

    def clear_output(self) -> None:
        self._output_panel.clear()

    # ----------------------------------------------------------------- intern

    def _apply_status(self, text: str, kind: StatusKind) -> None:
        self._status_label.setText(text)
        set_property(self._status_dot, "status", kind.value)
        set_property(self._status_label, "status", kind.value)

    @staticmethod
    def _set_optional_text(label: QLabel, value: str, placeholder: str) -> None:
        label.setText(value or placeholder)
        set_property(label, "muted", "false" if value else "true")

    def _clear_tags(self) -> None:
        while self._tags_layout.count():
            item = self._tags_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _copy_command(self) -> None:
        if self._command:
            QApplication.clipboard().setText(self._command.command)
