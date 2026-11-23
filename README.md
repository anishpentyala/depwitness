# depwitness

Find contradictory CSV mappings without confusing repeated rows with broken rules.

[![Tests](https://github.com/anishpentyala/depwitness/actions/workflows/ci.yml/badge.svg)](https://github.com/anishpentyala/depwitness/actions)

## Quickstart

```sh
python -m pip install depwitness
printf 'sku,category\n001,tools\n001,tools\n001,garden\n002,food\n' > products.csv
depwitness products.csv --determinant sku --dependent category
```

The command exits 1 because SKU `001` maps to two categories. Selected fields
from the full JSON report:

```json
{"counts": {"records": 4, "violating_groups": 1, "affected_records": 3, "conflicting_record_pairs": 2, "minimum_record_removals": 1}}
```

The repeated `001,tools` row is allowed. Both copies conflict with `001,garden`.
The tool counts contradictions; it does not choose the correct category or
repair your file. Raw cell examples stay off unless you pass `--examples N` with a positive integer N.

Install from [PyPI](https://pypi.org/project/depwitness/). Python 3.9 or later is required.

## Details

Check whether a caller-declared CSV mapping is consistent: for each exact
combination of determinant values, there must be one exact combination of
dependent values. Repeated identical mappings are allowed. This is a functional
dependency check, not a uniqueness check.

The report counts violating groups, every row in those groups, conflicting
unordered row pairs, and the minimum number of row removals needed to satisfy
**this one declared dependency**. It does not build the row pairs. Counterexamples
are opt-in. Python 3.9 or later, standard library only at runtime.

## Install from source

```sh
# From a checkout of this repository:
python -m pip install .
```

The source checkout is optional; the quickstart above installs from PyPI.

## Check a product catalog

```sh
depwitness examples/products.csv --determinant sku --determinant region \
  --dependent category --examples 2
```

The example declares `(sku, region) -> category`. Five US records for SKU `001`
have categories `tools` (three rows) and `garden` (two). All five rows are affected;
there are **six** conflicting row pairs and **two** minimum removals. The EU
record is a separate group. Repeated `002,US -> food` rows are consistent, even
though their unselected labels differ. The command exits **1** and still emits a
complete JSON report.

A dependency is a rule **you** supply. `ZIP -> city`, for example, may be an
incorrect business rule, even if many rows follow it. A counterexample does not
identify which value is true. Nothing is deleted, repaired, voted into truth,
or uploaded.

## Exact comparison, not inferred nulls or types

- Repeat `--determinant` and `--dependent` for composite tuples. Both lists must
  be nonempty, without repeated columns, and disjoint. Column order is preserved.
- Values are exact CSV strings. `001`, `1`, ` 1`, `A`, `a`, composed and decomposed
  Unicode are different. No trimming, case folding, numeric/date parsing, or
  Unicode normalization.
- Empty strings, `NA` and `NULL` are ordinary literal values on **both** sides.
  There is no null token, null matching policy, ignored row, or missing-value
  inference. This is not SQL NULL semantics or a simulation of a CSV loader.
- The whole CSV is validated, including unselected columns. Empty/whitespace-only
  values are valid, but header names must not be blank or duplicate.
- UTF-8, optionally with an initial UTF-8 BOM. Comma delimiter by default; use
  `--delimiter ';'` if needed. Quoted fields and multiline records use Python's
  `csv.reader(strict=True)` grammar. This is not a universal RFC/dialect validator;
  some quote spellings that other parsers reject are accepted by Python's parser.
- Ragged/blank data records, decoding errors, NUL, parser errors, missing selected
  columns and limit breaches fail without a JSON audit. No dialect autodetection.
  A header-only file has zero records and passes vacuously. It is not evidence
  of useful coverage or future consistency.

## Counts and counterexamples

For one determinant group with dependent-tuple frequencies `n1, n2, ...`:

- It violates the dependency iff more than one dependent tuple occurs.
- All its rows are affected if it violates, including repeated majority values.
- Conflicting unordered row pairs are `sum(ni * nj for i < j)`. Identical dependent
  tuples do not conflict. Counts are Python integers, without float rounding.
- Minimum removals are `sum(ni) - max(ni)`. Summing across groups gives the fewest
  removals that could satisfy this one FD on this file. This is a count, not a
  deletion plan or recommendation. It ignores other constraints, costs,
  record importance, and which value is correct. Ties can have several solutions.

`--examples N` emits at most one pair per violating group, in order of **first
conflict discovery** while reading. Each pair contains the first record in its
group and the first later record with a different dependent tuple. Record numbers
are 1-based **data-record ordinals**, excluding the header, not physical file
line numbers. Embedded newlines do not change them. `violating_groups_without_example`
counts groups not shown, not omitted conflicting pairs.

Without examples, reports contain no input cell values, but **do** reveal selected
column names, counts, policy, byte length and a SHA-256 of the input. This is not
anonymization: predictable inputs can be guessed using a hash. With examples,
raw selected values and record ordinals are included and may be sensitive. No
unselected cells are copied to the report. Reports have `schema_version: 1`.

## Limits, exits and resources

| Option | Default |
| --- | ---: |
| `--max-bytes` | 16,777,216 |
| `--max-records` | 100,000 |
| `--max-columns` | 256 |
| `--max-field-chars` | 1,024 |
| `--max-groups` | 100,000 |
| `--examples` | 0, at most 1,000 |

These are acceptance caps, not hard RAM or runtime bounds. Python's own CSV
field-size limit can also reject a field even if the requested character cap
is larger. Input is decoded and hashed incrementally instead of retaining the
complete raw byte string and decoded text. CSV records, decoder buffers and the
index still take memory; a large record can still be expensive. The index
retains every distinct determinant/dependent tuple and its frequency, not every
row or row pair. Memory grows with buffered input, distinct selected tuples and
their lengths. A group that has only one dependent tuple keeps its count and
representative directly, without a separate frequency dictionary. On its first
conflict, it switches to a full per-tuple counter seeded with all prior repeats.
This avoids that dictionary for consistent groups, but conflicting groups still
need it. The switch adds some work and a representative reference, so this is
not a promise of lower memory or faster execution on every input.
A small example cap does not cap index memory. Incremental input does not make
the whole audit constant-memory. Every accepted input is consumed to EOF before a report is returned;
late byte-limit, NUL, decoder, parser or source-read failures still fail the
audit. If an input has several faults, the first reported diagnostic may change
as validation runs while reading. No network code or telemetry.

With memory storage and selected tuple width `W`, scanning and hash-table aggregation take expected
`O(bytes + records * W)` work, plus a final pass over distinct selected tuples.
Hashing is expected, not a worst-case bound. A dense group with 10,000 rows split
equally across two values represents 25,000,000 conflicting pairs without
materializing them. It still reads every accepted row before returning.

Exit **0**: complete report and declared dependency holds. Exit **1**: complete
report with violations. Exit **2**: invalid/incomplete input, invalid options,
resource or output failure. Invalid input never produces a partial success or
partial violation report. Output I/O failures cannot retract bytes already
written to a failing pipe or filesystem; they are not complete audit delivery.

## Optional SQLite index

The default `--storage memory` keeps the selected-tuple index in RAM. For a
large number of distinct selected tuples, choose `--storage sqlite`:

```sh
depwitness examples/products.csv --determinant sku --determinant region \
  --dependent category --storage sqlite --temp-dir /path/to/private/temp
```

SQLite storage requires Python's `sqlite3` module. If the Python installation
lacks it, memory storage still works and requesting SQLite fails the audit.
`--temp-dir` is optional and requires SQLite storage. It names an **existing**
parent directory; the audit creates a private temporary subdirectory there.
Only selected determinant/dependent tuples, counts and optional first-record
ordinals enter the index, not ignored cell values or whole input rows. A group
with many conflicting dependent values keeps its frequency counter on disk too.
Counts remain exact Python integers, including beyond SQLite's integer range.
Report content, example order, validation and acceptance limits are unchanged;
the same complete input and options produce identical JSON on both backends.
Storage selection is operational and is not included in the report's settings.

The scan loads each group directly, without a separate membership query, and
persists a newly seen group only after counting its first row. This removes
redundant SQLite statements without changing report contents or acceptance
limits. In a local fixture with 300 consistent records across 100 groups, the
complete audit executed 906 SQL statements instead of 1,406, including setup
and summary queries. This is a statement-count observation for that fixture,
not a wall-time, RAM or general speedup claim. New dictionary groups now use a
missing-key exception internally; the memory backend is not claimed faster.

This trades speed and disk space for less RAM in some high-cardinality cases.
SQLite's page cache is configured to about 8 MiB, **not** a hard process-memory
bound. Input records, decoder state and requested examples still use RAM. Small
or repetitive inputs may use more RAM than the memory backend; all measured
local SQLite runs were slower. The default limits still apply and are not raised
automatically. See VALIDATION.md for the measured shapes and costs.

The temporary directory is mode 700 and database mode 600 on POSIX systems.
SQLite storage writes sensitive selected values to disk, even with `--examples 0`.
Use a trusted location with enough free space. The connection is closed and the
directory removed on normal completion and handled failures, including invalid
late input. Storage/close/cleanup errors fail the audit without returning a
report. A forced termination or crash can leave files behind. Cleanup is **not
secure erasure** and does not promise to remove backups, swap or filesystem
traces. This is not an encrypted store, resumable audit or persistent database.

## Library

```python
from depwitness import Limits, audit

report = audit(
    'catalog.csv',
    determinant=['sku', 'region'],
    dependent=['category'],
    examples=0,
    storage='sqlite',  # Optional; memory is the default.
    # temp_dir='/path/to/private/temp',
    limits=Limits(max_records=50000),
)
print(report['counts']['conflicting_record_pairs'])
```

`AuditError` means there is no complete report. Files are read only. Check a
fixed snapshot if another process may rewrite the file while it is being read;
the receipt identifies the bytes actually read, not an atomic filesystem snapshot.
The report is specific to the supplied file and rule, not a data-quality,
correctness, causal, or future-data certificate.

## Existing tools and scope

Functional-dependency validation and discovery are established work.
[Desbordante](https://github.com/Desbordante/desbordante-cli) supports both, along
with several other dependency families. [SemPy](https://learn.microsoft.com/en-us/fabric/data-science/tutorial-data-cleaning-functional-dependencies)
provides dependency discovery and violation inspection in its broader dataframe
workflow. [FDTool](https://pmc.ncbi.nlm.nih.gov/articles/PMC6489977/) describes FD and
candidate-key discovery. SQL grouping or dataframe code can implement this check.

Use those when you need discovery, approximate dependencies, broader profiling,
or their integrations. This project is a small, explicit-rule, source-installable
CSV check with exact conflict counts, bounded opt-in witnesses and no runtime
third-party dependencies. It does not claim a new algorithm, general superiority,
external adoption or benchmark wins. Sources and boundaries are in EVIDENCE.md;
local validation is in VALIDATION.md.

## Check several declared rules in one read

For a catalog with several declared mappings, `audit_many` parses, validates and
hashes the input once, while keeping a separate index and evidence cap per rule:

```python
from depwitness import audit_many

batch = audit_many(
    'catalog.csv',
    rules=[
        {'determinant': ['sku', 'region'], 'dependent': ['category']},
        {'determinant': ['sku'], 'dependent': ['brand']},
    ],
    examples=2,
    max_total_groups=100000,
)
```

Each item in `batch['rules']` has exactly the existing single-rule report shape,
in caller order. The batch has its own `schema_version: 1`, `passed` flag and
`max_total_groups`. It passes only if every rule passes. Duplicate rules are
allowed and counted separately. All input validation runs to EOF even if a
rule already has counterexamples; an invalid rule, late input failure, storage
failure or cleanup failure rejects the entire batch, without a partial report.
Every report describes the same bytes consumed in that one read. This does not
make the file an atomic snapshot if another process rewrites it during reading.

The CLI accepts repeated JSON rules instead of `--determinant`/`--dependent`:

```sh
depwitness catalog.csv \
  --rule '{"determinant":["sku","region"],"dependent":["category"]}' \
  --rule '{"determinant":["sku"],"dependent":["brand"]}' \
  --examples 2 --max-total-groups 100000
```

Rules must be a list or tuple of 1-100 mappings containing exactly `determinant`
and `dependent`, each a valid nonempty list or tuple of disjoint column names.
CLI JSON rules reject duplicate keys and strings above 262144 characters.
Single-rule CLI usage and report content are unchanged. Exit 0 means all rules
hold, 1 means a complete batch with at least one violation, 2 means no complete
batch or an output failure.

`max_groups` applies to each rule; `max_total_groups` caps the sum across all
rule indexes (default 100000), including duplicate rules. These are acceptance
caps, not hard memory bounds. Each rule retains its own distinct selected
values and up to `examples` counterexamples. Processing still does aggregation
work for every rule on every record. Sharing the input pass does not guarantee
faster execution, lower total RAM, or lower disk use than separate calls.
SQLite storage opens a separate private temporary database and connection per
rule; each has its own approximately 8 MiB page cache. Many rules can therefore
use more RAM, temporary files and open file descriptors. All databases are
closed before any of their temporary directories are removed, including when
a later index fails during setup. Directory cleanup itself can need file
descriptors, so closing every batch connection first avoids keeping earlier
connections open during cleanup after descriptor exhaustion. Cleanup failures
still reject the batch rather than return a report. Directories are removed on
normal completion and handled failures, not securely erased. Existing disk
sensitivity and crash caveats apply to every rule.

The minimum-removal count in each report is for that rule alone. Never sum
these counts to estimate a joint repair: the same removed row can resolve violations of several rules, so joint repair
can cost less than that sum. Deleting rows cannot introduce a new violation of
these dependencies. This is declared-rule checking, not dependency discovery,
data repair or an analysis recommendation.


### Output failures

The CLI returns exit2 for output write or flush failures, including a full disk
or a broken pipe. It also returns exit2 if its error diagnostic cannot be
written. The executable entrypoints close an already-failing standard stream
before Python shutdown so a second flush does not replace exit2 with exit120.
Calling `main()` from Python does not close caller-owned streams; callers own
any later flush/shutdown handling. No code can retract a report prefix already
accepted by a destination before that destination fails, so exit2 must not be
treated as a complete audit. No input, index or audit-count behavior changes.
