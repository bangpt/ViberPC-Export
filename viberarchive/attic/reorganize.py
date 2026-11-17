"""Move the Viber folders into one tidy data root. Dry run by default: nothing changes until you add --apply.

Run from d:\\Projects\\Viber\\ViberPC-Export (close the viewer server and anything using archive.db first):
    python reorganize.py             shows the plan
    python reorganize.py --apply     does it

Everything is a rename on the same drive, so it is instant, copies nothing, and loses nothing. Files that are
duplicates are moved into _retire (not deleted); you delete _retire yourself once the first backup is verified.
Options: --root D:\\ViberArchive  --viber d:\\Projects\\Viber  --recovery D:\\ViberRecovery
"""
import argparse
import os
import sys
from pathlib import Path


def plan(root, viber, recovery):
    """(source, destination, why) for every move."""
    root, viber, recovery = Path(root), Path(viber), Path(recovery)
    repo = viber / "ViberPC-Export"
    s = root / "sources"
    return [
        (viber / "ViberPCExport", s / "pc-old" / "2026-09-29", "old laptop export: database, index, media (as a whole)"),
        (recovery / "DatabaseCopy", s / "phone-db" / "2026-10-14", "phone databases (viber_messages and viber_data)"),
        (recovery / "files" / "files", s / "phone-app-files", "the phone app's files: stickers, emoticons, media"),
        (viber / "inbox" / "phone_media", s / "phone-media", "media pulled from the phone, with manifest.csv"),
        (viber / "ViberPhone" / "Viber messages", s / "phone-csv", "Viber's own CSV exports of the chats"),
        (viber / "AppBackup", s / "misc" / "AppBackup", "unidentified app backup, kept as it is"),
        (viber / "AppBackup.zip", s / "misc" / "AppBackup.zip", "unidentified, kept as it is"),
        (repo / "archive" / "archive.db", root / "archive" / "archive.db", "the merged archive"),
        (repo / "archive" / "archive.db-wal", root / "archive" / "archive.db-wal", "(only if present)"),
        (repo / "archive" / "archive.db-shm", root / "archive" / "archive.db-shm", "(only if present)"),
        (repo / "site", root / "derived" / "site", "viewer, rebuilt by the html command"),
        (repo / "report", root / "derived" / "report", "reconciliation report, rebuilt by reconcile"),
        (viber / "ViberPhone" / "com.viber.voip", root / "_retire" / "ViberPhone-com.viber.voip",
         "duplicate of the phone app files (only logs and thumbnails differ)"),
        (viber / "ViberPhone" / "ViberPictures", root / "_retire" / "ViberPhone-ViberPictures",
         "duplicate of phone-media"),
        (viber / "ViberPhone" / "ViberMovies", root / "_retire" / "ViberPhone-ViberMovies", "duplicate of phone-media"),
        (repo / "archive" / "sources", root / "_retire" / "archive-sources",
         "second copy of the phone database (identical to phone-db)"),
    ]


def check(moves):
    """Problems that stop the run (list of strings) and notes."""
    problems, notes = [], []
    for src, dst, _ in moves:
        if not src.exists():
            notes.append(f"skipped, not found: {src}")
        elif dst.exists():
            problems.append(f"already exists: {dst}")
        elif os.path.splitdrive(str(src))[0].lower() != os.path.splitdrive(str(dst))[0].lower():
            problems.append(f"different drive, would copy instead of rename: {src} -> {dst}")
    return problems, notes


def apply(moves):
    done = 0
    for src, dst, why in moves:
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        done += 1
        print(f"moved  {src}\n    -> {dst}")
    for folder in ("config", "derived"):
        (Path(moves[0][1]).parents[2] / folder).mkdir(parents=True, exist_ok=True)
    return done


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=r"D:\ViberArchive")
    parser.add_argument("--viber", default=r"d:\Projects\Viber")
    parser.add_argument("--recovery", default=r"D:\ViberRecovery")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    moves = plan(args.root, args.viber, args.recovery)
    problems, notes = check(moves)
    for src, dst, why in moves:
        mark = "  " if src.exists() else "--"
        print(f"{mark} {src}\n      -> {dst}    [{why}]")
    for note in notes:
        print("note:", note)
    if problems:
        print("\nSTOPPED, fix these first:")
        for problem in problems:
            print("  ", problem)
        return 1
    if not args.apply:
        print("\nDry run only. Add --apply to do it.")
        return 0
    count = apply(moves)
    print(f"\nDone: {count} moves. Next: rebuild the links and the site (see the message).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
