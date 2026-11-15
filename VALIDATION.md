# Local validation

2026-11-14 private candidate. These are local Linux results, not hosted CI,
Windows/macOS, acceptance, release or adoption claims.

- 35 unittest methods on actual CPython 3.9.25, 3.10.12, 3.11.17, 3.13.17,
  3.14.9 and 3.15.1. Counts include methods with subtests, not a claim of only
  35 individual assertions. The suite includes 200 seeded small inputs checked
  against literal row pairs and exhaustive deletion subsets, plus a 10,000-row
  two-version group with exactly 25,000,000 conflicting pairs.
- A separate seed991917 reference compared 4,000 complete reports: 1,000
  composite determinant/dependent CSVs at example caps 0/1/2/1000. The oracle
  enumerates literal row pairs, consistent-value classes and first-conflict
  witness events. It covers empty and exact Unicode/string values, quoting and
  multiline fields. This is not an exhaustive proof over arbitrary files.
- Intact suite passes. A deliberately wrong expected pass/fail assertion causes
  one assertion failure. Eight production mutations are caught by assertion
  failures, without test errors: pair multiplicity85, affected rows110,
  minimum removals40, collapsed keys158, dropped RHS coordinate2,
  normalized keys2, record ordinal103, repeats-as-violations54. Counts include
  failing subtests. Restoring production and test files restores all35 methods.
  An initial dropped-coordinate mutant also caused a test IndexError while
  indexing an absent witness. The test now first asserts the witness length;
  the final run above fails with two assertions and zero errors. The original
  IndexError is not counted as correctness evidence.
- Source coverage in this test run: core.py100% statements and branches;
  combined package99%, with only the __main__ direct-module launch guard not
  reached inside the in-process suite. Coverage is not a correctness proof.
- Ruff0.17.5 check and format checks on src and tests. No claim all Markdown
  snippets were separately linted.
- Wheel and sdist build. Fresh installed wheel, outside the source directory,
  passes all35 methods on Python3.9 and3.14. Archive source/example-byte checks
  and extracted-sdist tests are part of the accompanying private review proof.

## Controls and boundaries

Header-only input is explicitly a vacuous pass with zero records. Exact repeats
are consistent mappings; duplicate determinants with different RHS tuples are
not. The minimum-removal oracle exhausts deletion subsets for inputs up to eight
rows, independent of the aggregation formula. Composite-RHS tests prevent using
independent coordinate modes instead of complete tuples. Invalid input is tested
after an already-detected conflict to ensure no partial JSON report escapes.

Parser limits, malformed/decoding/NUL errors, unselected-field validation,
source receipts, privacy defaults, witness cap/count consistency, CLI exits,
memory-error handling and broken output pipes are covered. A broken output sink
may already have received some bytes; exit2 cannot retract them. Input caps are
not hard RAM/runtime bounds, and Python's parser has its own field-size limit.

The project does not infer that a business rule is correct, find candidate
keys, discover dependencies, prove real-world data correctness, choose repairs,
enforce database constraints, or produce a multi-rule minimum-deletion plan.
No benchmark superiority, novelty, external acceptance or adoption is claimed.

## 0.1.2 incremental input decoding and receipt

Local Linux checks on 2026-11-14. No hosted-CI/registry/adoption claim.

The source is read once in bounded decoder buffers instead of keeping full raw
and decoded file copies. The receipt hashes raw consumed bytes, including BOM
and original line endings. Accepted inputs still reach EOF before a report is
returned. NUL, byte-limit, UTF-8, CSV and source-read failures fail the audit,
including failures after a witness cap is filled. The exact FD index remains in
memory and can still grow with all distinct selected tuples. CSV can buffer a
large record, so this is not a hard RAM, constant-memory or runtime guarantee.
Validation now runs during reading; an input with multiple faults can produce a
different first error diagnostic. There is no report-schema/policy change.

- Original 39 methods are byte-unchanged; five new methods give 44 tests passing
  on actual local CPython 3.9/3.10/3.11/3.13/3.14/3.15. Coverage includes one
  open/read-once receipts, reads at most 8,192 bytes, UTF-8 code points and quoted
  CRLF deliberately split at raw byte 8,192, BOM, multibyte delimiter, exact and
  exceeded byte caps, invalid late tails with default/filled evidence caps, and
  late source-read errors with stream closure.
- Against the actual 0.1.1 source, the same 44 methods fail with two assertions
  and zero errors: the oversized source read violates the new recording-stream
  assertion, and a source that fails on its second read never gets that second
  read. The other 42 methods pass. The latter is an incremental-reader control,
  not a claim the original source returned a partial regular-file audit.
- 1,500 generated CSVs x four example caps x three composite-column policies
  give 18,000 complete-report equalities against 0.1.1 (seed 716990). Seven malformed
  complete sources are rejected by both implementations. Includes CR/LF/CRLF,
  multibyte delimiters, UTF-8 BOM, quoted multiline values and literal empty/NA/
  NULL/exact strings. This is finite testing, not exhaustive proof.
