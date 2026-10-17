"""Command line: python -m viberarchive <command>  (or python archive.py <command>)."""
import argparse
import sys
from pathlib import Path

from . import check, pcimport, phoneimport, reconcile


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
    ph = sub.add_parser("import-phone-db", help="import the phone's viber_messages database (after the PC export)")
    ph.add_argument("phone_db", help="path to the phone's viber_messages file")
    ph.add_argument("--archive", default="archive/archive.db")
    ph.add_argument("--label", help="free text, for example the date the copy was taken")
    ph.add_argument("--self-number", action="append", default=[],
                    help="your own number; by default it is the one in every conversation")
    ph.add_argument("--exclude-peer", action="append", default=[], help="number of a 1:1 chat to leave out")
    ph.add_argument("--keep-copy-in", help="folder to keep a copy of the phone file in "
                                           "(default: 'sources' next to the archive; use '-' for none)")
    rec = sub.add_parser("reconcile", help="write the reconciliation report (Markdown plus CSV files)")
    rec.add_argument("--archive", default="archive/archive.db")
    rec.add_argument("--out", default="report",
                     help="folder for reconciliation.md, gaps.csv, days.csv and findings.csv")
    chk = sub.add_parser("check", help="sanity checks on the archive")
    chk.add_argument("--archive", default="archive/archive.db")
    chk.add_argument("--acceptance", action="store_true",
                     help="also compare snapshot #1 with the known numbers of the 29/09/2026 export")
    return parser


def _import_phone(args):
    keep = args.keep_copy_in or str(Path(args.archive).resolve().parent / "sources")
    result = phoneimport.import_phone_db(args.archive, args.phone_db, args.label, args.self_number,
                                         args.exclude_peer, None if keep == "-" else keep)
    if result["status"] == "already_imported":
        print(f"This exact phone file is already in the archive (snapshot #{result['snapshot_id']}). Nothing changed.")
        return 0
    print(f"Imported as snapshot #{result['snapshot_id']}:")
    for key, value in result.items():
        if key not in ("status", "snapshot_id", "copy"):
            print(f"   {key:<22} {value:>10,}")
    if result["copy"]:
        print(f"A copy of the phone file is kept at {result['copy']}")
    return 0


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
    if args.cmd == "reconcile":
        path = reconcile.write_report(args.archive, args.out)
        print(f"Report written to {path} (gaps.csv, days.csv and findings.csv are beside it).")
        return 0
    if args.cmd == "import-phone-db":
        return _import_phone(args)
    return 0 if check.report(args.archive, args.acceptance) else 1


if __name__ == "__main__":
    sys.exit(main())
