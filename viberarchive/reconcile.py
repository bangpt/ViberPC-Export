"""Reconciliation report: what each source gave, what was merged, and where the two sources disagree.

Message-level differences (text, kind, sender, delivery delay, reactions) are recorded while the phone database is
imported, because that is when both rows are at hand. This module adds what can be derived from the archive alone
(which source has which days and months, gaps in one source) and writes everything as a Markdown report plus CSV files.
"""
import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import schema

TZ = timezone(timedelta(hours=7))
DAY = "date(m.composed_ms / 1000, 'unixepoch', '+7 hours')"
MAX_LISTED = 60
EXPLAIN = {
    "text_diff": "same message, different text on the PC and the phone",
    "kind_diff": "same message, different kind (text, photo, link...)",
    "sender_diff": "same message, different sender",
    "delivery_delay": "phone time is more than a minute after the PC time (message queued while offline)",
    "time_early": "phone time is more than 5 seconds before the PC time (usually a message sent from the phone that "
                  "reached the PC a few seconds later)",
    "phone_time_overflow": "the phone's date is 24.86 days (2**31 ms) too early; the PC time is kept and the phone "
                           "time is not stored",
    "resent_duplicate": "a PC message that never reached the phone (status 129) was sent again a moment later; the "
                        "first attempt is hidden in the viewer, the copy on the phone is kept",
    "reaction_disagree": "the phone's own reaction columns differ from the reactions in the archive",
}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _ids(arc, like):
    return [r[0] for r in arc.execute("SELECT id FROM source_snapshot WHERE source LIKE ?", (like,))]


def _day_rows(arc):
    """(chat_key, day, both, pc_only, phone_only) for every chat and local day."""
    pc, ph = _ids(arc, "pc-%"), _ids(arc, "phone%")
    if not pc or not ph:
        return []
    flag = ("EXISTS (SELECT 1 FROM source_record r WHERE r.entity = 'message' AND r.entity_id = m.id"
            " AND r.snapshot_id IN ({}))")
    in_pc, in_ph = flag.format(",".join(map(str, pc))), flag.format(",".join(map(str, ph)))
    sql = (f"SELECT chat_key, day, sum(p AND h), sum(p AND NOT h), sum(h AND NOT p) FROM "
           f"(SELECT m.chat_key AS chat_key, {DAY} AS day, {in_pc} AS p, {in_ph} AS h FROM message m) "
           "GROUP BY chat_key, day ORDER BY chat_key, day")
    return arc.execute(sql).fetchall()


def _ranges(days, kind):
    """Merge consecutive calendar days into (from, to, days, messages)."""
    out = []
    for day, count in days:
        d = date.fromisoformat(day)
        if out and d - out[-1][1] == timedelta(days=1):
            out[-1][1], out[-1][2], out[-1][3] = d, out[-1][2] + 1, out[-1][3] + count
        else:
            out.append([d, d, 1, count])
    return [(kind, a.isoformat(), b.isoformat(), n, c) for a, b, n, c in out]


def analyse(arc):
    """Work out the per-chat gaps and the month table. Returns a dict; nothing is written."""
    rows = _day_rows(arc)
    pc_last = arc.execute("SELECT max(last_event_ms) FROM source_snapshot WHERE source LIKE 'pc-%'").fetchone()[0]
    ph_first = arc.execute("SELECT min(first_event_ms) FROM source_snapshot WHERE source LIKE 'phone%'").fetchone()[0]
    pc_last_day = datetime.fromtimestamp(pc_last / 1000, TZ).date().isoformat() if pc_last else "9999-12-31"
    ph_first_day = datetime.fromtimestamp(ph_first / 1000, TZ).date().isoformat() if ph_first else "0000-01-01"
    per_chat = defaultdict(lambda: {"pc_gap": [], "phone_gap": []})
    months = defaultdict(lambda: [0, 0, 0])
    partial = []
    for chat, day, both, pc_only, ph_only in rows:
        if day is None:
            continue
        month = months[day[:7]]
        month[0] += both
        month[1] += pc_only
        month[2] += ph_only
        if both == 0 and ph_only > 0 and day <= pc_last_day:
            per_chat[chat]["pc_gap"].append((day, ph_only))
        elif both == 0 and pc_only > 0 and day >= ph_first_day:
            per_chat[chat]["phone_gap"].append((day, pc_only))
        elif both > 0 and (pc_only or ph_only):
            partial.append((day, chat, pc_only, ph_only))
    gaps = []
    for chat, kinds in per_chat.items():
        for kind, days in kinds.items():
            gaps += [(chat,) + r for r in _ranges(days, kind)]
    return {"gaps": sorted(gaps, key=lambda g: (g[0], g[2])), "months": dict(sorted(months.items())),
            "partial_days": sorted(partial, key=lambda p: -(p[2] + p[3])), "pc_last_day": pc_last_day,
            "ph_first_day": ph_first_day}