- On actual CPython 3.14.9, six production mutations fail the targeted controls
  by assertion, with zero test errors: unbounded read, missing digest update, exclusive byte cap, missing
  NUL check, premature EOF after a buffer, and wrong byte count. Focused failure
  counts are 1/1/1/2/1/1. Intact/restored focused suite passes five methods.
  This is not an all-interpreter mutation claim: on Python 3.10, the missing-NUL
  mutant survives because the CSV parser itself rejects NUL; the other five
  mutations fail assertions with zero errors in independent review.
  Earlier broad mutation runs also raised deliberate validation/buffer errors;
  those error totals are not used as assertion-only correctness evidence.
- Ruff 0.17.5 check/format passes for src/tests (six formatted files). Wheel and
  sdist build; neutral installed-wheel tests on actual Python 3.9 and 3.14 each
  pass 44 methods. Packaged Python module bytes match the candidate source.

Local performance measurements: Python 3.14.9, three fresh processes per source
and input, medians below. Full audit wall time and process high-water RSS include
imports/index, not only reader allocations. Source files exist before launch.

| Input | 0.1.1 seconds | 0.1.2 seconds | 0.1.1 peak RSS KiB | 0.1.2 peak RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| 14,000 consistent rows, 900-char ignored payload | 0.089353 | 0.064366 | 92,324 | 17,680 |
| 40,000 distinct determinants, no payload | 0.056033 | 0.056836 | 34,744 | 31,716 |
| 50 consistent rows, no payload | 0.000376 | 0.000378 | 17,764 | 17,580 |

The narrow-distinct case is slightly slower locally and still retains its full
selected-tuple index. These results do not promise lower RSS or faster execution
for every input or platform. No disk backend, atomic file snapshot, provenance
authentication, secure memory erasure or constant-memory claim is added.

### Review correction

Runtime `depwitness.__version__` now matches distribution version 0.1.2, with an
added regression assertion. The final suite is 45 methods (39 original methods
unchanged plus six new methods), including the version assertion. Local final
runs and neutral installed-wheel checks below supersede the 44-method snapshot
above. Baseline negative-control and reader mutation evidence above concern the
five reader methods, not the newly added version assertion.

## 0.2.0: opt-in SQLite selected-tuple index

Private candidate validation, November 14, 2026. Baseline is public main
2faf9589a13a0c60d1fd1adbf5c2993333c52d1a (0.1.2). This adds `storage="sqlite"`
and optional existing `temp_dir` to `audit`, plus matching CLI switches. Memory
remains the default. JSON schema/settings, exact-string comparison, validation,
counts, evidence order and input receipt are unchanged. No input snapshot,
secure-erasure, hard memory bound or speed improvement is claimed.

- 68 methods: 45 existing methods retained (the expected runtime version changes
  to 0.2.0), plus 23 storage methods. All pass on actual CPython 3.9.25 / SQLite
  3.50.4, 3.10.12 / 3.37.2, 3.11.17 / 3.53.1, 3.13.17 / 3.53.1, 3.14.9 /
  3.53.1 and 3.15.1 / 3.53.1. These are Linux x86-64 local runs, not claims
  about other operating systems or upstream CI.
- New coverage includes full-report and byte-identical CLI JSON parity, 300
  generated complete-report comparisons (seed 619204), one large conflicting
  group, exact counts above 2**100, no ignored-value storage, POSIX permissions,
  empty/header-only input, limit/late malformed/NUL/decode rejection, optional
  SQLite unavailability, failed connect/write/fetch/iteration/close/cleanup,
  explicit cursor close and explicit cleanup before return. Invalid or failed
  storage never returns a complete report. Forced termination is not tested as
  a cleanup guarantee and can leave files behind.
- A separate 600-input generated probe (seed 527910) compares each candidate
  backend to the actual baseline implementation: 1,200 complete-report equalities.
  Includes composite tuples, exact empty/NULL/NA strings, Unicode, BOM, delimiters,
  line endings, quoted records and example caps. This is finite testing, not
  exhaustive equivalence. The baseline does not implement the new storage API;
  unsupported-keyword errors are not used as correctness evidence.
- Five deliberate production mutations each fail a focused test by one inspected
  assertion with zero test errors on Python 3.14.9: zero frequency reads, missing
  per-row group persistence, lost prior frequencies at promotion, omitted explicit
  cleanup, and doubled group count. The cleanup mutant also emits the expected
  ResourceWarning from implicit cleanup; that warning is not counted as a test
  failure. Restored 68-method suite passes.
- Ruff 0.17.5 check/format, wheel/sdist build, packaged Python module byte
  comparison, and neutral installed-wheel 68-method tests on Python 3.9 and 3.14
  pass. No registry upload or external adoption is claimed.

### Measured trade-off

