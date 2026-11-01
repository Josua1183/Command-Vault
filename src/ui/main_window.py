import logging

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src import __version__
from src.database.models import (
    STATUS_IN_TERMINAL,
    STATUS_RUNNING,
    Command,
)
from src.services.command_service import CommandService
from src.services.executor_service import ExecutionResult, ExecutorService, TerminalError
from src.services.scheduler_service import SchedulerService
from src.styles import theme
from src.ui.command_detail import CommandDetail
from src.ui.command_editor import CommandEditor
from src.ui.command_list import CommandList
from src.ui.search_bar import SearchBar

logger = logging.getLogger(__name__)

STATUS_MESSAGE_MS = 5000


class MainWindow(QMainWindow):
    """Hauptfenster: Liste links, Details/Ausgabe rechts."""

    def __init__(
        self,
        command_service: CommandService | None = None,
        executor_service: ExecutorService | None = None,
    ):
        super().__init__()
        self._command_service = command_service or CommandService()
        self._executor_service = executor_service or ExecutorService(parent=self)
        self._scheduler = SchedulerService(
            self._command_service, self._executor_service, parent=self
        )
        self._selected_id: int | None = None
        self._selection_actions: list[QAction] = []
        self._selected_category: str = ""

        self._setup_window()
        self._setup_actions()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_statusbar()
        self._setup_signals()
        self._refresh_list()
        self._update_action_states()
        self._restore_geometry()
        self._scheduler.start()

    # ----------------------------------------------------------------- aufbau

    def _setup_window(self):
        self.setWindowTitle("Command Vault")
        self.setMinimumSize(980, 620)
        self.resize(1280, 800)

    def _make_action(self, text: str, slot, shortcut=None, needs_selection=False) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False: slot())
        if needs_selection:
            self._selection_actions.append(action)
        return action

    def _setup_actions(self):
        self._new_action = self._make_action(
            "&Neuer Befehl", self._on_new_command, QKeySequence.StandardKey.New
        )
        self._quit_action = self._make_action("&Beenden", self.close, QKeySequence.StandardKey.Quit)
        self._edit_action = self._make_action(
            "Befehl &bearbeiten", self._on_edit_command, "F2", needs_selection=True
        )
        self._delete_action = self._make_action(
            "Befehl &löschen",
            self._on_delete_command,
            QKeySequence.StandardKey.Delete,
            needs_selection=True,
        )
        self._copy_action = self._make_action(
            "Befehl &kopieren", self._on_copy_command, "Ctrl+Shift+C", needs_selection=True
        )
        self._run_action = self._make_action(
            "Befehl &ausführen / stoppen", self._on_run_or_stop, "F5", needs_selection=True
        )
        self._search_action = self._make_action(
            "&Suchen", self._search_bar_focus, QKeySequence.StandardKey.Find
        )
        self._theme_action = self._make_action("&Theme wechseln", self._on_toggle_theme, "Ctrl+T")

    def _setup_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&Datei")
        file_menu.addAction(self._new_action)
        file_menu.addSeparator()
        file_menu.addAction(self._quit_action)

        edit_menu = menu_bar.addMenu("&Bearbeiten")
        edit_menu.addAction(self._edit_action)
        edit_menu.addAction(self._copy_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._delete_action)

        view_menu = menu_bar.addMenu("&Ansicht")
        view_menu.addAction(self._search_action)
        view_menu.addAction(self._theme_action)

        run_menu = menu_bar.addMenu("&Ausführen")
        run_menu.addAction(self._run_action)

    def _setup_toolbar(self):
        toolbar = QToolBar("Hauptleiste")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(toolbar)

        new_btn = QToolButton()
        new_btn.setDefaultAction(self._new_action)
        new_btn.setText("＋ Neu")
        new_btn.setToolTip("Neuen Befehl anlegen (Strg+N)")
        toolbar.addWidget(new_btn)

        self._search_bar = SearchBar()
        toolbar.addWidget(self._search_bar)

        # Kategorie-Filter
        self._category_combo = QComboBox()
        self._category_combo.setMaximumWidth(180)
        self._category_combo.setToolTip("Nach Kategorie filtern")
        self._category_combo.currentTextChanged.connect(self._on_category_changed)
        toolbar.addWidget(self._category_combo)
        self._refresh_categories()

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self._theme_btn = QToolButton()
        self._theme_btn.setToolTip("Theme wechseln (Strg+T)")
        self._theme_btn.clicked.connect(self._on_toggle_theme)
        toolbar.addWidget(self._theme_btn)
        self._update_theme_button()

    def _setup_central_widget(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)

        left = QWidget()
        left.setMinimumWidth(300)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 8, 8)
        left_layout.setSpacing(8)

        header = QHBoxLayout()
        list_title = QLabel("Befehle")
        list_title.setObjectName("sectionTitle")
        header.addWidget(list_title)
        header.addStretch()
        self._count_label = QLabel()
        self._count_label.setObjectName("muted")
        header.addWidget(self._count_label)
        left_layout.addLayout(header)

        self._command_list = CommandList()
        left_layout.addWidget(self._command_list, 1)

        splitter.addWidget(left)

        self._command_detail = CommandDetail()
        splitter.addWidget(self._command_detail)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 900])

    def _setup_statusbar(self):
        self.statusBar().addPermanentWidget(QLabel(f"Command Vault v{__version__}"))
        self.statusBar().showMessage("Bereit")

    def _setup_signals(self):
        self._search_bar.text_changed.connect(lambda _text: self._refresh_list())

        self._command_list.command_selected.connect(self._on_command_selected)
        self._command_list.command_activated.connect(self._on_command_activated)
        self._command_list.context_menu_requested.connect(self._on_context_menu)

        self._command_detail.edit_requested.connect(self._on_edit_command)
        self._command_detail.delete_requested.connect(self._on_delete_command)
        self._command_detail.run_requested.connect(self._on_run_or_stop)

        self._executor_service.output_updated.connect(self._on_execution_output)
        self._executor_service.execution_finished.connect(self._on_execution_finished)

        self._scheduler.scheduled_executed.connect(self._on_scheduled_executed)
        self._scheduler.scheduled_error.connect(self._on_scheduled_error)

    # ------------------------------------------------------------------ helfer

    def _show_message(self, text: str) -> None:
        self.statusBar().showMessage(text, STATUS_MESSAGE_MS)

    def _selected_command(self) -> Command | None:
        if self._selected_id is None:
            return None
        return self._command_service.get_by_id(self._selected_id)

    def _refresh_list(self) -> None:
        query = self._search_bar.text()
        if self._selected_category:
            commands = self._command_service.filter_by_category(self._selected_category)
            # Zusätzlich nach Suchbegriff filtern
            if query.strip():
                pattern = query.strip().lower()
                commands = [
                    c
                    for c in commands
                    if pattern in c.title.lower()
                    or pattern in c.command.lower()
                    or pattern in c.description.lower()
                    or any(pattern in t.lower() for t in c.tags)
                ]
        else:
            commands = self._command_service.search(query)
        self._command_list.set_commands(commands, keep_selection_id=self._selected_id)
        total = len(commands)
        self._count_label.setText("1 Eintrag" if total == 1 else f"{total} Einträge")

    def _refresh_categories(self) -> None:
        """Aktualisiert die Kategorie-Filter-ComboBox."""
        current = self._category_combo.currentText()
        self._category_combo.blockSignals(True)
        self._category_combo.clear()
        self._category_combo.addItem("Alle Kategorien", "")
        for cat in self._command_service.get_categories():
            self._category_combo.addItem(cat, cat)
        # Vorherige Auswahl wiederherstellen
        idx = self._category_combo.findData(current)
        if idx >= 0:
            self._category_combo.setCurrentIndex(idx)
        self._category_combo.blockSignals(False)

    def _on_category_changed(self, category: str) -> None:
        self._selected_category = category
        self._refresh_list()

    def _update_action_states(self) -> None:
        has_selection = self._selected_id is not None
        running = self._executor_service.is_running()
        for action in self._selection_actions:
            action.setEnabled(has_selection)
        self._edit_action.setEnabled(has_selection and not running)
        self._delete_action.setEnabled(has_selection and not running)

    def _show_command(self, command: Command) -> None:
        """Zeigt den Befehl im Detailbereich; laufende Ausgabe bleibt erhalten."""
        is_running_here = self._executor_service.running_command_id == command.id
        if is_running_here:
            self._command_detail.set_command(command, show_output=False)
            self._command_detail.set_running(True)
        else:
            self._command_detail.set_command(command)
            self._command_detail.set_running(False)

    def _update_theme_button(self) -> None:
        dark = theme.get_current_theme() == "dark"
        self._theme_btn.setText("☀" if dark else "☾")

    def _search_bar_focus(self) -> None:
        self._search_bar.focus_input()

    # --------------------------------------------------------------- Auswahl

    def _on_command_selected(self, command_id: int) -> None:
        cmd = self._command_service.get_by_id(command_id)
        if cmd is None:
            return
        self._selected_id = command_id
        self._show_command(cmd)
        self._update_action_states()

    def _on_command_activated(self, command_id: int) -> None:
        self._on_command_selected(command_id)
        self._on_run_or_stop()

    # ----------------------------------------------------------------- CRUD

    def _on_new_command(self) -> None:
        editor = CommandEditor(parent=self)
        if editor.exec() != CommandEditor.DialogCode.Accepted:
            return
        saved = self._command_service.create(editor.get_command())
        self._scheduler.on_command_changed()
        self._selected_id = saved.id
        self._refresh_list()
        self._refresh_categories()
        self._command_list.select_command(saved.id)
        self._show_message(f"Angelegt: {saved.title}")

    def _on_edit_command(self) -> None:
        cmd = self._selected_command()
        if cmd is None or self._executor_service.is_running():
            return
        editor = CommandEditor(command=cmd, parent=self)
        if editor.exec() != CommandEditor.DialogCode.Accepted:
            return
        updated = self._command_service.update(editor.get_command())
        self._scheduler.on_command_changed()
        self._refresh_list()
        self._refresh_categories()
        self._show_command(updated)
        self._show_message(f"Gespeichert: {updated.title}")

    def _on_delete_command(self) -> None:
        cmd = self._selected_command()
        if cmd is None or self._executor_service.is_running():
            return
        reply = QMessageBox.question(
            self,
            "Befehl löschen",
            f"Soll „{cmd.title}“ wirklich gelöscht werden?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._command_service.delete(cmd.id)
        self._scheduler.on_command_deleted(cmd.id)
        self._selected_id = None
        self._command_list.clear_selection()
        self._command_detail.clear()
        self._refresh_list()
        self._refresh_categories()
        self._update_action_states()
        self._show_message(f"Gelöscht: {cmd.title}")

    def _on_copy_command(self) -> None:
        cmd = self._selected_command()
        if cmd is None:
            return
        QApplication.clipboard().setText(cmd.command)
        self._show_message("Befehl in die Zwischenablage kopiert")

    # ------------------------------------------------------------ Ausführung

    def _on_run_or_stop(self) -> None:
        if self._executor_service.is_running():
            if self._executor_service.running_command_id == self._selected_id:
                self._executor_service.stop_execution()
                self._show_message("Abbruch angefordert ...")
            else:
                self._show_message("Es läuft bereits ein anderer Befehl.")
            return

        cmd = self._selected_command()
        if cmd is None:
            return

        if self._executor_service.is_dangerous(cmd.command):
            reply = QMessageBox.warning(
                self,
                "Möglicherweise gefährlicher Befehl",
                f"Dieser Befehl könnte Schaden anrichten:\n\n{cmd.command}\n\nWirklich ausführen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if cmd.open_terminal:
            self._run_in_terminal(cmd)
        else:
            self._run_in_app(cmd)

    def _run_in_terminal(self, cmd: Command) -> None:
        try:
            terminal = self._executor_service.execute_in_terminal(cmd)
        except TerminalError as exc:
            QMessageBox.warning(self, "Terminal konnte nicht geöffnet werden", str(exc))
            return
        self._command_service.update_execution_status(cmd.id, STATUS_IN_TERMINAL, "")
        self._refresh_list()
        updated = self._command_service.get_by_id(cmd.id)
        if updated:
            self._show_command(updated)
        self._show_message(f"In {terminal} gestartet: {cmd.title}")

    def _run_in_app(self, cmd: Command) -> None:
        self._command_service.update_execution_status(cmd.id, STATUS_RUNNING, "")
        self._refresh_list()
        self._command_detail.clear_output()
        self._command_detail.set_running(True)
        self._show_message(f"Läuft: {cmd.title}")
        self._executor_service.execute_in_app(cmd)
        self._update_action_states()

    def _on_execution_output(self, command_id: int, text: str) -> None:
        if command_id == self._selected_id:
            self._command_detail.append_output(text)

    def _on_execution_finished(self, result: ExecutionResult) -> None:
        if result.command_id is not None:
            self._command_service.update_execution_status(
                result.command_id, result.status, result.output
            )
        self._refresh_list()
        self._refresh_categories()
        self._update_action_states()

        if result.command_id is not None and result.command_id == self._selected_id:
            cmd = self._command_service.get_by_id(result.command_id)
            if cmd:
                self._command_detail.set_command(cmd, show_output=False)
            self._command_detail.set_running(False)
        self._show_message(f"Beendet: {result.status}")

    def _on_scheduled_executed(self, command_id: int, schedule_label: str) -> None:
        cmd = self._command_service.get_by_id(command_id)
        title = cmd.title if cmd else f"Befehl #{command_id}"
        self._show_message(f"Geplant: {title} ({schedule_label})")
        self._refresh_list()
        self._refresh_categories()

    def _on_scheduled_error(self, command_id: int, error: str) -> None:
        cmd = self._command_service.get_by_id(command_id)
        title = cmd.title if cmd else f"Befehl #{command_id}"
        self._show_message(f"Fehler (geplant): {title} — {error}")

    # ------------------------------------------------------- Kontextmenü/Theme

    def _on_context_menu(self, _command_id: int, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction(self._run_action)
        menu.addAction(self._edit_action)
        menu.addAction(self._copy_action)
        menu.addSeparator()
        menu.addAction(self._delete_action)
        menu.exec(global_pos)

    def _on_toggle_theme(self) -> None:
        name = theme.toggle_theme()
        QSettings().setValue("theme", name)
        self._update_theme_button()
        self._show_message(f"Theme: {'Dunkel' if name == 'dark' else 'Hell'}")

    # -------------------------------------------------------------- Lebenszyklus

    def _restore_geometry(self) -> None:
        geometry = QSettings().value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: QCloseEvent) -> None:
        QSettings().setValue("window/geometry", self.saveGeometry())
        self._scheduler.stop()
        self._executor_service.shutdown()
        super().closeEvent(event)
