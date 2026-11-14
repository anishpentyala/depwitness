# depwitness

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

This is a source-installable tool, not a claimed package-registry release.

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
is larger. Input bytes and decoded text are retained while reading. The index
retains every distinct determinant/dependent tuple and its frequency, not every
row or row pair. Memory grows with input bytes and distinct selected tuples and
their lengths. A small example cap does not cap index memory. No disk backend or
streaming-memory guarantee. No network code or telemetry.

For selected tuple width `W`, scanning and hash-table aggregation take expected
`O(bytes + records * W)` work, plus a final pass over distinct selected tuples.
Hashing is expected, not a worst-case bound. A dense group with 10,000 rows split
equally across two values represents 25,000,000 conflicting pairs without
materializing them. It still reads every accepted row before returning.

Exit **0**: complete report and declared dependency holds. Exit **1**: complete
report with violations. Exit **2**: invalid/incomplete input, invalid options,
resource or output failure. Invalid input never produces a partial success or
partial violation report. Output I/O failures cannot retract bytes already
written to a failing pipe or filesystem; they are not complete audit delivery.

## Library

```python
from depwitness import Limits, audit

report = audit(
    'catalog.csv',
    determinant=['sku', 'region'],
    dependent=['category'],
    examples=0,
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
