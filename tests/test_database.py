import sqlite3

from src.database import connection
from src.database.models import STATUS_NEVER_RUN, Command, StatusKind, classify_status
from src.services.command_service import CommandService


def _make(title="Titel", command="echo hi", **kwargs) -> Command:
    return Command(title=title, command=command, **kwargs)


def test_crud_roundtrip(db):
    service = CommandService()
    created = service.create(
        _make(
            description="Beschreibung",
            tags=["a", "ä"],
            open_terminal=False,
            working_directory="/tmp",
        )
    )
    assert created.id is not None

    loaded = service.get_by_id(created.id)
    assert loaded.title == "Titel"
    assert loaded.tags == ["a", "ä"]
    assert loaded.open_terminal is False
    assert loaded.last_status == STATUS_NEVER_RUN
    assert loaded.created_at is not None

    loaded.title = "Neu"
    service.update(loaded)
    assert service.get_by_id(created.id).title == "Neu"

    assert service.delete(created.id) is True
    assert service.get_by_id(created.id) is None
    assert service.delete(created.id) is False


def test_search_matches_all_fields_and_escapes_wildcards(db):
    service = CommandService()
    service.create(_make("Docker prune", "docker system prune", tags=["docker"]))
    service.create(_make("Disk", "df -h", description="Speicherplatz"))
    service.create(_make("Prozent", "echo 100%"))
    service.create(_make("Unter_strich", "echo x"))

    assert [c.title for c in service.search("docker")] == ["Docker prune"]
    assert [c.title for c in service.search("speicher")] == ["Disk"]
    assert [c.title for c in service.search("%")] == ["Prozent"]
    assert [c.title for c in service.search("_")] == ["Unter_strich"]
    assert len(service.search("   ")) == 4


def test_filter_by_tag_is_exact_and_case_insensitive(db):
    service = CommandService()
    service.create(_make("A", tags=["Docker"]))
    service.create(_make("B", tags=["docker-compose"]))
    assert [c.title for c in service.filter_by_tag("docker")] == ["A"]


def test_update_execution_status(db):
    service = CommandService()
    cmd = service.create(_make())
    assert service.update_execution_status(cmd.id, "Erfolgreich (Exit: 0)", "out")
    loaded = service.get_by_id(cmd.id)
    assert loaded.status_kind is StatusKind.SUCCESS
    assert loaded.last_output == "out"
    assert not service.update_execution_status(9999, "x")


def test_migration_from_legacy_schema(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE commands (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, command TEXT,"
        " last_status TEXT DEFAULT 'Noch nie ausgeführt')"
    )
    conn.execute("INSERT INTO commands (title, command) VALUES ('Alt', 'ls')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(connection, "DB_PATH", str(path))
    connection.init_db()
    connection.init_db()  # idempotent

    loaded = CommandService().get_all()
    assert len(loaded) == 1
    assert loaded[0].title == "Alt"
    assert loaded[0].open_terminal is True
    assert loaded[0].tags == []
    assert loaded[0].created_at is not None


def test_classify_status():
    assert classify_status("Erfolgreich (Exit: 0)") is StatusKind.SUCCESS
    assert classify_status("Fehler (Exit: 2)") is StatusKind.ERROR
    assert classify_status("Abgebrochen") is StatusKind.ERROR
    assert classify_status("Läuft ...") is StatusKind.RUNNING
    assert classify_status("Läuft...") is StatusKind.RUNNING
    assert classify_status(STATUS_NEVER_RUN) is StatusKind.IDLE
