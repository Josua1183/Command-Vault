import logging
import os
import re
import shutil
from dataclasses import dataclass

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from src.database.models import (
    STATUS_CANCELLED,
    STATUS_TIMEOUT,
    Command,
    status_error,
    status_success,
)
from src.services import terminal_launcher
from src.services.terminal_launcher import TerminalError

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 5 * 60 * 1000
KILL_GRACE_MS = 3000
MAX_STORED_OUTPUT = 200_000

# Muster, die auf potenziell gefährliche Befehle hindeuten.
DANGEROUS_PATTERNS = [
    re.compile(r"\bsudo\b"),
    re.compile(r"\brm\s+(-\S*\s+)*-\S*[rRf]"),
    re.compile(r"\bmkfs(\.\w+)?\b"),
    re.compile(r"\bdd\s+[^|;&]*\bif="),
    re.compile(r":\s*\(\s*\)\s*\{"),
    re.compile(r"\bchmod\s+(-\S+\s+)*0?777\b"),
    re.compile(r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba|z)?sh\b"),
    re.compile(r">\s*/dev/(sd|nvme|vd)"),
    re.compile(r"\b(shutdown|reboot|poweroff|halt)\b"),
]

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

__all__ = ["ExecutionResult", "ExecutorService", "TerminalError", "is_dangerous"]


def is_dangerous(command_str: str) -> bool:
    """Prüft, ob ein Befehl auf ein gefährliches Muster passt."""
    return any(pattern.search(command_str) for pattern in DANGEROUS_PATTERNS)


@dataclass(frozen=True)
class ExecutionResult:
    """Ergebnis einer Ausführung innerhalb der App."""

    command_id: int | None
    output: str
    exit_code: int
    status: str


class ExecutorService(QObject):
    """Führt Befehle aus – in der App (QProcess) oder in einem Terminal-Fenster."""

    output_updated = Signal(int, str)  # command_id, Textblock
    execution_finished = Signal(object)  # ExecutionResult

    def __init__(self, timeout_ms: int = DEFAULT_TIMEOUT_MS, parent: QObject | None = None):
        super().__init__(parent)
        self._timeout_ms = timeout_ms
        self._process: QProcess | None = None
        self._command_id: int | None = None
        self._buffer: list = []
        self._stopped = False
        self._timed_out = False

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

    # ----------------------------------------------------------------- public

    def is_dangerous(self, command_str: str) -> bool:
        return is_dangerous(command_str)

    def is_running(self) -> bool:
        return self._process is not None

    @property
    def running_command_id(self) -> int | None:
        return self._command_id if self._process is not None else None

    def execute_in_terminal(self, command: Command) -> str:
        """Öffnet ein Terminal und führt den Befehl dort aus.

        Gibt den Namen des Terminals zurück, wirft ``TerminalError`` bei Problemen.
        """
        return terminal_launcher.launch_in_terminal(command.command, command.working_directory)

    def execute_in_app(self, command: Command) -> bool:
        """Führt den Befehl in der App aus und streamt die Ausgabe über Signale."""
        if self._process is not None:
            return False

        work_dir = (
            os.path.expanduser(command.working_directory)
            if command.working_directory
            else os.getcwd()
        )
        self._command_id = command.id
        self._buffer = []
        self._stopped = False
        self._timed_out = False

        if not os.path.isdir(work_dir):
            self._emit_failure(f"Arbeitsverzeichnis existiert nicht: {work_dir}")
            return False

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setWorkingDirectory(work_dir)
        process.setProgram(shutil.which("bash") or "/bin/sh")
        process.setArguments(["-c", command.command])
        process.readyReadStandardOutput.connect(self._drain_output)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)

        self._process = process
        process.start()
        if self._timeout_ms > 0:
            self._timeout_timer.start(self._timeout_ms)
        return True

    def stop_execution(self) -> None:
        """Bricht die laufende Ausführung ab (SIGTERM, nach Karenzzeit SIGKILL)."""
        process = self._process
        if process is None:
            return
        self._stopped = True
        self._terminate(process)

    def shutdown(self) -> None:
        """Beendet einen laufenden Prozess hart (z. B. beim Schließen der App)."""
        process, self._process = self._process, None
        self._timeout_timer.stop()
        if process is None:
            return
        process.blockSignals(True)
        process.kill()
        process.waitForFinished(1000)
        process.deleteLater()

    # --------------------------------------------------------------- internals

    def _terminate(self, process: QProcess) -> None:
        process.terminate()
        QTimer.singleShot(KILL_GRACE_MS, lambda: self._kill_if_alive(process))

    def _kill_if_alive(self, process: QProcess) -> None:
        if self._process is process and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def _on_timeout(self) -> None:
        if self._process is not None:
            self._timed_out = True
            self._terminate(self._process)

    def _drain_output(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput().data())
        if not data:
            return
        text = _ANSI_ESCAPE.sub("", data.decode("utf-8", errors="replace"))
        self._buffer.append(text)
        self.output_updated.emit(self._command_id if self._command_id is not None else -1, text)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and self._process is not None:
            message = self._process.errorString()
            self._cleanup_process()
            self._emit_failure(f"Prozess konnte nicht gestartet werden: {message}")

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._drain_output()
        self._cleanup_process()

        if self._stopped:
            status, code = STATUS_CANCELLED, exit_code
        elif self._timed_out:
            status, code = STATUS_TIMEOUT, exit_code
        elif exit_status == QProcess.ExitStatus.CrashExit:
            code = -1
            status = status_error(code)
        elif exit_code == 0:
            status, code = status_success(0), 0
        else:
            status, code = status_error(exit_code), exit_code

        self._emit_result(code, status)

    def _cleanup_process(self) -> None:
        self._timeout_timer.stop()
        process, self._process = self._process, None
        if process is not None:
            process.deleteLater()

    def _emit_failure(self, message: str) -> None:
        logger.warning(message)
        text = message + "\n"
        self._buffer.append(text)
        self.output_updated.emit(self._command_id if self._command_id is not None else -1, text)
        self._emit_result(-1, status_error(-1))

    def _emit_result(self, exit_code: int, status: str) -> None:
        output = "".join(self._buffer)
        if len(output) > MAX_STORED_OUTPUT:
            output = "[... Ausgabe gekürzt ...]\n" + output[-MAX_STORED_OUTPUT:]
        self.execution_finished.emit(
            ExecutionResult(
                command_id=self._command_id,
                output=output,
                exit_code=exit_code,
                status=status,
            )
        )
