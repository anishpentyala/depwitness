"""Command-line interface; complete reports only."""

import argparse
import json
import sys

from .core import AuditError, Limits, audit


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit a declared CSV functional dependency")
    parser.add_argument("input")
    parser.add_argument("--determinant", action="append", required=True)
    parser.add_argument("--dependent", action="append", required=True)
    parser.add_argument("--examples", type=int, default=0)
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--storage", choices=("memory", "sqlite"), default="memory")
    parser.add_argument("--temp-dir")
    for name, default in vars(Limits()).items():
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=default)
    args = parser.parse_args(argv)
    try:
        report = audit(
            args.input,
            determinant=args.determinant,
            dependent=args.dependent,
            examples=args.examples,
            delimiter=args.delimiter,
            storage=args.storage,
            temp_dir=args.temp_dir,
            limits=Limits(**{name: getattr(args, name) for name in vars(Limits())}),
        )
        # Build the full serialization before emitting anything to stdout.
        output = json.dumps(report, ensure_ascii=True, sort_keys=True) + "\n"
        sys.stdout.write(output)
        sys.stdout.flush()
        return 0 if report["passed"] else 1
    except (AuditError, MemoryError) as exc:
        print(f"depwitness: {str(exc) or 'insufficient memory'}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
