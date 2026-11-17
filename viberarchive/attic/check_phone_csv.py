#!/usr/bin/env python3
"""Read-only check of Viber 'Email message history' CSV files.

    python check_phone_csv.py "D:\\...\\Viber messages"
    python check_phone_csv.py "D:\\...\\Viber messages" --pc .\\ViberPCExport\\viber_export.db

Prints counts and dates only, never message text. File names are printed, so
blur contact names before you paste the output anywhere.

With --pc it also prints, per year, how many content messages the PC export
holds next to how many records the phone files hold. PC counts leave out edit
events, so they are approximate (within a few hundred of the archive's own count).
"""
import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

START = re.compile(r"^(\d{2})/(\d{2})/(\d{4}),(\d{1,2}):(\d{2}):(\d{2}) ([AP]M),")
PLACEHOLDERS = {"Photo message", "Video message", "Sticker"}


def scan(path):
    stats = {"records": 0, "continuation": 0, "before_first": 0, "placeholders": 0,
             "bad_date": 0, "years": Counter(), "months": Counter(), "days": Counter(), "first": None, "last": None, "bom": False}
    with open(path, "rb") as fh:
        stats["bom"] = fh.read(3) == b"\xef\xbb\xbf"
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            m = START.match(line)
            if not m:
                if stats["records"]:
                    stats["continuation"] += 1
                elif line.strip(","):
                    stats["before_first"] += 1
                continue
            dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (1 <= mm <= 12 and 1 <= dd <= 31):
                stats["bad_date"] += 1
                continue
            stats["records"] += 1
            stats["years"][yyyy] += 1
            stats["months"][f"{yyyy}-{mm:02d}"] += 1
            stats["days"][f"{yyyy}-{mm:02d}-{dd:02d}"] += 1
            key = (yyyy, mm, dd)
            stats["first"] = key if stats["first"] is None else min(stats["first"], key)
            stats["last"] = key if stats["last"] is None else max(stats["last"], key)
            fields = line.split(",", 4)
            body = fields[4].rstrip(",").strip('"') if len(fields) > 4 else ""
            if body in PLACEHOLDERS:
                stats["placeholders"] += 1
    return stats


def fmt(key):
    return f"{key[2]:02d}/{key[1]:02d}/{key[0]}" if key else "-"


def pc_months(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT strftime('%Y-%m', e.TimeStamp/1000, 'unixepoch', '+7 hours'), count(*) "
        "FROM Events e JOIN Messages m ON m.EventID=e.EventID "
        "WHERE e.Type=0 AND (m.Info IS NULL OR m.Info NOT LIKE '%\"edit\"%') "
        "GROUP BY 1").fetchall()
    con.close()
    return Counter({k: n for k, n in rows})


def phone_day(files, day):
    """Records of one day as (HH:MM:SS, direction, kind, body length). No text is returned."""
    want = day.split("/")
    out = []
    for path in files:
        last = None
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for raw in fh:
                line = raw.rstrip("\r\n")
                m = START.match(line)
                if not m:
                    if last is not None:
                        last[3] += len(line.strip(",").strip('"'))
                    continue
                last = None
                if [m.group(1), m.group(2), m.group(3)] != want:
                    continue
                h = int(m.group(4)) % 12 + (12 if m.group(7) == "PM" else 0)
                fields = line.split(",", 4)
                body = fields[4].rstrip(",").strip('"') if len(fields) > 4 else ""
                kind = ("placeholder" if body in PLACEHOLDERS else "link" if "http" in body
                        else "empty" if not body else "text")
                who = "out" if len(fields) > 2 and fields[2].strip('"') == "Me" else "in"
                code = body if re.fullmatch(r"\([a-z_0-9]+\)", body) else ""
                last = [f"{h:02d}:{m.group(5)}:{m.group(6)}", who, kind, len(body), code]
                out.append(last)
    return sorted(out)


def pc_day(db, day):
    dd, mm, yyyy = day.split("/")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT strftime('%H:%M:%S', e.TimeStamp/1000, 'unixepoch', '+7 hours'), e.Direction, "
        "m.Type, length(m.Body), CASE WHEN m.Info LIKE '%\"edit\"%' THEN 'edit' ELSE '' END "
        "FROM Events e JOIN Messages m ON m.EventID=e.EventID "
        "WHERE e.Type=0 AND strftime('%d/%m/%Y', e.TimeStamp/1000, 'unixepoch', '+7 hours')=? "
        "ORDER BY e.TimeStamp, e.SortOrder", (day,)).fetchall()
    react = con.execute(
        "SELECT strftime('%H:%M:%S', e.TimeStamp/1000, 'unixepoch', '+7 hours'), e.Direction, 'reaction-row' "
        "FROM Events e WHERE e.Type=3 AND "
        "strftime('%d/%m/%Y', e.TimeStamp/1000, 'unixepoch', '+7 hours')=? ORDER BY e.TimeStamp", (day,)).fetchall()
    con.close()
    return rows, react


def pc_days(db, ym):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT strftime('%Y-%m-%d', e.TimeStamp/1000, 'unixepoch', '+7 hours') d, count(*) "
        "FROM Events e JOIN Messages m ON m.EventID=e.EventID "
        "WHERE e.Type=0 AND (m.Info IS NULL OR m.Info NOT LIKE '%\"edit\"%') "
        "AND strftime('%Y-%m', e.TimeStamp/1000, 'unixepoch', '+7 hours')=? GROUP BY 1", (ym,)).fetchall()
    con.close()
    return Counter({k: n for k, n in rows})


