"""Private, short-lived SQLite indexes. Cleanup is not secure erasure."""

import json
import sqlite3
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from .core import AuditError


def _call(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except (OSError, sqlite3.Error, TypeError) as exc:
        raise AuditError("temporary dependency storage: " + str(exc)) from exc


def _encode(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


class _DiskCounter:
    def __init__(self, groups, key):
        self.groups, self.key = groups, key

    def __getitem__(self, value):
        row = self.groups.one(
            "SELECT n FROM frequencies WHERE k = ? AND v = ?", (self.key, _encode(value))
        )
        return int(row[0]) if row else 0

    def __setitem__(self, value, n):
        self.groups.write(
            "INSERT OR REPLACE INTO frequencies(k, v, n) VALUES (?, ?, ?)",
            (self.key, _encode(value), str(n)),
        )

    def values(self):
        cursor = self.groups.execute("SELECT n FROM frequencies WHERE k = ?", (self.key,))
        try:
            for row in cursor:
                yield int(row[0])
        except sqlite3.Error as exc:
            raise AuditError("temporary dependency storage: " + str(exc)) from exc
        finally:
            _call(cursor.close)


class _DiskGroups:
    def __init__(self, connection):
        self.connection, self.size = connection, 0

    def execute(self, sql, parameters=()):
        return _call(self.connection.execute, sql, parameters)

    def write(self, sql, parameters=()):
        cursor = self.execute(sql, parameters)
        try:
            return cursor.rowcount
        finally:
            _call(cursor.close)

    def one(self, sql, parameters=()):
        cursor = self.execute(sql, parameters)
        try:
            return _call(cursor.fetchone)
        finally:
            _call(cursor.close)

    def __len__(self):
        return self.size

    def __contains__(self, key):
        return self.one("SELECT 1 FROM groups WHERE k = ?", (_encode(key),)) is not None

    def __getitem__(self, key):
        encoded = _encode(key)
        row = self.one(
            "SELECT n, representative, promoted, first_record FROM groups WHERE k = ?", (encoded,)
        )
        if row is None:
            raise KeyError(key)
        n, representative, promoted, first = row
        return [
            int(n),
            tuple(json.loads(representative)),
            _DiskCounter(self, encoded) if promoted else None,
            int(first) if first is not None else None,
        ]

    def __setitem__(self, key, group):
        encoded = _encode(key)
        n, representative, counts, first = group
        parameters = (
            str(n),
            _encode(representative),
            int(counts is not None),
            str(first) if first is not None else None,
            encoded,
        )
        inserted = self.write(
            "INSERT OR IGNORE INTO groups(n, representative, promoted, first_record, k) "
            "VALUES (?, ?, ?, ?, ?)",
            parameters,
        )
        if inserted:
            self.size += 1
        else:
            self.write(
                "UPDATE groups SET n = ?, representative = ?, promoted = ?, "
                "first_record = ? WHERE k = ?",
                parameters,
            )
        # A group promotes once. Copy only its initial two-tuple Counter;
        # subsequent frequencies stay on disk, including a very large group.
        if isinstance(counts, Counter):
            counter = _DiskCounter(self, encoded)
            for value, count in counts.items():
                counter[value] = count

    def values(self):
        # Read each group payload in this cursor instead of looking it up again
        # by key. Frequency values for promoted groups remain streamed on disk.
        cursor = self.execute(
            "SELECT k, n, representative, promoted, first_record FROM groups ORDER BY rowid"
        )
        try:
            for encoded, n, representative, promoted, first in cursor:
                yield [
                    int(n),
                    tuple(json.loads(representative)),
                    _DiskCounter(self, encoded) if promoted else None,
                    int(first) if first is not None else None,
                ]
        except sqlite3.Error as exc:
            raise AuditError("temporary dependency storage: " + str(exc)) from exc
        finally:
            _call(cursor.close)


@contextmanager
def sqlite_groups(temp_dir=None, *, cleanup_stack=None):
    temporary = _call(TemporaryDirectory, prefix="depwitness-", dir=temp_dir)
    # Batch audits defer these callbacks until all their connections close.
    if cleanup_stack is not None:
        cleanup_stack.callback(_call, temporary.cleanup)
    connection = None
    try:
        path = Path(temporary.name) / "dependency.sqlite3"
        connection = _call(sqlite3.connect, str(path))
        _call(path.chmod, 0o600)
        groups = _DiskGroups(connection)
        groups.write("PRAGMA cache_size = -8192")
        groups.write("PRAGMA temp_store = FILE")
        # Store counts as decimal TEXT and do arithmetic in Python, not SQLite's
        # fixed-width integers or floating-point SUM().
        groups.write(
            "CREATE TABLE groups (k TEXT PRIMARY KEY, n TEXT NOT NULL, "
            "representative TEXT NOT NULL, promoted INTEGER NOT NULL, first_record TEXT)"
        )
        groups.write(
            "CREATE TABLE frequencies (k TEXT NOT NULL, v TEXT NOT NULL, n TEXT NOT NULL, "
            "PRIMARY KEY (k, v))"
        )
        groups.write("BEGIN")
        yield groups
    finally:
        try:
            if connection is not None:
                _call(connection.close)
        finally:
            if cleanup_stack is None:
                _call(temporary.cleanup)
