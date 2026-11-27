"""Command line entry point.

    routing run FILE [--dry-run] [--phase routing] [--only create] [--rows 5-12] [--slow]
    routing check routing-condition FILE [-o OUT]
    routing opc add-tpm [-i FILE] [-o OUT]
    routing list

FILE is optional: when missing you are asked for it (drag & drop works).
Exit code 0 = success, 1 = error (for UiPath).
"""
import argparse
import importlib
import sys
import traceback

from routing.core.excel import ask_path, clean_path, with_suffix
from routing.model.enums import PHASES, Action

# command -> (module, function, accepts sheet_name)
CHECKS = {
    "routing-condition": ("routing.checks.routing_condition", "run", False),
    "alt-bom": ("routing.checks.alt_bom", "run", False),
    "delete-status": ("routing.checks.delete_status", "run", False),
    "operation-values": ("routing.checks.operation_values", "run", True),
    # old command names, kept so existing scripts / UiPath calls keep working
    "operation-capacity": ("routing.checks.operation_values", "run", True),
    "util-eff": ("routing.checks.operation_values", "run", True),
    "routings-by-tool": ("routing.checks.routings_by_tool", "run", False),
    "tpm-exist": ("routing.checks.tpm_exist", "run", True),
    "pv-count": ("routing.checks.production_version", "run_count", True),
    "pv-by-group": ("routing.checks.production_version", "run_by_group", True),
    "pv-by-attributes": ("routing.checks.production_version", "run_by_attributes", True),
    "pv-fallback": ("routing.checks.production_version", "run_with_fallback", True),
    "pv-exist": ("routing.checks.pv_exist", "run", True),
}

OPC = {
    "add-tpm": "routing.opc.add_tpm",
    "add-workflow": "routing.opc.add_workflow",
    "compare-workflow": "routing.opc.compare_workflow",
    "delete-tpm": "routing.opc.delete_tpm",
    "update-tpm-priority": "routing.opc.update_tpm_priority",
}

# run() functions without an output_path argument
NO_OUTPUT = set()


def _load(module, function):
    return getattr(importlib.import_module(module), function)


def parse_rows(text):
    """'5-12' / '5,7,9' / '5-7,10' -> {5, 6, 7, 10}; None for all rows."""
    if not text:
        return None
    rows = set()
    for part in str(text).split(","):
        start, _, end = part.strip().partition("-")
        rows.update(range(int(start), int(end or start) + 1))
    return rows


def run_check(name, file=None, output=None, sheet=None):
    module, function, has_sheet = CHECKS[name]
    kwargs = {}
    if output and name not in NO_OUTPUT:
        kwargs["output_path"] = output
    if sheet is not None and has_sheet:
        kwargs["sheet_name"] = sheet
    return _load(module, function)(file or ask_path(), **kwargs)


def run_opc(name, file=None, output=None):
    """Default output: next to the input, '<input>_<command>_result.xlsx'."""
    module = importlib.import_module(OPC[name])
    file = clean_path(file or ask_path())
    output = clean_path(output) if output else with_suffix(file, f"_{name.replace('-', '_')}_result")
    return module.main(input_file=file, output_file=output)


def build_parser():
    parser = argparse.ArgumentParser(prog="routing", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="plan + run routing requests in SAP (Action column: Add / Delete / Assign Components)")
    run.add_argument("file", nargs="?")
    run.add_argument("--phase", action="append", choices=PHASES,
                     help="only these phases (repeatable); default: all, always in phase order")
    run.add_argument("--only", choices=[a.value.lower() for a in Action], help="only rows with this Action")
    run.add_argument("--rows", help="only these Excel rows, e.g. 5-12 or 5,7,9")
    run.add_argument("--dry-run", action="store_true", help="plan only (Plan sheet), SAP is not touched")
    run.add_argument("--slow", action="store_true", help="wait after every SAP action (watch / debug)")
    run.add_argument("--sheet", help="request sheet (default: first sheet)")

    check = sub.add_parser("check", help="run one Snowflake / OpCenter check")
    check.add_argument("name", choices=sorted(CHECKS))
    check.add_argument("file", nargs="?")
    check.add_argument("-o", "--output")
    check.add_argument("--sheet", help="sheet name (checks that read one sheet)")

    opc = sub.add_parser("opc", help="generate an OpCenter upload file")
    opc.add_argument("name", choices=sorted(OPC))
    opc.add_argument("-i", "--input", help="input Excel (asked for when missing)")
    opc.add_argument("-o", "--output", help="output Excel (default: <input>_<name>_result.xlsx next to the input)")

    sub.add_parser("list", help="show all commands")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            from routing.pipelines.run import run
            run(args.file or ask_path(), phases=tuple(args.phase or PHASES),
                only=Action.parse(args.only) if args.only else None, rows=parse_rows(args.rows),
                dry_run=args.dry_run, slow=args.slow, sheet=args.sheet)
        elif args.command == "check":
            run_check(args.name, args.file, args.output, args.sheet)
        elif args.command == "opc":
            run_opc(args.name, args.input, args.output)
        elif args.command == "list":
            print("run\n" + "\n".join(f"check {n}" for n in sorted(CHECKS))
                  + "\n" + "\n".join(f"opc {n}" for n in sorted(OPC)))
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
