"""CLI-Eintrag: Führt einen geplanten Befehl außerhalb der GUI-App aus.

Wird von Cron-Jobs aufgerufen. Liest den Befehl aus der Datenbank, führt ihn aus
und schreibt Status/Ausgabe sowie den Zeitstempel zurück.
"""

import logging
import os
import subprocess
import sys
from datetime import datetime

# Stelle sicher, dass das Projekt-Root im Pfad ist, damit "src" importierbar ist.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from src.database.connection import get_connection, init_db
from src.database.models import Command, status_error, status_success

logger = logging.getLogger("command-vault.cron")

MAX_OUTPUT = 200_000
DEFAULT_TIMEOUT = 300  # Sekunden


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def run(command_id: int) -> None:
    """Liest Befehl aus der DB, führt ihn aus und aktualisiert die DB."""
    init_db()

    conn = get_connection()
    try:
        # Befehl lesen
        row = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        if row is None:
            logger.warning("Befehl %d nicht gefunden, Cron-Job sollte entfernt werden", command_id)
            return

        cmd = Command.from_row(row)
        logger.info("Cron-Ausführung: %s (ID %d)", cmd.title, cmd.id)

        # Arbeitsverzeichnis bestimmen
        work_dir = (
            os.path.expanduser(cmd.working_directory)
            if cmd.working_directory
            else os.getcwd()
        )

        if not os.path.isdir(work_dir):
            _update_status(conn, command_id, f"Fehler: Arbeitsverzeichnis existiert nicht: {work_dir}", "")
            return

        # Befehl ausführen
        try:
            result = subprocess.run(
                ["bash", "-c", cmd.command],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT,
            )
            output = result.stdout + result.stderr
            exit_code = result.returncode

            if exit_code == 0:
                status = status_success(0)
            else:
                status = status_error(exit_code)

        except subprocess.TimeoutExpired:
            output = "[Zeitüberschreitung nach %d Sekunden]" % DEFAULT_TIMEOUT
            status = "Zeitüberschreitung"
            exit_code = -1
        except OSError as exc:
            output = str(exc)
            status = f"Fehler (Exit: -1)"
            exit_code = -1

        # Ausgabe kürzen, falls nötig
        if len(output) > MAX_OUTPUT:
            output = "[... Ausgabe gekürzt ...]\n" + output[-MAX_OUTPUT:]

        _update_status(conn, command_id, status, output)
        logger.info("Cron-Ausführung beendet: %s — %s", cmd.title, status)

    finally:
        conn.close()


def _update_status(conn, command_id: int, status: str, output: str) -> None:
    conn.execute(
        """UPDATE commands SET last_status = ?, last_output = ?,
           last_scheduled_run = ?, updated_at = ?
           WHERE id = ?""",
        (status, output, _now().isoformat(), _now().isoformat(), command_id),
    )
    conn.commit()


if __name__ == "__main__":
    # Logging in eine Datei, da Cron keine stdout/stderr anzeigt
    log_dir = os.path.join(_PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(log_dir, "cron.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )

    if len(sys.argv) < 2:
        logger.error("Verwendung: run_scheduled.py <command_id>")
        sys.exit(1)

    try:
        cmd_id = int(sys.argv[1])
    except ValueError:
        logger.error("Ungültige command_id: %s", sys.argv[1])
        sys.exit(1)

    run(cmd_id)
