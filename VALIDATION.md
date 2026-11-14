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
