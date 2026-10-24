import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

APP_DIR_NAME = "command-vault"
DB_FILE_NAME = "commands.db"
SCHEMA_VERSION = 2

# Kann in Tests oder per Code überschrieben werden.
DB_PATH: str | None = None

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        command TEXT NOT NULL,
        description TEXT DEFAULT '',
        working_directory TEXT DEFAULT '',
        tags TEXT DEFAULT '[]',
        open_terminal INTEGER DEFAULT 1,
        last_status TEXT DEFAULT 'Noch nie ausgeführt',
        last_output TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    )
"""

# Spalten, die bei älteren Datenbanken (id, title, command, last_status) fehlen.
_MIGRATION_COLUMNS = {
    "description": "TEXT DEFAULT ''",
    "working_directory": "TEXT DEFAULT ''",
    "tags": "TEXT DEFAULT '[]'",
    "open_terminal": "INTEGER DEFAULT 1",
    "last_output": "TEXT DEFAULT ''",
    "created_at": "TEXT",
    "updated_at": "TEXT",
    "category": "TEXT DEFAULT ''",
    "schedule_interval": "TEXT DEFAULT 'none'",
    "last_scheduled_run": "TEXT",
}


def get_db_path() -> Path:
    """Pfad der Datenbank: Override > $COMMAND_VAULT_DB > XDG-Datenverzeichnis."""
    if DB_PATH:
        return Path(DB_PATH)
    env_path = os.environ.get("COMMAND_VAULT_DB")
    if env_path:
        return Path(env_path).expanduser()
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return data_home / APP_DIR_NAME / DB_FILE_NAME


def get_connection() -> sqlite3.Connection:
    """Öffnet eine neue Verbindung (Aufrufer muss sie schließen)."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """Verbindung mit Commit bei Erfolg, Rollback bei Fehler und sicherem Schließen."""
    conn = get_connection()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _import_legacy_database(target: Path) -> None:
    """Übernimmt die frühere Projekt-Datenbank beim ersten Start (Kopie, kein Verschieben)."""
    legacy = _PROJECT_ROOT / DB_FILE_NAME
    if target.exists() or not legacy.is_file():
        return
    try:
        source = sqlite3.connect(legacy)
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
            source.close()
        logger.info("Bestehende Datenbank von %s nach %s übernommen", legacy, target)
    except sqlite3.Error:
        logger.exception("Übernahme der bestehenden Datenbank fehlgeschlagen")
        target.unlink(missing_ok=True)


def init_db() -> None:
    """Legt die Datenbank an bzw. migriert sie auf das aktuelle Schema."""
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH is None and "COMMAND_VAULT_DB" not in os.environ:
        _import_legacy_database(path)

    conn = get_connection()
    try:
        with conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_TABLE)
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(commands)")}
            for column, definition in _MIGRATION_COLUMNS.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE commands ADD COLUMN {column} {definition}")
            conn.execute(
                "UPDATE commands SET created_at = datetime('now') WHERE created_at IS NULL"
            )
            conn.execute(
                "UPDATE commands SET updated_at = datetime('now') WHERE updated_at IS NULL"
            )
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    finally:
        conn.close()
