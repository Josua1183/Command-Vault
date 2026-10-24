"""Überwacht geplante Befehle und führt sie automatisch aus."""

import logging
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from src.database.models import ScheduleInterval
from src.services.command_service import CommandService
from src.services.executor_service import ExecutorService, TerminalError

logger = logging.getLogger(__name__)

# Wie oft der Scheduler prüft (Sekunden).
CHECK_INTERVAL_SECONDS = 30

# Mindestens so viel Zeit zwischen zwei geplanten Ausführungen desselben Befehls.
MIN_SCHEDULE_GAP_SECONDS = 10


class SchedulerService(QObject):
    """Läuft im Hintergrund und führt Befehle nach ihrem Intervall aus."""

    scheduled_executed = Signal(int, str)  # command_id, schedule_label
    scheduled_error = Signal(int, str)  # command_id, error_message

    def __init__(
        self,
        command_service: CommandService,
        executor_service: ExecutorService,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._command_service = command_service
        self._executor_service = executor_service
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_scheduled)
        self._running = False

        # Verbinde mit dem Executor, um geplante Ausführungen zu tracken
        self._executor_service.execution_finished.connect(self._on_execution_finished)
        self._last_executed_id: int | None = None

    def start(self) -> None:
        """Startet den Scheduler, wenn er noch nicht läuft."""
        if self._running:
            return
        self._running = True
        self._timer.start(CHECK_INTERVAL_SECONDS * 1000)
        logger.info("Scheduler gestartet (Prüfung alle %d s)", CHECK_INTERVAL_SECONDS)

    def stop(self) -> None:
        """Stoppt den Scheduler."""
        self._running = False
        self._timer.stop()
        logger.info("Scheduler gestoppt")

    @property
    def is_running(self) -> bool:
        return self._running

    def _check_scheduled(self) -> None:
        """Prüft alle geplanten Befehle und führt fällige aus."""
        if self._executor_service.is_running():
            # Bereits ein Befehl läuft – warten
            return

        try:
            scheduled = self._command_service.get_scheduled_commands()
        except Exception:
            logger.exception("Fehler beim Laden geplanter Befehle")
            return

        now = datetime.now()
        for cmd in scheduled:
            try:
                interval = cmd.schedule
            except ValueError:
                continue

            if interval == ScheduleInterval.NONE or interval.seconds == 0:
                continue

            # Prüfen, ob das Intervall abgelaufen ist
            last_run = cmd.last_scheduled_run
            if last_run is not None:
                elapsed = (now - last_run).total_seconds()
                if elapsed < interval.seconds:
                    continue
                # Vermeide zu schnelle Wiederholung
                if elapsed < MIN_SCHEDULE_GAP_SECONDS:
                    continue

            logger.info("Geplante Ausführung: %s (%s)", cmd.title, interval.label)
            self._execute_scheduled(cmd)
            # Nur ein Befehl pro Zyklus ausführen
            break

    def _execute_scheduled(self, cmd) -> None:
        """Führt einen geplanten Befehl aus."""
        try:
            self._command_service.update_scheduled_run(cmd.id)
            self._last_executed_id = cmd.id
            interval = cmd.schedule
            self.scheduled_executed.emit(cmd.id, interval.label)

            if cmd.open_terminal:
                try:
                    self._executor_service.execute_in_terminal(cmd)
                    self._command_service.update_execution_status(
                        cmd.id, "Im Terminal gestartet (geplant)", ""
                    )
                except TerminalError as exc:
                    logger.warning("Terminal-Fehler bei geplantem Befehl %s: %s", cmd.title, exc)
                    self.scheduled_error.emit(cmd.id, str(exc))
            else:
                self._command_service.update_execution_status(cmd.id, "Läuft ... (geplant)", "")
                self._executor_service.execute_in_app(cmd)

        except Exception:
            logger.exception("Fehler bei geplanter Ausführung: %s", cmd.title)
            self.scheduled_error.emit(cmd.id, "Unbekannter Fehler")

    def _on_execution_finished(self, result) -> None:
        """Wenn der letzte geplante Befehl beendet wurde, Status aktualisieren."""
        if self._last_executed_id is not None and result.command_id == self._last_executed_id:
            self._last_executed_id = None