def _day(ms):
    return datetime.fromtimestamp(ms / 1000, TZ).strftime("%d/%m/%Y") if ms else "-"


def _scalar(arc, sql, *args):
    return arc.execute(sql, args).fetchone()[0]


def _labels(arc):
    rows = arc.execute("SELECT c.chat_key, c.kind, c.title, count(m.id) FROM chat c LEFT JOIN message m"
                       " ON m.chat_key = c.chat_key GROUP BY c.chat_key ORDER BY 4 DESC").fetchall()
    return {key: f"chat {n} ({kind}{', ' + title if title else ''})"
            for n, (key, kind, title, _c) in enumerate(rows, 1)}


def write_report(archive_path, out_dir):  # pylint: disable=too-many-locals,too-many-statements
    """Write reconciliation.md, gaps.csv and findings.csv into out_dir. Returns the Markdown path."""
    arc = schema.connect(archive_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    info = analyse(arc)
    labels = _labels(arc)
    run = arc.execute("INSERT INTO recon_run(started_utc, params_json) VALUES (?,?)",
                      (_now(), json.dumps({"kind": "report"}))).lastrowid
    for chat, kind, a, b, n, c in info["gaps"]:
        arc.execute("INSERT INTO recon_finding(run_id, kind, message_id, detail_json) VALUES (?,?,NULL,?)",
                    (run, kind, json.dumps({"chat": chat, "from": a, "to": b, "days": n, "messages": c})))
    arc.execute("UPDATE recon_run SET finished_utc = ? WHERE id = ?", (_now(), run))
    arc.commit()

    with open(out / "gaps.csv", "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["chat", "gap_in", "from", "to", "days", "messages_in_other_source"])
        for chat, kind, a, b, n, c in info["gaps"]:
            writer.writerow([labels.get(chat, chat), "PC" if kind == "pc_gap" else "phone", a, b, n, c])
    with open(out / "days.csv", "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["day", "chat", "only_in_PC", "only_on_phone"])
        writer.writerows([d, labels.get(c, c), a, b] for d, c, a, b in info["partial_days"])
    kinds = Counter()
    with open(out / "findings.csv", "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["kind", "chat", "time_hanoi", "message_id", "detail (no message text)"])
        query = ("SELECT f.kind, m.chat_key, m.composed_ms, f.message_id, f.detail_json FROM recon_finding f"
                 " JOIN message m ON m.id = f.message_id ORDER BY f.kind, m.composed_ms")
        for kind, chat, ms, mid, detail in arc.execute(query):
            kinds[kind] += 1
            data = json.loads(detail)
            if kind == "text_diff":
                data = {"pc_length": len(data.get("pc") or ""), "phone_length": len(data.get("phone") or "")}
            writer.writerow([kind, labels.get(chat, chat), datetime.fromtimestamp(ms / 1000, TZ).strftime(
                "%Y-%m-%d %H:%M:%S"), mid, json.dumps(data, ensure_ascii=False)])

    lines = ["# Viber archive: reconciliation report", "", f"Generated {_now()} UTC from `{archive_path}`.", ""]
    lines += ["## Sources", "", "| # | source | label | imported (UTC) | first message | last message | events |",
              "|---|---|---|---|---|---|---|"]
    for sid, src, label, when, first, last, events in arc.execute(
            "SELECT id, source, label, imported_utc, first_event_ms, last_event_ms, events_total FROM source_snapshot"):
        lines.append(f"| {sid} | {src} | {label or ''} | {when} | {_day(first)} | {_day(last)} | {events:,} |")
    total = _scalar(arc, "SELECT count(*) FROM message")
    both = sum(m[0] for m in info["months"].values())
    pc_only = sum(m[1] for m in info["months"].values())
    ph_only = sum(m[2] for m in info["months"].values())
    lines += ["", "## What the archive holds", "",
              f"- **{total:,} messages** in {_scalar(arc, 'SELECT count(*) FROM chat')} chats, with "
              f"{_scalar(arc, 'SELECT count(*) FROM message_version'):,} versions (originals plus edits) and "
              f"{_scalar(arc, 'SELECT count(*) FROM reaction'):,} reaction records.",
              f"- In both sources: **{both:,}**. Only in the PC export: **{pc_only:,}**. Only on the phone: "
              f"**{ph_only:,}**.", ""]
    stats = [json.loads(m) for (m,) in arc.execute(
        "SELECT message FROM import_log WHERE level = 'info' AND message LIKE '{%' ORDER BY id")]
    lines += ["## Merged, deduplicated and fixed", ""]
    for snap, st in zip(arc.execute("SELECT id, source FROM source_snapshot ORDER BY id").fetchall(), stats):
        lines.append(f"- Snapshot {snap[0]} ({snap[1]}): " + ", ".join(
            f"{k.replace('_', ' ')} {v:,}" for k, v in st.items() if v and not k.startswith("found_")))
    lines += [f"- Delivery time from the phone stored beside the composed time on "
              f"{_scalar(arc, 'SELECT count(*) FROM message WHERE sent_ms IS NOT NULL'):,} messages.", ""]
    lines += ["## Differences between the sources for the same message", ""]
    if kinds:
        lines += ["| kind | count | meaning |", "|---|---|---|"]
        lines += [f"| {k} | {n:,} | {EXPLAIN.get(k, '')} |" for k, n in sorted(kinds.items())]
    else:
        lines.append("None recorded. (They are written when the phone database is imported.)")
    lines += ["", "Every difference is listed with its time and chat in `findings.csv`.", ""]
    lines += ["## Gaps: stretches where one source has no messages", "",
              f"PC export covers up to {info['pc_last_day']}; the phone database starts {info['ph_first_day']}. "
              "Days after the PC export are not counted as gaps.", ""]
    if info["gaps"]:
        lines += ["| chat | missing in | from | to | days | messages the other source has |",
                  "|---|---|---|---|---|---|"]
        for chat, kind, a, b, n, c in sorted(info["gaps"], key=lambda g: -g[5])[:MAX_LISTED]:
            where = "PC" if kind == "pc_gap" else "phone"
            lines.append(f"| {labels.get(chat, chat)} | {where} | {a} | {b} | {n} | {c:,} |")
        if len(info["gaps"]) > MAX_LISTED:
            lines.append(f"\nThe {MAX_LISTED} largest of {len(info['gaps'])} gaps are shown; all are in gaps.csv.")
    else:
        lines.append("None.")
    lines += ["", "## Days where both sources have messages but not the same ones", ""]
    if info["partial_days"]:
        lines += ["| day | chat | only in PC | only on phone |", "|---|---|---|---|"]
        lines += [f"| {d} | {labels.get(c, c)} | {a:,} | {b:,} |" for d, c, a, b in info["partial_days"][:MAX_LISTED]]
        if len(info["partial_days"]) > MAX_LISTED:
            lines.append(f"\nThe {MAX_LISTED} biggest of {len(info['partial_days'])} days are shown; "
                         "all are in days.csv.")
    else:
        lines.append("None.")
    lines += ["", "## Month by month", "", "| month | in both | PC only | phone only |", "|---|---|---|---|"]
    lines += [f"| {m} | {v[0]:,} | {v[1]:,} | {v[2]:,} |" for m, v in info["months"].items()]
    lines += ["", "## Still open", ""]
    for label, sql in (
            ("edit rows whose original message is in neither source (kept as ordinary messages)",
             "SELECT count(*) FROM message WHERE flags LIKE '%edit_ref_missing%'"),
            ("outgoing messages that the PC marks as sent but never delivered (single grey tick)",
             "SELECT count(*) FROM message WHERE flags LIKE '%status_129%'"),
            ("outgoing phone-only messages whose tick is unknown",
             "SELECT count(*) FROM message WHERE tick = 'unknown'"),
            ("phone-only messages whose time is the delivery time, not the composed time",
             "SELECT count(*) FROM message WHERE flags LIKE '%time_is_delivery%'"),
            ("reactions whose target message is not in the archive",
             "SELECT count(*) FROM reaction WHERE message_id IS NULL")):
        lines.append(f"- {_scalar(arc, sql):,} {label}")
    path = out / "reconciliation.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    arc.close()
    return path
