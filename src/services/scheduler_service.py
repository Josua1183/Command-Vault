"""Verwaltet geplante Befehle über System-Cron-Jobs.

Statt eines In-App-Timers synchronisiert dieser Service die geplanten Befehle
mit echten crontab-Einträgen, sodass sie auch ausgeführt werden, wenn die App
geschlossen ist.

Falls Cron nicht verfügbar ist (z. B. kein Linux), fällt er auf den alten
In-App-Timer zurück.
"""

import logging
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from src.database.models import ScheduleInterval
from src.services.command_service import CommandService
from src.services.cron_service import is_available as cron_is_available
from src.services.cron_service import sync_cron, remove_cron_job, cleanup_all
from src.services.executor_service import ExecutorService, TerminalError

logger = logging.getLogger(__name__)

# Fallback: Wie oft der In-App-Timer prüft (Sekunden), wenn Cron nicht verfügbar ist.
CHECK_INTERVAL_SECONDS = 30

# Mindestens so viel Zeit zwischen zwei geplanten Ausführungen desselben Befehls.
MIN_SCHEDULE_GAP_SECONDS = 10


class SchedulerService(QObject):
    """Synchronisiert geplante Befehle mit System-Cron.

    Falls Cron nicht verfügbar ist, nutzt er einen In-App-Timer als Fallback.
    """

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
        self._running = False

        # Cron-Modus ist primär, Timer ist Fallback
        self._use_cron = cron_is_available()
        if self._use_cron:
            logger.info("Scheduler: System-Cron wird verwendet")
        else:
            logger.info("Scheduler: Cron nicht verfügbar, In-App-Timer wird verwendet")

        if not self._use_cron:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._check_scheduled)

        # Verbinde mit dem Executor, um geplante Ausführungen zu tracken (nur Fallback-Modus)
        if not self._use_cron:
            self._executor_service.execution_finished.connect(self._on_execution_finished)
            self._last_executed_id: int | None = None

    def start(self) -> None:
        """Startet den Scheduler und synchronisiert Cron-Jobs."""
        if self._running:
            return
        self._running = True

        if self._use_cron:
            self._sync_cron()
            logger.info("Scheduler gestartet (System-Cron)")
        else:
            self._timer.start(CHECK_INTERVAL_SECONDS * 1000)
            logger.info("Scheduler gestartet (In-App-Timer, Prüfung alle %d s)", CHECK_INTERVAL_SECONDS)

    def stop(self) -> None:
        """Stoppt den Scheduler."""
        self._running = False
        if not self._use_cron:
            self._timer.stop()
        logger.info("Scheduler gestoppt")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def uses_cron(self) -> bool:
        """Gibt an, ob System-Cron verwendet wird."""
        return self._use_cron

    # ---------------------------------------------------------------- cron sync

    def _sync_cron(self) -> None:
        """Synchronisiert die crontab mit den aktuellen geplanten Befehlen."""
        if not self._use_cron:
            return
        try:
            scheduled = self._command_service.get_scheduled_commands()
            sync_cron(scheduled)
        except Exception:
            logger.exception("Fehler bei Cron-Synchronisation")

    def on_command_changed(self) -> None:
        """Wird aufgerufen, wenn ein Befehl erstellt, aktualisiert oder gelöscht wurde.
        
        Synchronisiert die Cron-Jobs neu.
        """
        if self._running:
            self._sync_cron()

    def on_command_deleted(self, command_id: int) -> None:
        """Wird aufgerufen, wenn ein Befehl gelöscht wurde."""
        if self._use_cron:
            remove_cron_job(command_id)

    def cleanup(self) -> None:
        """Entfernt alle Cron-Jobs (z. B. beim Deinstallieren)."""
        if self._use_cron:
            cleanup_all()

    # ------------------------------------------------------- in-app timer fallback

    def _check_scheduled(self) -> None:
        """Prüft alle geplanten Befehle und führt fällige aus (Fallback-Modus)."""
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
        """Führt einen geplanten Befehl aus (Fallback-Modus)."""
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
