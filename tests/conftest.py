import os

# Muss vor dem ersten Qt-Import gesetzt sein: Tests laufen ohne Display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.database import connection  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    # Eigene Settings-Domain, damit die echten Nutzereinstellungen unberührt bleiben.
    app.setOrganizationName("CommandVaultTests")
    app.setApplicationName("command-vault-tests")
    yield app


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Frische, isolierte Datenbank pro Test."""
    monkeypatch.setattr(connection, "DB_PATH", str(tmp_path / "test.db"))
    connection.init_db()
    return tmp_path / "test.db"
