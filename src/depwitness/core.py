"""Exact validation of one caller-declared functional dependency."""

import csv
import hashlib
import io
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class AuditError(ValueError):
    """No complete audit can be returned under the declared contract."""


def _integer(name, value, minimum):
    if type(value) is not int or value < minimum:
        raise AuditError(f"{name} must be an integer >= {minimum}")


@dataclass(frozen=True)
class Limits:
    """Input acceptance caps, not hard RAM or runtime bounds."""

    max_bytes: int = 16777216
    max_records: int = 100000
    max_columns: int = 256
    max_field_chars: int = 1024
    max_groups: int = 100000

    def __post_init__(self):
        for name, value in vars(self).items():
            _integer(name, value, 1)


def _columns(name, values):
    if not isinstance(values, (list, tuple)) or not values:
        raise AuditError(f"{name} must be a nonempty list or tuple of column names")
    result = tuple(values)
    if any(not isinstance(x, str) or not x.strip() for x in result):
        raise AuditError(f"{name} needs nonblank string column names")
    if len(set(result)) != len(result):
        raise AuditError(f"{name} must not repeat a column")
    return result


class _InputReader(io.RawIOBase):
    """Bound and hash the bytes consumed by the incremental UTF-8 decoder."""

    def __init__(self, source, limit):
        self.source = source
        self.limit = limit
        self.count = 0
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.source.read(min(len(buffer), self.limit - self.count + 1))
        self.count += len(data)
        if self.count > self.limit:
            raise AuditError("input byte limit exceeded")
        if b"\x00" in data:
            raise AuditError("input must not contain NUL")
        self.digest.update(data)
        buffer[: len(data)] = data
        return len(data)


@contextmanager
def _groups(storage, temp_dir):
    if storage == "memory":
        yield {}
    else:
        try:
            from .disk import sqlite_groups
        except ImportError as exc:
            raise AuditError("sqlite storage is unavailable in this Python installation") from exc

        with sqlite_groups(temp_dir) as groups:
            yield groups


def audit(
    path,
    *,
    determinant,
    dependent,
    examples=0,
    delimiter=",",
    limits=None,
    storage="memory",
    temp_dir=None,
):
    """Return the full exact-string FD report, or raise AuditError.

    Empty strings and spellings like NA or NULL are literal values. No rows
    are excluded, no types inferred, no trimming or Unicode normalization.
    """
    determinant = _columns("determinant", determinant)
    dependent = _columns("dependent", dependent)
    if set(determinant) & set(dependent):
        raise AuditError("determinant and dependent columns must be disjoint")
    _integer("examples", examples, 0)
    if examples > 1000:
        raise AuditError("examples must be <= 1000")
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '\r\n\x00"\ufeff':
        raise AuditError("delimiter must be one character other than quote, NUL, BOM or newline")
    if limits is None:
        limits = Limits()
    if type(limits) is not Limits:
        raise AuditError("limits must be a Limits instance")
    if not isinstance(storage, str) or storage not in ("memory", "sqlite"):
        raise AuditError("storage must be memory or sqlite")
    if storage == "memory" and temp_dir is not None:
        raise AuditError("temp_dir requires sqlite storage")
    try:
        source = Path(path)
    except TypeError as exc:
        raise AuditError("input path must be a string or path-like object") from exc
    with _groups(storage, temp_dir) as groups:
        return _audit(source, determinant, dependent, examples, delimiter, limits, groups)


def _audit(source, determinant, dependent, examples, delimiter, limits, groups):
    samples = []
    records = pairs = 0
    try:
        with source.open("rb") as stream:
            bounded = _InputReader(stream, limits.max_bytes)
            with io.TextIOWrapper(
                io.BufferedReader(bounded), encoding="utf-8-sig", newline=""
            ) as text:
                reader = csv.reader(text, delimiter=delimiter, strict=True)
                header = next(reader, None)
                if not header or len(header) > limits.max_columns:
                    raise AuditError("missing header or input column limit exceeded")
                if any(not x.strip() or len(x) > limits.max_field_chars for x in header):
                    raise AuditError("blank or oversized header name")
                if len(set(header)) != len(header):
                    raise AuditError("duplicate header name")
                if not set(determinant + dependent).issubset(header):
                    raise AuditError("selected column missing from header")
                left = tuple(header.index(x) for x in determinant)
                right = tuple(header.index(x) for x in dependent)
                for number, row in enumerate(reader, 1):
                    if number > limits.max_records:
                        raise AuditError("input record limit exceeded")
                    if len(row) != len(header):
                        raise AuditError(f"wrong field count at data record {number}")
                    if any(len(x) > limits.max_field_chars for x in row):
                        raise AuditError(f"oversized field at data record {number}")
                    key = tuple(row[i] for i in left)
                    value = tuple(row[i] for i in right)
                    if key not in groups:
                        if len(groups) >= limits.max_groups:
                            raise AuditError("determinant group limit exceeded")
                        # Keep a single representative until a second RHS tuple occurs.
                        # n, representative, optional per-tuple counts, first ordinal.
                        groups[key] = [0, value, None, number if examples else None]
                    group = groups[key]
                    n, representative, counts, first = group
                    if counts is None and value != representative:
                        if len(samples) < examples:
                            samples.append(
                                {
                                    "determinant_values": list(key),
                                    "first_record": first,
                                    "first_dependent_values": list(representative),
                                    "conflicting_record": number,
                                    "conflicting_dependent_values": list(value),
                                }
                            )
                        counts = Counter({representative: n})
                        group[2] = counts
                    if counts is not None:
                        pairs += n - counts[value]
                        counts[value] += 1
                    group[0] += 1
                    groups[key] = group
                    records += 1
    except (OSError, UnicodeError, csv.Error, OverflowError) as exc:
        raise AuditError("unreadable or invalid UTF-8 CSV input") from exc
    violating = affected = removals = repeated = 0
    for n, _, counts, _ in groups.values():
        repeated += n > 1
        if counts is not None:
            violating += 1
            affected += n
            removals += n - max(counts.values())
    return {
        "schema_version": 1,
        "passed": not violating,
        "policy": {
            "determinant": list(determinant),
            "dependent": list(dependent),
            "comparison": "exact_strings_including_empty_no_null_inference",
        },
        "counts": {
            "records": records,
            "determinant_groups": len(groups),
            "repeated_determinant_groups": repeated,
            "violating_groups": violating,
            "affected_records": affected,
            "conflicting_record_pairs": pairs,
            "minimum_record_removals": removals,
        },
        "examples": samples,
        "violating_groups_without_example": violating - len(samples),
        "settings": {"examples": examples, "delimiter": delimiter, "limits": dict(vars(limits))},
        "input": {"sha256": bounded.digest.hexdigest(), "bytes": bounded.count},
    }
