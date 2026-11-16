"""Command-line interface; complete reports only."""

import argparse
import json
import sys

from .core import AuditError, Limits, audit, audit_many


def _parse_rule(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise AuditError("duplicate JSON rule key")
            result[key] = item
        return result

    if len(value) > 262144:
        raise AuditError("JSON rule exceeds 262144 characters")
    try:
        return json.loads(value, object_pairs_hook=unique)
    except (ValueError, RecursionError) as exc:
        raise AuditError("invalid JSON rule: " + str(exc)) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit a declared CSV functional dependency")
    parser.add_argument("input")
    parser.add_argument("--determinant", action="append")
    parser.add_argument("--dependent", action="append")
    parser.add_argument("--rule", action="append", help="JSON rule; repeat for a single-pass batch")
    parser.add_argument("--max-total-groups", type=int)
    parser.add_argument("--examples", type=int, default=0)
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--storage", choices=("memory", "sqlite"), default="memory")
    parser.add_argument("--temp-dir")
    for name, default in vars(Limits()).items():
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=default)
    args = parser.parse_args(argv)
    try:
        common = {
            "examples": args.examples,
            "delimiter": args.delimiter,
            "storage": args.storage,
            "temp_dir": args.temp_dir,
            "limits": Limits(**{name: getattr(args, name) for name in vars(Limits())}),
        }
        if args.rule is not None:
            if args.determinant is not None or args.dependent is not None:
                raise AuditError("--rule cannot be combined with --determinant or --dependent")
            rules = [_parse_rule(value) for value in args.rule]
            report = audit_many(
                args.input,
                rules=rules,
                max_total_groups=100000 if args.max_total_groups is None else args.max_total_groups,
                **common,
            )
        else:
            if args.max_total_groups is not None:
                raise AuditError("--max-total-groups requires --rule")
            report = audit(
                args.input, determinant=args.determinant, dependent=args.dependent, **common
            )
        # Build the full serialization before emitting anything to stdout.
        output = json.dumps(report, ensure_ascii=True, sort_keys=True) + "\n"
        sys.stdout.write(output)
        sys.stdout.flush()
        return 0 if report["passed"] else 1
    except (AuditError, MemoryError) as exc:
        try:
            print(f"depwitness: {str(exc) or 'insufficient memory'}", file=sys.stderr, flush=True)
        except OSError:
            # The diagnostic destination can fail too; failure is still exit2.
            pass
        return 2
    except OSError:
        return 2


def cli():
    """Process entrypoint: prevent a second failed flush overriding exit2.

    Keep stream ownership unchanged for callers of main(). Only the executable
    entrypoint closes an already-failing standard stream before shutdown.
    """
    try:
        code = main()
    except SystemExit as exc:
        # argparse uses SystemExit for help and invalid arguments. Its buffered
        # output still needs the same checked flush as an audit report.
        code = exc.code
    except OSError:
        # argparse may itself fail while writing help or a diagnostic.
        code = 2
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except OSError:
            code = 2
            try:
                stream.close()
            except OSError:
                pass
    return code


if __name__ == "__main__":
    raise SystemExit(cli())
