"""Verwaltet System-Cron-Jobs für geplante Befehle.

Synchronisiert die `schedule_interval`-Spalte der Datenbank mit echten crontab-Einträgen,
damit Befehle auch ausgeführt werden, wenn die GUI-App geschlossen ist.
"""

import logging
import os
import re
import shutil
import subprocess
import sys

from src.database.models import ScheduleInterval

logger = logging.getLogger(__name__)

# Marker, der jeden Command-Vault-Cron-Eintrag identifiziert
CRON_MARKER = "# command-vault:cmd_{command_id}"

# Pfad zum Wrapper-Skript (relativ zum Projekt-Root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WRAPPER_SCRIPT = os.path.join(_PROJECT_ROOT, "src", "cli", "run_scheduled.py")

# Python-Interpreter für Cron-Umgebung explizit setzen
_PYTHON = sys.executable or shutil.which("python3") or "/usr/bin/python3"


# ------------------------------------------------------------------- Cron expression mapping

def _interval_to_cron(interval: ScheduleInterval) -> str | None:
    """Konvertiert ein ScheduleInterval in einen Cron-Zeit-Ausdruck (5 Felder)."""
    mapping = {
        ScheduleInterval.EVERY_MINUTE: "* * * * *",
        ScheduleInterval.EVERY_5_MINUTES: "*/5 * * * *",
        ScheduleInterval.EVERY_15_MINUTES: "*/15 * * * *",
        ScheduleInterval.EVERY_30_MINUTES: "*/30 * * * *",
        ScheduleInterval.EVERY_HOUR: "0 * * * *",
        ScheduleInterval.EVERY_6_HOURS: "0 */6 * * *",
        ScheduleInterval.EVERY_12_HOURS: "0 */12 * * *",
        ScheduleInterval.ONCE_DAILY: "0 0 * * *",
        ScheduleInterval.ONCE_WEEKLY: "0 0 * * 0",
    }
    return mapping.get(interval)


def _build_cron_entry(command_id: int, interval: ScheduleInterval) -> str | None:
    """Baut eine vollständige crontab-Zeile mit Zeit-Ausdruck."""
    cron_time = _interval_to_cron(interval)
    if cron_time is None:
        return None
    if not _PYTHON:
        return None

    cmd = f'{_PYTHON} {_WRAPPER_SCRIPT} {command_id}'
    return f"{cron_time} {cmd}  # command-vault:cmd_{command_id}"


# ------------------------------------------------------------------- crontab operations

def _is_linux() -> bool:
    return sys.platform == "linux"


def _has_crontab() -> bool:
    """Prüft ob crontab-Befehl verfügbar ist."""
    return shutil.which("crontab") is not None


def _read_crontab() -> str:
    """Liest die aktuelle crontab und gibt sie als String zurück."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Exit-Code 1 bedeutet "keine crontab", ist kein Fehler
        if result.returncode == 0:
            return result.stdout
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _write_crontab(content: str) -> None:
    """Schreibt eine neue crontab."""
    process = subprocess.Popen(
        ["crontab", "-"],
        stdin=subprocess.PIPE,
        text=True,
    )
    process.communicate(input=content, timeout=10)


def _is_command_vault_line(line: str) -> bool:
    """Prüft ob eine crontab-Zeile zu Command Vault gehört."""
    return "# command-vault:" in line


def _extract_command_id(line: str) -> int | None:
    """Extrahiert die command_id aus einer Command-Vault-Cron-Zeile."""
    match = re.search(r"command-vault:cmd_(\d+)", line)
    if match:
        return int(match.group(1))
    return None


def _get_existing_cron_ids() -> dict[int, str]:
    """Liest alle Command-Vault-Cron-Einträge aus der crontab.
    
    Returns:
        Dict von command_id -> crontab-Zeile
    """
    crontab = _read_crontab()
    ids: dict[int, str] = {}
    for line in crontab.splitlines():
        if _is_command_vault_line(line):
            cmd_id = _extract_command_id(line)
            if cmd_id is not None:
                ids[cmd_id] = line
    return ids


# ------------------------------------------------------------------- public API

def is_available() -> bool:
    """Prüft ob Cron-Integration auf diesem System verfügbar ist."""
    return _is_linux() and _has_crontab()


def sync_cron(scheduled_commands: list) -> None:
    """Synchronisiert die crontab mit den geplanten Befehlen.
    
    - Neue/geänderte Befehle werden hinzugefügt/aktualisiert.
    - Gelöschte Befehle werden aus der crontab entfernt.
    
    Args:
        scheduled_commands: Liste von Command-Objekten mit aktivem Schedule.
    """
    if not is_available():
        return

    # Aktuelle Cron-Einträge lesen
    existing = _get_existing_cron_ids()
    
    # IDs der aktuellen geplanten Befehle
    current_ids = {cmd.id for cmd in scheduled_commands if cmd.id is not None}
    
    # Neue/aktualisierte Einträge bauen
    new_entries: dict[int, str] = {}
    for cmd in scheduled_commands:
        if cmd.id is None:
            continue
        interval = cmd.schedule
        if interval == ScheduleInterval.NONE or interval.seconds == 0:
            continue
        entry = _build_cron_entry(cmd.id, interval)
        if entry:
            new_entries[cmd.id] = entry

    # Zu entfernende IDs (in crontab, aber nicht mehr in DB)
    to_remove = set(existing.keys()) - current_ids
    
    # crontab aktualisieren
    crontab = _read_crontab()
    lines = crontab.splitlines() if crontab else []
    
    # Alte Command-Vault-Zeilen entfernen
    filtered = [line for line in lines if not _is_command_vault_line(line)]
    
    # Neue Einträge hinzufügen
    for entry in new_entries.values():
        filtered.append(entry)
    
    # Leerzeile als Trenner, falls Einträge existieren
    if new_entries and filtered and filtered[-1].strip():
        filtered.append("")
    
    _write_crontab("\n".join(filtered) + "\n")
    
    added = set(new_entries.keys()) - set(existing.keys())
    removed = to_remove
    changed = {k for k in new_entries if k in existing and new_entries[k] != existing[k]}
    
    if added or removed or changed:
        logger.info(
            "Cron synchronisiert: +%d, -%d, ~%d",
            len(added), len(removed), len(changed),
        )


def remove_cron_job(command_id: int) -> None:
    """Entfernt einen spezifischen Cron-Job."""
    if not is_available():
        return
    
    crontab = _read_crontab()
    if not crontab:
        return
    
    lines = crontab.splitlines()
    marker = f"command-vault:cmd_{command_id}"
    filtered = [line for line in lines if marker not in line]
    
    if len(filtered) < len(lines):
        _write_crontab("\n".join(filtered) + "\n")
        logger.info("Cron-Job entfernt: cmd_%d", command_id)


def cleanup_all() -> None:
    """Entfernt alle Command-Vault-Cron-Jobs (z. B. beim Deinstallieren)."""
    if not is_available():
        return
    
    crontab = _read_crontab()
    if not crontab:
        return
    
    lines = crontab.splitlines()
    filtered = [line for line in lines if not _is_command_vault_line(line)]
    
    if len(filtered) < len(lines):
        _write_crontab("\n".join(filtered) + "\n")
        logger.info("Alle Command-Vault-Cron-Jobs entfernt")
