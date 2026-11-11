"""Round 5 / C2: one ordered migration ledger."""

from __future__ import annotations

import sqlite3

import pytest

from harness.migrations import Migration, MigrationRunner


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.row_factory = sqlite3.Row
    return db


def test_applies_each_migration_once_in_order():
    db = _db()
    runner = MigrationRunner(db, "test")
    migrations = [
        Migration("002-second", "second", ("CREATE TABLE b (id TEXT)",)),
        Migration("001-first", "first", ("CREATE TABLE a (id TEXT)",)),
    ]

    applied = runner.apply(migrations)
    assert [migration.id for migration in applied] == ["001-first", "002-second"]
    assert runner.current_version() == "002-second"
    assert runner.apply(migrations) == []
    assert runner.applied() == {"001-first", "002-second"}

    names = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"a", "b", "HarnessMigration"} <= names


def test_a_failed_migration_rolls_back_the_whole_batch():
    db = _db()
    runner = MigrationRunner(db, "test")
    with pytest.raises(sqlite3.OperationalError):
        runner.apply([
            Migration("001-good", "creates", ("CREATE TABLE good (id TEXT)",)),
            Migration("002-bad", "fails", ("THIS IS NOT SQL",)),
        ])

    assert runner.applied() == set()
    names = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "good" not in names


def test_the_ledger_is_per_namespace():
    db = _db()
    first = MigrationRunner(db, "agent-memory")
    second = MigrationRunner(db, "eclipse-memory")
    migration = Migration("001-x", "x", ("CREATE TABLE x (id TEXT)",))

    assert [m.id for m in first.apply([migration])] == ["001-x"]
    assert second.applied() == set()
