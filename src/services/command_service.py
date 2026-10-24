from datetime import datetime

from src.database.connection import connection
from src.database.models import Command


def _like_pattern(text: str) -> str:
    """Baut ein LIKE-Muster, in dem %, _ und \\ wörtlich behandelt werden."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


class CommandService:
    """Service for CRUD operations on commands."""

    def get_all(self) -> list[Command]:
        """Retrieve all commands, ordered by title."""
        with connection() as conn:
            rows = conn.execute("SELECT * FROM commands ORDER BY title COLLATE NOCASE").fetchall()
        return [Command.from_row(row) for row in rows]

    def get_by_id(self, command_id: int) -> Command | None:
        """Retrieve a single command by ID."""
        with connection() as conn:
            row = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        return Command.from_row(row) if row else None

    def create(self, command: Command) -> Command:
        """Insert a new command and return it with the assigned ID."""
        now = _now()
        with connection() as conn:
            cursor = conn.execute(
                """INSERT INTO commands
                   (title, command, description, working_directory, category, tags,
                    open_terminal, schedule_interval, last_scheduled_run,
                    last_status, last_output, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    command.title,
                    command.command,
                    command.description,
                    command.working_directory,
                    command.category,
                    command.tags_to_json(),
                    int(command.open_terminal),
                    command.schedule_interval,
                    command.last_scheduled_run.isoformat() if command.last_scheduled_run else None,
                    command.last_status,
                    command.last_output,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            command.id = cursor.lastrowid
        command.created_at = now
        command.updated_at = now
        return command

    def update(self, command: Command) -> Command:
        """Update an existing command."""
        if command.id is None:
            raise ValueError("Cannot update a command without an ID")

        now = _now()
        with connection() as conn:
            conn.execute(
                """UPDATE commands SET
                   title = ?, command = ?, description = ?, working_directory = ?,
                   category = ?, tags = ?, open_terminal = ?,
                   schedule_interval = ?, last_scheduled_run = ?,
                   last_status = ?, last_output = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    command.title,
                    command.command,
                    command.description,
                    command.working_directory,
                    command.category,
                    command.tags_to_json(),
                    int(command.open_terminal),
                    command.schedule_interval,
                    command.last_scheduled_run.isoformat() if command.last_scheduled_run else None,
                    command.last_status,
                    command.last_output,
                    now.isoformat(),
                    command.id,
                ),
            )
        command.updated_at = now
        return command

    def delete(self, command_id: int) -> bool:
        """Delete a command by ID. Returns True if a row was deleted."""
        with connection() as conn:
            cursor = conn.execute("DELETE FROM commands WHERE id = ?", (command_id,))
            return cursor.rowcount > 0

    def search(self, query: str) -> list[Command]:
        """Search commands by title, command, description, or tags."""
        query = query.strip()
        if not query:
            return self.get_all()

        pattern = _like_pattern(query)
        with connection() as conn:
            rows = conn.execute(
                """SELECT * FROM commands
                   WHERE title LIKE :p ESCAPE '\\'
                      OR command LIKE :p ESCAPE '\\'
                      OR description LIKE :p ESCAPE '\\'
                      OR tags LIKE :p ESCAPE '\\'
                   ORDER BY title COLLATE NOCASE""",
                {"p": pattern},
            ).fetchall()
        return [Command.from_row(row) for row in rows]

    def filter_by_tag(self, tag: str) -> list[Command]:
        """Filter commands that contain a specific tag."""
        tag = tag.strip()
        if not tag:
            return self.get_all()

        return [cmd for cmd in self.get_all() if tag.casefold() in (t.casefold() for t in cmd.tags)]

    def filter_by_category(self, category: str) -> list[Command]:
        """Filter commands by category. Empty category returns all."""
        category = category.strip()
        if not category:
            return self.get_all()

        with connection() as conn:
            rows = conn.execute(
                "SELECT * FROM commands WHERE category = ? ORDER BY title COLLATE NOCASE",
                (category,),
            ).fetchall()
        return [Command.from_row(row) for row in rows]

    def get_categories(self) -> list[str]:
        """Return all non-empty categories, sorted alphabetically."""
        with connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM commands "
                "WHERE category != '' ORDER BY category COLLATE NOCASE"
            ).fetchall()
        return [row["category"] for row in rows]

    def get_scheduled_commands(self) -> list[Command]:
        """Return all commands with a non-'none' schedule interval."""
        with connection() as conn:
            rows = conn.execute(
                "SELECT * FROM commands "
                "WHERE schedule_interval != 'none' AND schedule_interval IS NOT NULL "
                "ORDER BY title COLLATE NOCASE"
            ).fetchall()
        return [Command.from_row(row) for row in rows]

    def update_scheduled_run(self, command_id: int) -> bool:
        """Update the last_scheduled_run timestamp to now."""
        with connection() as conn:
            cursor = conn.execute(
                "UPDATE commands SET last_scheduled_run = ? WHERE id = ?",
                (_now().isoformat(), command_id),
            )
            return cursor.rowcount > 0

    def update_execution_status(self, command_id: int, status: str, output: str = "") -> bool:
        """Update the last_status and last_output of a command."""
        with connection() as conn:
            cursor = conn.execute(
                """UPDATE commands SET last_status = ?, last_output = ?, updated_at = ?
                   WHERE id = ?""",
                (status, output, _now().isoformat(), command_id),
            )
            return cursor.rowcount > 0