def pc_all_days(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT strftime('%Y-%m-%d', e.TimeStamp/1000, 'unixepoch', '+7 hours'), count(*) "
        "FROM Events e JOIN Messages m ON m.EventID=e.EventID "
        "WHERE e.Type=0 AND (m.Info IS NULL OR m.Info NOT LIKE '%\"edit\"%') GROUP BY 1").fetchall()
    con.close()
    return Counter({k: n for k, n in rows})


def gap_ranges(pcd, phd):
    """Ranges of consecutive days where one source has no messages and the other does."""
    from datetime import date, timedelta
    keys = sorted(set(pcd) | set(phd))
    first, last = date.fromisoformat(keys[0]), date.fromisoformat(keys[-1])
    out, cur = [], None
    d = first
    while d <= last:
        k = d.isoformat()
        a, b = pcd[k], phd[k]
        kind = "pc_gap" if a == 0 and b > 0 else "phone_gap" if b == 0 and a > 0 else None
        if kind and cur and cur[0] == kind and cur[2] == d - timedelta(days=1):
            cur[2], cur[3], cur[4] = d, cur[3] + 1, cur[4] + max(a, b)
        else:
            if kind:
                cur = [kind, d, d, 1, max(a, b)]
                out.append(cur)
            else:
                cur = None
        d += timedelta(days=1)
    return out


def pc_years(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT strftime('%Y', e.TimeStamp/1000, 'unixepoch', '+7 hours'), count(*) "
        "FROM Events e JOIN Messages m ON m.EventID=e.EventID "
        "WHERE e.Type=0 AND (m.Info IS NULL OR m.Info NOT LIKE '%\"edit\"%') "
        "GROUP BY 1").fetchall()
    con.close()
    return Counter({int(y): n for y, n in rows})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--pc", help="path to viber_export.db for a per-year comparison")
    ap.add_argument("--day", metavar="dd/MM/yyyy", help="with --pc, list one day on both sides (times, kinds, lengths; no text)")
    ap.add_argument("--daily", metavar="YYYY-MM", help="with --pc, per-day table for one month")
    ap.add_argument("--gaps", action="store_true", help="with --pc, list stretches where only one source has messages")
    ap.add_argument("--monthly", action="store_true", help="with --pc, also print a per-month table")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    files = sorted(Path(args.folder).glob("*.csv")) + sorted(Path(args.folder).glob("*.cvs"))
    if not files:
        sys.exit("No .csv files found in " + args.folder)
    total = Counter()
    months = Counter()
    days = Counter()
    for path in files:
        s = scan(path)
        print(f"\n{path.name}: {s['records']:,} records, {fmt(s['first'])} to {fmt(s['last'])}")
        print(f"   continuation lines {s['continuation']:,} | placeholder rows {s['placeholders']:,} | "
              f"lines before first record {s['before_first']} | bad dates {s['bad_date']} | "
              f"BOM {'yes' if s['bom'] else 'no'}")
        if s["records"]:
            print("   per year: " + "  ".join(f"{y}:{n:,}" for y, n in sorted(s["years"].items())))
        total.update(s["years"])
        months.update(s["months"])
        days.update(s["days"])
    print(f"\nAll files: {sum(total.values()):,} records")
    if args.pc:
        pc = pc_years(args.pc)
        print("\nYear      PC (approx)     Phone   Phone minus PC")
        for y in sorted(set(pc) | set(total)):
            print(f"{y}   {pc[y]:>11,}  {total[y]:>8,}  {total[y] - pc[y]:>+14,}")
        print(f"Total  {sum(pc.values()):>11,}  {sum(total.values()):>8,}  "
              f"{sum(total.values()) - sum(pc.values()):>+14,}")

        if args.day:
            print(f"\nPC, {args.day}: time, direction (0 in, 1 out), Messages.Type, length, edit")
            msgs, react = pc_day(args.pc, args.day)
            for r in msgs:
                print("  ", *r)
            print(f"\nPC reaction rows (Events.Type 3), {args.day}: time, direction")
            for r in react:
                print("  ", *r)
            print(f"\nPhone, {args.day}: time, direction, kind, length, emoji code if the whole body is one")
            for r in phone_day(files, args.day):
                print("  ", *r)
        if args.gaps:
            rng = gap_ranges(pc_all_days(args.pc), days)
            print("\nStretches where one source has no messages and the other does")
            print("kind        from        to          days  messages in the other source")
            for kind, a, b, n, m in rng:
                print(f"{kind:<10}  {a.strftime('%d/%m/%Y')}  {b.strftime('%d/%m/%Y')}  {n:>4}  {m:>8,}")
            for kind in ("pc_gap", "phone_gap"):
                print(f"{kind}: {sum(r[3] for r in rng if r[0]==kind)} days, "
                      f"{sum(r[4] for r in rng if r[0]==kind):,} messages")
        if args.daily:
            pdy = pc_days(args.pc, args.daily)
            print(f"\nDay         PC (approx)     Phone   Phone minus PC   ({args.daily})")
            for k in sorted(set(pdy) | {d for d in days if d.startswith(args.daily)}):
                print(f"{k}   {pdy[k]:>11,}  {days[k]:>8,}  {days[k] - pdy[k]:>+14,}")
        if args.monthly:
            pm = pc_months(args.pc)
            print("\nMonth     PC (approx)     Phone   Phone minus PC")
            for k in sorted(set(pm) | set(months)):
                print(f"{k}   {pm[k]:>11,}  {months[k]:>8,}  {months[k] - pm[k]:>+14,}")


if __name__ == "__main__":
    main()
