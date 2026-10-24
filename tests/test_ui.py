from PySide6.QtCore import QEventLoop, QTimer

from src.database.models import Command
from src.services.command_service import CommandService
from src.styles import theme
from src.ui.command_editor import CommandEditor, parse_tags
from src.ui.main_window import MainWindow


def _wait(ms: int, until=lambda: False):
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(20)
    poll.timeout.connect(lambda: loop.quit() if until() else None)
    poll.start()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    poll.stop()


def test_parse_tags():
    assert parse_tags(" a, b ,, A ,c") == ["a", "b", "c"]
    assert parse_tags("") == []


def test_editor_validation_and_result(qapp, tmp_path):
    editor = CommandEditor()
    assert len(editor.validate()) == 2

    editor._title_input.setText("  Titel ")
    editor._command_input.setPlainText("echo 1\necho 2")
    editor._tags_input.setText("x, y")
    editor._terminal_check.setChecked(False)
    editor._directory_input.setText("/does/not/exist")
    assert editor.validate() == ["Das Arbeitsverzeichnis existiert nicht."]

    editor._directory_input.setText(str(tmp_path))
    assert editor.validate() == []
    cmd = editor.get_command()
    assert (cmd.title, cmd.command, cmd.tags, cmd.open_terminal) == (
        "Titel",
        "echo 1\necho 2",
        ["x", "y"],
        False,
    )


def test_editor_edit_mode_keeps_identity(qapp):
    original = Command(
        id=5, title="T", command="ls", last_status="Fehler (Exit: 1)", last_output="o"
    )
    editor = CommandEditor(command=original)
    assert editor.is_edit_mode
    result = editor.get_command()
    assert (result.id, result.last_status, result.last_output) == (5, "Fehler (Exit: 1)", "o")


def test_theme_switch_builds_valid_qss(qapp):
    for name in theme.THEMES:
        theme.apply_theme(name)
        assert "$" not in qapp.styleSheet()
    theme.apply_theme("dark")


def test_main_window_create_run_and_delete(qapp, db):
    service = CommandService()
    service.create(Command(title="Echo", command="echo hallo", open_terminal=False, tags=["t"]))

    window = MainWindow()
    window.show()
    assert window._command_list.count() == 1

    window._command_list.select_command(service.get_all()[0].id)
    assert window._selected_id is not None

    window._on_run_or_stop()
    _wait(5000, until=lambda: not window._executor_service.is_running())

    cmd = service.get_all()[0]
    assert cmd.last_status.startswith("Erfolgreich")
    assert "hallo" in cmd.last_output
    assert "hallo" in window._command_detail._output_panel.get_text()

    # Suche filtert
    window._search_bar.set_text("gibtsnicht")
    _wait(600, until=lambda: window._command_list.count() == 0)
    assert window._command_list.count() == 0
    window._search_bar.set_text("")
    _wait(600, until=lambda: window._command_list.count() == 1)
    assert window._command_list.count() == 1

    window.close()
