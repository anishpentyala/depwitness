# Scope and source notes

Read 2026-11-14. These sources establish prior art and semantics, not a performance
comparison, endorsement, implemented feature in another project, or copied code.
No third-party implementation was copied into this project.

All claims used below checked in fetched pages, not highlights. No external code copied.
1. Desbordante CLI, official repository documentation, https://github.com/Desbordante/desbordante-cli . Exact FD discovery and validation already supported, validation can explain conflicting rows. High confidence prior art. License noted AGPL: no implementation copying or dependency.
2. Microsoft Learn SemPy FD tutorial, official product guide, https://learn.microsoft.com/en-us/fabric/data-science/tutorial-data-cleaning-functional-dependencies . find_dependencies/list_dependency_violations; warns only use statistical row dropping when confident it suits data. High confidence workflow motivation, not a source of universal ZIP->city rule.
3. dbt-utils feature issue989, community request, https://github.com/dbt-labs/dbt-utils/issues/989 . Requests determinant->dependent check, distinguishes unique-combination test. Request is demand evidence only, not implemented capability, author identity or endorsement.
4. FDTool paper, research publication via PMC, https://pmc.ncbi.nlm.nih.gov/articles/PMC6489977/ . Discovery of minimal FDs, equivalent attributes and candidate keys. Established prior art, not a benchmark against our code.
5. PostgreSQL18 constraints documentation, primary technical documentation, https://www.postgresql.org/docs/current/ddl-constraints.html . Unique constraint ensures unique column combination; NULLS DISTINCT vs NOT DISTINCT differ. Supports explicit separation from FD and no implicit SQL-null claim.
6. Python csv documentation, primary technical documentation, https://docs.python.org/3/library/csv.html . newline='' for quoted newline handling, strict=True raises csv.Error on parser bad input, format differences exist. Does not prove all malformed dialects rejected or universal RFC conformity.


## Decisions from that evidence

- Exact supplied-rule validation, not discovery, is a deliberate limited scope.
- Repeated identical mappings can satisfy an FD while violating uniqueness.
- Literal CSV strings, including empties, avoid implicit SQL-null/loader claims.
- A declared rule can be wrong. Minimum removals are a count for that single
  rule, not recommendations, record correctness, or multi-rule repairs.
- Python CSV strict mode is a parser contract, not universal CSV validation.
- Counterexamples use data-record ordinals, not physical line numbers.

## Privacy and integrity boundaries

Full raw-byte SHA-256 receipt, byte count, selected field names, settings and
aggregate counts are returned. No raw input cell values by default. Hashes are
not anonymization and counts can disclose information. Examples opt in to raw
selected cells and record ordinals, never unselected cells. No input writes,
network or telemetry. Input caps are not hard memory or runtime guarantees.
The receipt identifies the bytes read, not an atomic filesystem snapshot.
