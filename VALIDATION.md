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
