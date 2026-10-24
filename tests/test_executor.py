import subprocess

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from src.database.models import Command
from src.services import terminal_launcher
from src.services.executor_service import ExecutorService, is_dangerous


@pytest.mark.parametrize(
    "command",
    [
        "sudo dnf clean all",
        "rm -rf /tmp/x",
        "rm -f file",
        "dd if=/dev/zero of=/dev/sda",
        "curl https://x.sh | sh",
        "wget -qO- https://x | sudo bash",
        "chmod -R 777 /",
        ":(){ :|:& };:",
        "echo hi && reboot",
    ],
)
def test_dangerous_commands_detected(command):
    assert is_dangerous(command)


@pytest.mark.parametrize(
    "command", ["ls -la", "rm file.txt", "echo sudoku", "git status", "curl https://x.org -o f"]
)
def test_harmless_commands_not_flagged(command):
    assert not is_dangerous(command)


def _run(qapp, command: Command, timeout_ms=5000, service=None, after_start=None):
    service = service or ExecutorService()
    results, chunks = [], []
    loop = QEventLoop()
    service.execution_finished.connect(lambda r: (results.append(r), loop.quit()))
    service.output_updated.connect(lambda _id, text: chunks.append(text))
    QTimer.singleShot(timeout_ms, loop.quit)
    service.execute_in_app(command)
    if after_start:
        after_start(service)
    if not results:
        loop.exec()
    return results, "".join(chunks)


def test_execute_in_app_success(qapp):
    results, streamed = _run(qapp, Command(id=1, command="echo hallo; echo fehler >&2"))
    assert len(results) == 1
    result = results[0]
    assert result.command_id == 1
    assert result.exit_code == 0
    assert result.status.startswith("Erfolgreich")
    assert "hallo" in result.output and "fehler" in result.output
    assert streamed == result.output


def test_execute_in_app_failure_exit_code(qapp):
    results, _ = _run(qapp, Command(id=2, command="exit 3"))
    assert results[0].exit_code == 3
    assert results[0].status == "Fehler (Exit: 3)"


def test_execute_in_app_uses_working_directory(qapp, tmp_path):
    results, _ = _run(qapp, Command(id=3, command="pwd", working_directory=str(tmp_path)))
    assert results[0].output.strip() == str(tmp_path)


def test_execute_in_app_missing_directory(qapp):
    results, _ = _run(qapp, Command(id=4, command="ls", working_directory="/does/not/exist"))
    assert results[0].exit_code == -1
    assert "existiert nicht" in results[0].output


def test_stop_execution(qapp):
    results, _ = _run(
        qapp,
        Command(id=5, command="sleep 30"),
        after_start=lambda svc: QTimer.singleShot(200, svc.stop_execution),
    )
    assert results and results[0].status == "Abgebrochen"


def test_timeout(qapp):
    service = ExecutorService(timeout_ms=300)
    results, _ = _run(qapp, Command(id=6, command="sleep 30"), service=service)
    assert results and results[0].status == "Zeitüberschreitung"


def test_only_one_run_at_a_time(qapp):
    service = ExecutorService()
    assert service.execute_in_app(Command(id=7, command="sleep 1"))
    assert service.is_running() and service.running_command_id == 7
    assert not service.execute_in_app(Command(id=8, command="echo x"))
    service.shutdown()
    assert not service.is_running()


# ---------------------------------------------------------------- Terminal


def test_wrapper_runs_command_and_waits_for_key():
    """Wrapper führt den Befehl (mit Sonderzeichen) aus und liest danach einen Tastendruck."""
    command = "echo \"a 'quoted' $((1+2))\"; exit 4"
    argv = terminal_launcher.build_wrapped_argv(command)
    proc = subprocess.run(argv, input="x", capture_output=True, text=True, timeout=10)
    assert "a 'quoted' 3" in proc.stdout
    assert "Exit-Code 4" in proc.stdout
    assert proc.returncode == 0


@pytest.mark.parametrize("spec", terminal_launcher.TERMINALS, ids=lambda s: s.binary)
def test_terminal_argv_keeps_wrapped_command_intact(spec):
    wrapped = terminal_launcher.build_wrapped_argv("echo 'x y'")
    argv = spec.build_args("/tmp", wrapped)
    assert argv[0] == spec.binary
    assert "/tmp" in " ".join(argv) or spec.binary in ("xterm", "x-terminal-emulator")


def test_konsole_options_precede_command():
    spec = next(s for s in terminal_launcher.TERMINALS if s.binary == "konsole")
    argv = spec.build_args("/tmp", ["bash", "-c", "x"])
    # Alles nach -e ist der Befehl – Optionen davor, sonst verschluckt konsole sie.
    assert argv[:5] == ["konsole", "--workdir", "/tmp", "-e", "bash"]


def test_launch_without_terminal(monkeypatch):
    monkeypatch.setattr(terminal_launcher, "find_terminal", lambda: None)
    with pytest.raises(terminal_launcher.TerminalError):
        terminal_launcher.launch_in_terminal("ls")


def test_launch_with_invalid_directory():
    with pytest.raises(terminal_launcher.TerminalError):
        terminal_launcher.launch_in_terminal("ls", "/does/not/exist")


def test_launch_uses_found_terminal(monkeypatch, tmp_path):
    calls = []
    spec = terminal_launcher.TerminalSpec("fake", lambda wd, argv: ["fake", wd, *argv])
    monkeypatch.setattr(terminal_launcher, "find_terminal", lambda: spec)
    monkeypatch.setattr(
        terminal_launcher.subprocess, "Popen", lambda argv, **kw: calls.append((argv, kw))
    )
    assert terminal_launcher.launch_in_terminal("ls", str(tmp_path)) == "fake"
    argv, kwargs = calls[0]
    assert argv[:2] == ["fake", str(tmp_path)]
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["env"]["PWD"] == str(tmp_path)
    assert kwargs["start_new_session"] is True
