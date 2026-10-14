"""Sanity checks over archive.db: counts, invariants and the acceptance numbers of a known export."""
import json

from . import schema

# Snapshot #1 of the real export (upstream viber_export.db taken 29/09/2026), before any chat is excluded.
ACCEPTANCE = {
    "events_total": 428627,
    "content_total": 408331,
    "reaction_total": 20293,
    "standalone_total": 3,
    "distinct_messages": 396160,
    "edits_attached": 12171,
    "edit_ref_missing": 227,
}


def _one(arc, sql):
    return arc.execute(sql).fetchone()[0]


def invariants(arc):
    """Return a list of (name, ok, detail)."""
    one = lambda sql: _one(arc, sql)  # pylint: disable=unnecessary-lambda-assignment
    out = []
    n = one("SELECT count(*) FROM message WHERE chat_key NOT IN (SELECT chat_key FROM chat)")
    out.append(("every message has a chat", n == 0, n))
    n = one("SELECT count(*) FROM message m WHERE NOT EXISTS (SELECT 1 FROM message_version v WHERE v.message_id=m.id)")
    out.append(("every message has a version 0", n == 0, n))
    n = one("SELECT count(*) FROM message m WHERE version_count <> (SELECT count(*) FROM message_version v "
            "WHERE v.message_id=m.id)")
    out.append(("version_count matches the versions", n == 0, n))
    n = one("SELECT count(*) FROM (SELECT message_id, reactor FROM reaction_effective "
            "GROUP BY 1, 2 HAVING count(*) > 1)")
    out.append(("at most one effective reaction per target and reactor", n == 0, n))
    n = one("SELECT count(*) FROM message WHERE composed_ms IS NULL")
    out.append(("every message has a time", n == 0, n))
    return out


def totals(arc):
    one = lambda sql: _one(arc, sql)  # pylint: disable=unnecessary-lambda-assignment
    return {
        "snapshots": one("SELECT count(*) FROM source_snapshot"),
        "chats": one("SELECT count(*) FROM chat"),
        "contacts": one("SELECT count(*) FROM contact"),
        "messages": one("SELECT count(*) FROM message"),
        "versions": one("SELECT count(*) FROM message_version"),
        "edited_messages": one("SELECT count(*) FROM message WHERE version_count > 1"),
        "reactions": one("SELECT count(*) FROM reaction"),
        "reactions_effective": one("SELECT count(*) FROM reaction_effective"),
        "reaction_orphans": one("SELECT count(*) FROM reaction WHERE message_id IS NULL"),
        "standalone": one("SELECT count(*) FROM standalone_event"),
        "edit_ref_missing": one("SELECT count(*) FROM message WHERE flags LIKE '%edit_ref_missing%'"),
        "status_129": one("SELECT count(*) FROM message WHERE flags LIKE '%status_129%'"),
    }


def acceptance(arc, snapshot_id=1):
    """Compare snapshot #1 with the known numbers. Excluded chats are added back before comparing."""
    row = arc.execute("SELECT events_total, content_total, reaction_total, standalone_total, messages_created,"
                      " excluded_messages, edits_attached, edit_ref_missing FROM source_snapshot WHERE id=?",
                      (snapshot_id,)).fetchone()
    if row is None:
        return None
    got = {"events_total": row[0], "content_total": row[1], "reaction_total": row[2], "standalone_total": row[3],
           "distinct_messages": row[4] + row[5], "edits_attached": row[6], "edit_ref_missing": row[7]}
    return [(k, want, got[k], want == got[k]) for k, want in ACCEPTANCE.items()]


def report(archive_path, expect_first=False):
    """Print the check report. Returns True when every invariant (and, if asked, the acceptance numbers) pass."""
    arc = schema.connect(archive_path)
    ok = True
    print("Totals:")
    for key, value in totals(arc).items():
        print(f"   {key:<22} {value:>10,}")
    print("\nInvariants:")
    for name, passed, detail in invariants(arc):
        ok = ok and passed
        print(f"   {'ok  ' if passed else 'FAIL'} {name}" + ("" if passed else f"  ({detail} rows)"))
    if expect_first:
        print("\nAcceptance numbers for snapshot #1 (upstream export of 29/09/2026):")
        rows = acceptance(arc)
        if rows is None:
            print("   no snapshot #1 yet")
            ok = False
        else:
            for name, want, got, passed in rows:
                ok = ok and passed
                print(f"   {'ok  ' if passed else 'DIFF'} {name:<18} expected {want:>9,}   got {got:>9,}")
    print("\nSnapshots:")
    for row in arc.execute("SELECT id, source, label, imported_utc, events_total FROM source_snapshot ORDER BY id"):
        print("  ", json.dumps(row, ensure_ascii=False))
    arc.close()
    return ok
