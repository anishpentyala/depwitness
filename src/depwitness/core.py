"""Exact validation of one caller-declared functional dependency."""

import csv
import hashlib
import io
from collections import Counter
from contextlib import ExitStack, contextmanager
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
def _groups(storage, temp_dir, cleanup_stack=None):
    if storage == "memory":
        yield {}
    else:
        try:
            from .disk import sqlite_groups
        except ImportError as exc:
            raise AuditError("sqlite storage is unavailable in this Python installation") from exc

        with sqlite_groups(temp_dir, cleanup_stack=cleanup_stack) as groups:
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
    determinant, dependent = _dependency(determinant, dependent)
    limits = _options(examples, delimiter, limits, storage, temp_dir)
    try:
        source = Path(path)
    except TypeError as exc:
        raise AuditError("input path must be a string or path-like object") from exc
    with _groups(storage, temp_dir) as groups:
        return _audit(source, determinant, dependent, examples, delimiter, limits, groups)


def _dependency(determinant, dependent):
    determinant = _columns("determinant", determinant)
    dependent = _columns("dependent", dependent)
    if set(determinant) & set(dependent):
        raise AuditError("determinant and dependent columns must be disjoint")
    return determinant, dependent


def _options(examples, delimiter, limits, storage, temp_dir):
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
    return limits


def audit_many(
    path,
    *,
    rules,
    examples=0,
    delimiter=",",
    limits=None,
    storage="memory",
    temp_dir=None,
    max_total_groups=100000,
):
    """Check 1-100 declared dependencies against one complete read of a CSV.

    Each rule is a mapping with exactly determinant and dependent column lists.
    Rules and reports retain caller order. Any invalid input or rule fails the
    entire batch. Removal counts apply separately, never jointly across rules.
    """
    if not isinstance(rules, (list, tuple)) or not 1 <= len(rules) <= 100:
        raise AuditError("rules must be a list or tuple containing 1 to 100 rules")
    _integer("max_total_groups", max_total_groups, 1)
    policies = []
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"determinant", "dependent"}:
            raise AuditError("each rule must contain exactly determinant and dependent")
        policies.append(_dependency(rule["determinant"], rule["dependent"]))
    limits = _options(examples, delimiter, limits, storage, temp_dir)
    try:
        source = Path(path)
    except TypeError as exc:
        raise AuditError("input path must be a string or path-like object") from exc
    # Close every batch connection before removing any directory: recursive
    # removal itself needs file descriptors, including after setup exhaustion.
    with ExitStack() as cleanup_stack, ExitStack() as stack:
        states = [
            _RuleState(
                left,
                right,
                examples,
                limits,
                stack.enter_context(_groups(storage, temp_dir, cleanup_stack)),
            )
            for left, right in policies
        ]
        reports = _scan(source, states, delimiter, limits, max_total_groups)
    return {
        "schema_version": 1,
        "passed": all(r["passed"] for r in reports),
        "rules": reports,
        "max_total_groups": max_total_groups,
    }


class _RuleState:
    def __init__(self, determinant, dependent, examples, limits, groups):
        self.determinant, self.dependent = determinant, dependent
        self.examples, self.limits, self.groups = examples, limits, groups
        self.samples, self.pairs = [], 0

    def bind(self, header):
        if not set(self.determinant + self.dependent).issubset(header):
            raise AuditError("selected column missing from header")
        self.left = tuple(header.index(x) for x in self.determinant)
        self.right = tuple(header.index(x) for x in self.dependent)

    def add(self, row, number):
        groups, examples, limits = self.groups, self.examples, self.limits
        key = tuple(row[i] for i in self.left)
        value = tuple(row[i] for i in self.right)
        if key not in groups:
            if len(groups) >= limits.max_groups:
                raise AuditError("determinant group limit exceeded")
            # Keep a single representative until a second RHS tuple occurs.
            # n, representative, optional per-tuple counts, first ordinal.
            groups[key] = [0, value, None, number if examples else None]
        group = groups[key]
        n, representative, counts, first = group
        if counts is None and value != representative:
            if len(self.samples) < examples:
                self.samples.append(
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
            self.pairs += n - counts[value]
            counts[value] += 1
        group[0] += 1
        groups[key] = group

    def report(self, records, delimiter, bounded):
        violating = affected = removals = repeated = 0
        for n, _, counts, _ in self.groups.values():
            repeated += n > 1
            if counts is not None:
                violating += 1
                affected += n
                removals += n - max(counts.values())
        return {
            "schema_version": 1,
            "passed": not violating,
            "policy": {
                "determinant": list(self.determinant),
                "dependent": list(self.dependent),
                "comparison": "exact_strings_including_empty_no_null_inference",
            },
            "counts": {
                "records": records,
                "determinant_groups": len(self.groups),
                "repeated_determinant_groups": repeated,
                "violating_groups": violating,
                "affected_records": affected,
                "conflicting_record_pairs": self.pairs,
                "minimum_record_removals": removals,
            },
            "examples": self.samples,
            "violating_groups_without_example": violating - len(self.samples),
            "settings": {
                "examples": self.examples,
                "delimiter": delimiter,
                "limits": dict(vars(self.limits)),
            },
            "input": {"sha256": bounded.digest.hexdigest(), "bytes": bounded.count},
        }


def _audit(source, determinant, dependent, examples, delimiter, limits, groups):
    state = _RuleState(determinant, dependent, examples, limits, groups)
    return _scan(source, [state], delimiter, limits)[0]


def _scan(source, states, delimiter, limits, max_total_groups=None):
    records = total_groups = 0
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
                for state in states:
                    state.bind(header)
                for number, row in enumerate(reader, 1):
                    if number > limits.max_records:
                        raise AuditError("input record limit exceeded")
                    if len(row) != len(header):
                        raise AuditError(f"wrong field count at data record {number}")
                    if any(len(x) > limits.max_field_chars for x in row):
                        raise AuditError(f"oversized field at data record {number}")
                    for state in states:
                        previous = len(state.groups)
                        state.add(row, number)
                        total_groups += len(state.groups) - previous
                        if max_total_groups is not None and total_groups > max_total_groups:
                            raise AuditError("batch total determinant group limit exceeded")
                    records += 1
    except (OSError, UnicodeError, csv.Error, OverflowError) as exc:
        raise AuditError("unreadable or invalid UTF-8 CSV input") from exc
    return [state.report(records, delimiter, bounded) for state in states]
