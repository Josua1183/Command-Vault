"""Tests für Kategorien, Schedule-Intervalle und den Scheduler-Service."""

import pytest

from src.database import connection
from src.database.models import Command, ScheduleInterval
from src.services.command_service import CommandService


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Frische, isolierte Datenbank pro Test."""
    monkeypatch.setattr(connection, "DB_PATH", str(tmp_path / "test.db"))
    connection.init_db()
    return tmp_path / "test.db"


@pytest.fixture
def service(db):
    return CommandService()


# ------------------------------------------------------------------ ScheduleInterval


class TestScheduleInterval:
    """Tests ohne DB – ScheduleInterval ist rein rechnerisch."""

    @pytest.mark.usefixtures("db")
    def test_none_has_zero_seconds(self):
        assert ScheduleInterval.NONE.seconds == 0

    @pytest.mark.usefixtures("db")
    def test_every_minute(self):
        assert ScheduleInterval.EVERY_MINUTE.seconds == 60

    @pytest.mark.usefixtures("db")
    def test_every_hour(self):
        assert ScheduleInterval.EVERY_HOUR.seconds == 3600

    @pytest.mark.usefixtures("db")
    def test_once_daily(self):
        assert ScheduleInterval.ONCE_DAILY.seconds == 86400

    @pytest.mark.usefixtures("db")
    def test_once_weekly(self):
        assert ScheduleInterval.ONCE_WEEKLY.seconds == 604800

    @pytest.mark.usefixtures("db")
    def test_labels_are_german(self):
        assert "täglich" in ScheduleInterval.ONCE_DAILY.label
        assert "Stündlich" == ScheduleInterval.EVERY_HOUR.label

    @pytest.mark.usefixtures("db")
    def test_all_intervals_have_labels(self):
        for interval in ScheduleInterval:
            assert interval.label, f"{interval.value} has no label"


# ------------------------------------------------------------------ Command model


class TestCommandModel:
    def test_default_schedule_is_none(self, db):
        cmd = Command()
        assert cmd.schedule == ScheduleInterval.NONE

    def test_schedule_property_round_trip(self, db):
        cmd = Command()
        cmd.schedule = ScheduleInterval.ONCE_DAILY
        assert cmd.schedule == ScheduleInterval.ONCE_DAILY
        assert cmd.schedule_interval == "once_daily"

    def test_invalid_schedule_falls_back_to_none(self, db):
        cmd = Command(schedule_interval="invalid_value")
        assert cmd.schedule == ScheduleInterval.NONE

    def test_category_field_exists(self, db):
        cmd = Command(category="System")
        assert cmd.category == "System"

    def test_from_row_with_new_columns(self, service):
        """Testet from_row mit allen neuen Spalten."""
        saved = service.create(
            Command(
                title="Test",
                command="echo 1",
                category="Monitoring",
                schedule_interval=ScheduleInterval.EVERY_HOUR.value,
            )
        )
        cmd = service.get_by_id(saved.id)
        assert cmd is not None
        assert cmd.category == "Monitoring"
        assert cmd.schedule == ScheduleInterval.EVERY_HOUR

    def test_from_row_without_new_columns(self, service):
        """Testet from_row mit Default-Werten."""
        saved = service.create(Command(title="Alt", command="echo alt"))
        cmd = service.get_by_id(saved.id)
        assert cmd is not None
        assert cmd.category == ""
        assert cmd.schedule == ScheduleInterval.NONE


# ------------------------------------------------------------------ Service: Kategorien


class TestCategoryService:
    def test_get_categories_empty(self, service):
        assert service.get_categories() == []

    def test_get_categories_after_create(self, service):
        service.create(Command(title="A", command="echo a", category="System"))
        service.create(Command(title="B", command="echo b", category="Docker"))
        service.create(Command(title="C", command="echo c", category="System"))
        cats = service.get_categories()
        assert cats == ["Docker", "System"]

    def test_filter_by_category(self, service):
        service.create(Command(title="A", command="echo a", category="System"))
        service.create(Command(title="B", command="echo b", category="Docker"))
        service.create(Command(title="C", command="echo c", category="System"))
        result = service.filter_by_category("System")
        assert len(result) == 2
        assert all(c.category == "System" for c in result)

    def test_filter_by_empty_category_returns_all(self, service):
        service.create(Command(title="A", command="echo a", category="System"))
        service.create(Command(title="B", command="echo b"))
        result = service.filter_by_category("")
        assert len(result) == 2

    def test_category_persisted_after_update(self, service):
        saved = service.create(Command(title="A", command="echo a", category="Alt"))
        saved.category = "Neu"
        service.update(saved)
        updated = service.get_by_id(saved.id)
        assert updated is not None
        assert updated.category == "Neu"

    def test_category_removed_from_list_on_delete(self, service):
        service.create(Command(title="A", command="echo a", category="Temp"))
        assert "Temp" in service.get_categories()
        service.delete(service.get_all()[0].id)
        assert "Temp" not in service.get_categories()


# ------------------------------------------------------------------ Service: Schedule


class TestScheduleService:
    def test_get_scheduled_commands_empty(self, service):
        service.create(Command(title="A", command="echo a"))
        assert service.get_scheduled_commands() == []

    def test_get_scheduled_commands_returns_only_scheduled(self, service):
        service.create(
            Command(
                title="A",
                command="echo a",
                schedule_interval=ScheduleInterval.ONCE_DAILY.value,
            )
        )
        service.create(Command(title="B", command="echo b"))
        scheduled = service.get_scheduled_commands()
        assert len(scheduled) == 1
        assert scheduled[0].title == "A"

    def test_update_scheduled_run(self, service):
        saved = service.create(
            Command(
                title="A",
                command="echo a",
                schedule_interval=ScheduleInterval.EVERY_HOUR.value,
            )
        )
        assert saved.last_scheduled_run is None
        service.update_scheduled_run(saved.id)
        updated = service.get_by_id(saved.id)
        assert updated is not None
        assert updated.last_scheduled_run is not None

    def test_schedule_persisted_after_update(self, service):
        saved = service.create(Command(title="A", command="echo a"))
        saved.schedule = ScheduleInterval.EVERY_30_MINUTES
        service.update(saved)
        updated = service.get_by_id(saved.id)
        assert updated is not None
        assert updated.schedule == ScheduleInterval.EVERY_30_MINUTES

    def test_search_includes_category_and_schedule(self, service):
        """Suche soll auch Befehle mit Kategorie/Schedule finden."""
        service.create(
            Command(
                title="System prüfen",
                command="uptime",
                category="Monitoring",
                schedule_interval=ScheduleInterval.EVERY_HOUR.value,
            )
        )
        results = service.search("System")
        assert len(results) == 1
        assert results[0].category == "Monitoring"
