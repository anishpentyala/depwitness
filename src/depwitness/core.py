"""Exact validation of one caller-declared functional dependency."""

import csv
import hashlib
import io
from collections import Counter
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


def audit(path, *, determinant, dependent, examples=0, delimiter=",", limits=None):
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
    try:
        source = Path(path)
    except TypeError as exc:
        raise AuditError("input path must be a string or path-like object") from exc
    groups, samples = {}, []
    records = pairs = 0
    try:
        with source.open("rb") as stream:
            raw = stream.read(limits.max_bytes + 1)
        if len(raw) > limits.max_bytes:
            raise AuditError("input byte limit exceeded")
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise AuditError("input must not contain NUL")
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
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
                # n, per-dependent-tuple counts, optional first record ordinal.
                groups[key] = [0, Counter(), number if examples else None]
            group = groups[key]
            n, counts, first = group
            previous = counts[value]
            pairs += n - previous
            if len(samples) < examples and len(counts) == 1 and not previous:
                first_value = next(iter(counts))
                samples.append(
                    {
                        "determinant_values": list(key),
                        "first_record": first,
                        "first_dependent_values": list(first_value),
                        "conflicting_record": number,
                        "conflicting_dependent_values": list(value),
                    }
                )
            group[0] += 1
            counts[value] += 1
            records += 1
    except (OSError, UnicodeError, csv.Error, OverflowError) as exc:
        raise AuditError("unreadable or invalid UTF-8 CSV input") from exc
    violating = affected = removals = repeated = 0
    for n, counts, _ in groups.values():
        repeated += n > 1
        if len(counts) > 1:
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
        "input": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)},
}
