"""Command line: python -m viberarchive <command>  (or python archive.py <command>)."""
import argparse
import sys

from . import check, pcimport


def build_parser():
    parser = argparse.ArgumentParser(prog="viberarchive", description="Personal Viber chat archive")
    sub = parser.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import-pc", help="import an upstream viber_export.db into the archive")
    imp.add_argument("export_db", help="path to viber_export.db")
    imp.add_argument("--archive", default="archive/archive.db", help="archive database (created if missing)")
    imp.add_argument("--source", choices=["pc-old", "pc-new"], required=True,
                     help="which laptop the export came from")
    imp.add_argument("--label", help="free text, for example the export date")
    imp.add_argument("--self-number", action="append", default=[],
                     help="your own number; by default it is found as the member of every chat")
    imp.add_argument("--exclude-peer", action="append", default=[],
                     help="number of a 1:1 chat to leave out (repeatable)")
    chk = sub.add_parser("check", help="sanity checks on the archive")
    chk.add_argument("--archive", default="archive/archive.db")
    chk.add_argument("--acceptance", action="store_true",
                     help="also compare snapshot #1 with the known numbers of the 29/09/2026 export")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if args.cmd == "import-pc":
        result = pcimport.import_pc(args.archive, args.export_db, args.source, args.label,
                                    args.self_number, args.exclude_peer)
        if result["status"] == "already_imported":
            print(f"This exact export is already in the archive (snapshot #{result['snapshot_id']}). Nothing changed.")
            return 0
        print(f"Imported as snapshot #{result['snapshot_id']}:")
        for key, value in result.items():
            if key not in ("status", "snapshot_id"):
                print(f"   {key:<22} {value:>10,}")
        if not result["self_found"]:
            print("WARNING: could not tell which contact is you; pass --self-number.")
        return 0
    return 0 if check.report(args.archive, args.acceptance) else 1


if __name__ == "__main__":
    sys.exit(main())
