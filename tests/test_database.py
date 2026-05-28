import sqlite3 as sql

import pytest

from modules.database import (
    backup_db,
    insert_row,
    read_row,
    restore_latest_backup,
    try_read_row,
)


@pytest.fixture(autouse=True)
def _isolate_db(monkeypatch, tmp_path):
    test_db = tmp_path / "settings.db"
    test_backup = tmp_path / "backups"
    monkeypatch.setattr("modules.database.DB_PATH", test_db)
    monkeypatch.setattr("modules.database.BACKUP_DIR", test_backup)


def test_create_table(tmp_path):
    test_db = tmp_path / "settings.db"
    with sql.connect(str(test_db)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS settings (staff_channel integer, role_id integer)"
        )
        cursor.execute("SELECT COUNT(*) FROM settings")
        assert cursor.fetchone()[0] == 0


def test_insert_and_read_row(tmp_path):
    test_db = tmp_path / "settings.db"
    with sql.connect(str(test_db)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS settings (staff_channel integer, role_id integer)"
        )
        cursor.execute("INSERT INTO settings VALUES (?, ?)", (123456789, 987654321))

    with sql.connect(str(test_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings")
        rows = cursor.fetchall()
        assert rows == [(123456789, 987654321)]


def test_insert_overwrites_previous(tmp_path):
    test_db = tmp_path / "settings.db"
    with sql.connect(str(test_db)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS settings (staff_channel integer, role_id integer)"
        )
        cursor.execute("INSERT INTO settings VALUES (?, ?)", (1, 2))

    with sql.connect(str(test_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM settings")
        cursor.execute("INSERT INTO settings VALUES (?, ?)", (3, 4))

    with sql.connect(str(test_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings")
        rows = cursor.fetchall()
        assert rows == [(3, 4)]


def test_try_read_row_empty():
    channel, role = try_read_row()
    assert isinstance(channel, int)
    assert isinstance(role, int)
    assert channel == 0
    assert role == 0


def test_backup_db_when_no_db():
    result = backup_db()
    assert result is False


def test_restore_latest_backup_when_no_backups():
    result = restore_latest_backup()
    assert result is False


def test_insert_row_accepts_int_values():
    insert_row(111222333, 444555666)
    rows = read_row()
    assert rows == [(111222333, 444555666)]
