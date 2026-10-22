"""Command line: python -m viberarchive <command>  (or python archive.py <command>)."""
import argparse
import sys
from pathlib import Path

from . import check, htmlview, media, pcimport, phoneimport, reconcile, serve


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
    lm = sub.add_parser("link-media", help="link photos and videos to messages (needed before 'html' shows them)")
    lm.add_argument("--archive", default="archive/archive.db")
    lm.add_argument("--pc-index", help="media_index.csv written by the upstream media export")
    lm.add_argument("--phone-manifest", help="manifest.csv of the media copied from the phone")
    lm.add_argument("--stickers", help="Viber .stickers folder (pack folders with r144_<id>_orig.png files)")
    web = sub.add_parser("html", help="write the static HTML viewer (one page per chat and month)")
    web.add_argument("--archive", default="archive/archive.db")
    web.add_argument("--out", default="site")
    web.add_argument("--media", choices=["link", "copy"], default="link",
                     help="link: point at the media where it is; copy: put a copy of each photo in the site folder")
    web.add_argument("--emoticons", help="folder of PNGs named smiley.png, teeth.png ... for emoticon-only messages")
    web.add_argument("--seen-icon", help="picture used for a seen message instead of the double tick "
                                         "(not needed if the emoticons folder has a file with 'seen' in its name)")
    web.add_argument("--chat-names", help="JSON file {\"direct:849...\": \"Her name\", \"notes\": \"My Notes\"} "
                                          "to override chat names (names also come from the contacts)")
    web.add_argument("--config", help="folder with names.json, seen.png and the icons8 icons "
                                      "(default: the 'config' folder next to the archive folder, when it exists)")
    web.add_argument("--bubble-time", choices=["composed", "sent"], default="composed",
                     help="time shown in each bubble: composed (as the desktop app) or sent (as the phone)")
    srv = sub.add_parser("serve", help="serve the site on your network so a phone can open it")
    srv.add_argument("--site", default="site", help="the folder written by 'html' (default site)")
    srv.add_argument("--port", type=int, default=8000)
    srv.add_argument("--local-only", action="store_true", help="only this computer, not the network")
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
    if args.cmd == "link-media":
        result = media.link_media(args.archive, args.pc_index, args.phone_manifest, args.stickers)
        for key, value in result.items():
            print(f"   {key:<22} {value:>10,}")
        return 0
    if args.cmd == "html":
        result = htmlview.build(args.archive, args.out, args.bubble_time, args.media, args.emoticons,
                                args.seen_icon, args.chat_names, args.config)
        print(f"Wrote {result['pages']:,} month pages for {result['chats']} chats ({result['messages']:,} messages) "
              f"to {args.out}. Open {Path(args.out) / 'index.html'} in a browser.")
        print(f"Emoticon pictures: {result['emoticons']}; "
              f"seen icon: {result['seen_icon'] or 'NOT FOUND (double tick used)'}")
        print(f"Icons: {result['icons']} of 7 found (others use a character); "
              f"chat names file: {result['names_file'] or 'none'}")
        return 0
    if args.cmd == "serve":
        serve.serve(args.site, args.port, args.local_only)
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