Actual Python 3.14.9, three fresh processes for each input/backend, medians.
Wall time is audit-only; peak RSS includes imports and audit. Inputs exist before
launch. Wider limits are explicit in the benchmark, not new defaults. Complete
counts/receipt are compared in every run. Selected values below have 80-character
padding where stated. RSS is the Linux process high-water mark, not an allocation
bound and not isolated index-only memory.

| Input | Memory seconds | SQLite seconds | Memory RSS KiB | SQLite RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| 120,000 distinct padded determinant/dependent tuples | 0.280829 | 3.289987 | 81,804 | 31,684 |
| 60,000 distinct padded dependent tuples in one group | 0.109664 | 1.472797 | 33,952 | 30,960 |
| 120,000 rows in ten repeated groups | 0.120156 | 1.638856 | 19,868 | 20,472 |

SQLite was slower in all three shapes and used more RSS for the small-index
shape. Its 8 MiB page-cache setting is not a process memory limit. Disk usage,
filesystem cache and crash recovery are not characterized by this measurement.
The benchmark and detailed local proof are retained with the review packet.

## Single-pass rule batches, 2026-11-15 private preparation

This extends the library/CLI to multiple declared rules. No hosted CI, public
release, user adoption or performance claim is made for this private candidate.

- 85 unittest methods (68 existing plus 17 batch methods) pass on actual Linux
  CPython 3.9.25, 3.10.12, 3.11.17, 3.13.17 and 3.14.9. Existing single-rule
  report, input-validation, compact-index and SQLite-cleanup tests still pass.
- Batch tests cover exact ordered per-rule reports, generated parity, one input
  open with full-byte receipt, late malformed/UTF-8/NUL input, invalid later
  policies, shared and per-rule caps, later storage-setup cleanup, last-summary
  failure with no CLI JSON, duplicate rules, header-only inputs and CLI exits.
  The generated suite uses 100 fixtures, three rules and both storage backends.
- A separate process importing the actual unchanged released source at
  bcbf1356d871009d028a69dd29fb2bc5d60ae697 generated expected reports from
  repeated single-rule calls. All 960 complete reports matched the batch output
  exactly (160 seeded fixtures, three rules, both storage backends). This
  checks preservation of existing behavior, not independent scientific truth.
- Four deliberate production mutations cause assertion failures with no setup
  or collection errors: skipping the last rule, accepting any passing rule
  instead of all, disabling the total-group cap, and rereading the input once
  per rule. Restoring the code restores all 85 passing methods. A mutant can
  trigger several failing subtests; these are four mechanisms, not extra work
  or contributions.
- Ruff 0.17.5 check/format and wheel/sdist build pass. Neutral installed-wheel
  runs outside the checkout pass all 85 methods on Python 3.9.25 and 3.14.9;
  all four runtime Python files match source/wheel/installed bytes exactly.

One shared CSV scan still performs separate per-rule aggregation. No speed/RAM
benchmark or guarantee is claimed. SQLite creates one private database and
connection per rule, with separate caches. The new total-group acceptance cap
limits the sum across indexes; it is not a hard process-memory bound. Counts of
minimum removals stay per-rule and cannot be summed into a joint repair claim.

## Batch cleanup after descriptor exhaustion (0.3.1)

A Linux/Python 3.10 subprocess with POSIX `RLIMIT_NOFILE=64`, 100 repeated
supported rules and a three-record CSV reproduced a handled SQLite setup failure
in 0.3.0. One private temporary directory with a zero-byte `dependency.sqlite3`
remained after the call. No retained CSV values or partial successful report
were observed. The failed setup's recursive directory cleanup needed a file
descriptor while earlier rule connections were still open.

Batch cleanup now closes every connection before attempting any directory
removal, including directories from a later index whose setup failed. The same
64-descriptor case still fails the audit, but leaves no temporary index and the
CLI exits 2 without JSON. It does not increase the descriptor limit or make
100-rule SQLite batches succeed under that limit. A 128-descriptor run also
failed cleanly; 256 and 512 completed with unchanged reports. These observations
are local, not portable descriptor thresholds or performance claims.

The 90-test suite passed on Linux/Python 3.9, 3.10, 3.11, 3.13, 3.14 and 3.15.
Five new tests cover connection/cleanup ordering on success and failed setup,
close failure, cleanup failure and real isolated POSIX descriptor exhaustion for
both API and CLI. The real limit test skips non-POSIX systems and unusually low
hard limits. Deterministic ordering/failure tests run without that OS condition.
Against unchanged 0.3.0, the new tests have three assertion failures and no setup
errors. Restoring immediate batch cleanup or omitting explicit deferred cleanup
each also produces three assertion failures, with no setup errors.

Across 160 seeded CSV fixtures and both storage backends, 320 full batch rule
lists (960 individual reports) remained byte-identical to 0.3.0. Source/wheel
runtime bytes matched both neutral Python 3.9 and 3.14 installs, and all 90 tests
passed from each installed wheel outside the checkout. No Windows or macOS
resource-exhaustion result is claimed. Disk privacy, crash, cleanup-error and
non-secure-erasure limits still apply.
