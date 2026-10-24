import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

STATUS_NEVER_RUN = "Noch nie ausgeführt"
STATUS_RUNNING = "Läuft ..."
STATUS_IN_TERMINAL = "Im Terminal gestartet"
STATUS_CANCELLED = "Abgebrochen"
STATUS_TIMEOUT = "Zeitüberschreitung"


def status_success(exit_code: int) -> str:
    return f"Erfolgreich (Exit: {exit_code})"


def status_error(exit_code: int) -> str:
    return f"Fehler (Exit: {exit_code})"


class StatusKind(StrEnum):
    """Grobe Einordnung eines Status-Textes (für Farben/Icons in der UI)."""

    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


def classify_status(status: str) -> StatusKind:
    text = (status or "").lower()
    if "erfolgreich" in text:
        return StatusKind.SUCCESS
    if text.startswith(("fehler", "abgebrochen", "zeitüberschreitung")):
        return StatusKind.ERROR
    if text.startswith("läuft"):
        return StatusKind.RUNNING
    return StatusKind.IDLE


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


class ScheduleInterval(StrEnum):
    """Wiederholungsintervalle für automatisierte Ausführung."""

    NONE = "none"
    EVERY_MINUTE = "every_minute"
    EVERY_5_MINUTES = "every_5_minutes"
    EVERY_15_MINUTES = "every_15_minutes"
    EVERY_30_MINUTES = "every_30_minutes"
    EVERY_HOUR = "every_hour"
    EVERY_6_HOURS = "every_6_hours"
    EVERY_12_HOURS = "every_12_hours"
    ONCE_DAILY = "once_daily"
    ONCE_WEEKLY = "once_weekly"

    @property
    def seconds(self) -> int:
        """Intervall in Sekunden (0 = kein Schedule)."""
        return {
            ScheduleInterval.EVERY_MINUTE: 60,
            ScheduleInterval.EVERY_5_MINUTES: 300,
            ScheduleInterval.EVERY_15_MINUTES: 900,
            ScheduleInterval.EVERY_30_MINUTES: 1800,
            ScheduleInterval.EVERY_HOUR: 3600,
            ScheduleInterval.EVERY_6_HOURS: 21600,
            ScheduleInterval.EVERY_12_HOURS: 43200,
            ScheduleInterval.ONCE_DAILY: 86400,
            ScheduleInterval.ONCE_WEEKLY: 604800,
        }.get(self, 0)

    @property
    def label(self) -> str:
        """Menschlich lesbare Beschriftung."""
        return {
            ScheduleInterval.NONE: "Nicht automatisiert",
            ScheduleInterval.EVERY_MINUTE: "Jede Minute",
            ScheduleInterval.EVERY_5_MINUTES: "Alle 5 Minuten",
            ScheduleInterval.EVERY_15_MINUTES: "Alle 15 Minuten",
            ScheduleInterval.EVERY_30_MINUTES: "Alle 30 Minuten",
            ScheduleInterval.EVERY_HOUR: "Stündlich",
            ScheduleInterval.EVERY_6_HOURS: "Alle 6 Stunden",
            ScheduleInterval.EVERY_12_HOURS: "Alle 12 Stunden",
            ScheduleInterval.ONCE_DAILY: "Einmal täglich",
            ScheduleInterval.ONCE_WEEKLY: "Einmal wöchentlich",
        }.get(self, self.value)


@dataclass
class Command:
    """Data model for a stored command."""

    id: int | None = None
    title: str = ""
    command: str = ""
    description: str = ""
    working_directory: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    open_terminal: bool = True
    schedule_interval: str = ScheduleInterval.NONE.value
    last_scheduled_run: datetime | None = None
    last_status: str = STATUS_NEVER_RUN
    last_output: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def schedule(self) -> ScheduleInterval:
        """Liefert das ScheduleInterval aus dem gespeicherten String."""
        try:
            return ScheduleInterval(self.schedule_interval)
        except ValueError:
            return ScheduleInterval.NONE

    @schedule.setter
    def schedule(self, value: ScheduleInterval) -> None:
        self.schedule_interval = value.value

    @property
    def status_kind(self) -> StatusKind:
        return classify_status(self.last_status)

    def tags_to_json(self) -> str:
        """Serialize tags list to JSON string for storage."""
        return json.dumps(self.tags, ensure_ascii=False)

    @staticmethod
    def tags_from_json(json_str: str | None) -> list[str]:
        """Deserialize tags from JSON string."""
        if not json_str:
            return []
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError, TypeError:
            return []
        if not isinstance(data, list):
            return []
        return [str(tag) for tag in data]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Command:
        """Create a Command instance from a sqlite3.Row."""

        # sqlite3.Row hat kein .get() – nutze try/except für neue Spalten,
        # die bei älteren Datenbanken noch fehlen könnten.
        def _col(name: str, default=""):
            try:
                return row[name]
            except KeyError:
                return default

        open_terminal = _col("open_terminal", 1)
        return cls(
            id=row["id"],
            title=row["title"] or "",
            command=row["command"] or "",
            description=_col("description") or "",
            working_directory=_col("working_directory") or "",
            category=_col("category") or "",
            tags=cls.tags_from_json(_col("tags")),
            open_terminal=True if open_terminal is None else bool(open_terminal),
            schedule_interval=_col("schedule_interval") or ScheduleInterval.NONE.value,
            last_scheduled_run=_parse_datetime(_col("last_scheduled_run")),
            last_status=row["last_status"] or STATUS_NEVER_RUN,
            last_output=_col("last_output") or "",
            created_at=_parse_datetime(_col("created_at")),
            updated_at=_parse_datetime(_col("updated_at")),
        )
