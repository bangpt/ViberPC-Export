"""Tests for the archive importer, on a synthetic export."""
import json
import shutil
import sqlite3

import pytest

from tests import fixture_export
from viberarchive import check, ids, pcimport, schema


@pytest.fixture(name="export")
def export_fixture(tmp_path):
    path = tmp_path / "viber_export.db"
    fixture_export.standard(str(path))
    return path


@pytest.fixture(name="arc_path")
def arc_path_fixture(tmp_path):
    return str(tmp_path / "archive.db")


def run(arc_path, export, **kw):
    return pcimport.import_pc(arc_path, str(export), "pc-old", exclude_peers=["84999000999"], **kw)


def q(arc_path, sql, *args):
    con = sqlite3.connect(arc_path)
    rows = con.execute(sql, args).fetchall()
    con.close()
    return rows


def test_counts(arc_path, export):
    res = run(arc_path, export)
    assert res["status"] == "imported" and res["self_found"] == 1
    assert res["events_total"] == 19
    assert res["content_total"] == 12 and res["reaction_total"] == 6 and res["standalone_total"] == 1
    assert res["excluded_events"] == 1 and res["excluded_messages"] == 1
    assert res["edits_attached"] == 2 and res["edit_ref_missing"] == 3
    # 12 content events - 2 edits - 1 excluded = 9 messages
    assert res["messages_created"] == 9
    assert q(arc_path, "SELECT count(*) FROM message")[0][0] == 9


def test_chats_and_authors(arc_path, export):
    run(arc_path, export)
    keys = {r[0] for r in q(arc_path, "SELECT chat_key FROM chat")}
    assert keys == {"direct:84901000001", "notes"}
    assert q(arc_path, "SELECT author FROM message WHERE token='1001'")[0][0] == "84901000001"
    assert q(arc_path, "SELECT author FROM message WHERE token='1002'")[0][0] == "self"


def test_edits_become_versions(arc_path, export):
    run(arc_path, export)
    text, count, edited = q(arc_path, "SELECT text, version_count, edited_ms FROM message WHERE token='1002'")[0]
    assert text == "hi there!" and count == 3
    assert edited == fixture_export.T0 + 4000 * 1000
    versions = q(arc_path, "SELECT version, text FROM message_version WHERE message_id="
                           "(SELECT id FROM message WHERE token='1002') ORDER BY version")
    assert versions == [(0, "hi"), (1, "hi there"), (2, "hi there!")]
    assert q(arc_path, "SELECT count(*) FROM message WHERE token IN ('1004','1005')")[0][0] == 0


def test_unresolved_edits_stay_ordinary_and_flagged(arc_path, export):
    run(arc_path, export)
    for token in ("1006", "1007", "1008"):
        flags = json.loads(q(arc_path, "SELECT flags FROM message WHERE token=?", token)[0][0])
        assert "edit_ref_missing" in flags


def test_ticks(arc_path, export):
    run(arc_path, export)
    assert q(arc_path, "SELECT tick FROM message WHERE token='1002'")[0][0] == "seen"
    tick, flags = q(arc_path, "SELECT tick, flags FROM message WHERE token='1003'")[0]
    assert tick == "sent" and "status_129" in json.loads(flags)
    assert q(arc_path, "SELECT tick FROM message WHERE token='1001'")[0][0] == "none"


def test_kinds_and_media(arc_path, export):
    run(arc_path, export)
    assert q(arc_path, "SELECT kind, media_path FROM message WHERE token='1009'")[0] == ("image", "C:/x/photo.jpg")
    assert q(arc_path, "SELECT kind, text FROM message WHERE token='1010'")[0] == ("link", "http://a.example")


def test_reactions_last_wins_clear_recover_orphan(arc_path, export):
    run(arc_path, export)
    eff = q(arc_path, "SELECT m.token, r.reactor, r.reaction_id FROM reaction_effective r "
                      "JOIN message m ON m.id = r.message_id ORDER BY m.token")
    assert eff == [("1001", "me", 4), ("1010", "me", 3)]       # her heart on 1002 was cleared
    flags = json.loads(q(arc_path, "SELECT flags FROM reaction WHERE target_token='1010'")[0][0])
    assert "recovered_from_target" in flags
    assert q(arc_path, "SELECT count(*) FROM reaction WHERE message_id IS NULL")[0][0] == 1
    assert q(arc_path, "SELECT count(*) FROM reaction")[0][0] == 6


def test_standalone_and_excluded(arc_path, export):
    run(arc_path, export)
    assert q(arc_path, "SELECT count(*) FROM standalone_event")[0][0] == 1
    assert q(arc_path, "SELECT count(*) FROM message WHERE chat_key LIKE 'direct:84999%'")[0][0] == 0


def test_second_import_changes_nothing(arc_path, export):
    run(arc_path, export)
    before = check.totals(schema.connect(arc_path))
    res = run(arc_path, export)
    assert res["status"] == "already_imported"
    assert check.totals(schema.connect(arc_path)) == before


def test_newer_export_adds_only_new_rows(arc_path, export, tmp_path):
    run(arc_path, export)
    newer = tmp_path / "newer.db"
    shutil.copy(export, newer)
    con = sqlite3.connect(newer)
    con.execute("INSERT INTO Events VALUES (90, 0, ?, 0, 2, 2, 1100, 1100, 0)", (fixture_export.T0 + 9_000_000,))
    con.execute("INSERT INTO Messages VALUES (90, 1, NULL, 'later', NULL, NULL, 0, 0, NULL, 0, 0, NULL, NULL, NULL, 0)")
    con.commit()
    con.close()
    before = check.totals(schema.connect(arc_path))
    res = pcimport.import_pc(arc_path, str(newer), "pc-new", exclude_peers=["84999000999"])
    assert res["status"] == "imported" and res["messages_created"] == 1
    after = check.totals(schema.connect(arc_path))
    assert after["messages"] == before["messages"] + 1
    assert after["versions"] == before["versions"] + 1
    assert after["reactions"] == before["reactions"]
    assert after["snapshots"] == 2


def test_ids_are_deterministic_across_archives(export, tmp_path):
    a, b = str(tmp_path / "a.db"), str(tmp_path / "b.db")
    run(a, export)
    run(b, export)
    assert q(a, "SELECT id FROM message ORDER BY id") == q(b, "SELECT id FROM message ORDER BY id")
    assert q(a, "SELECT id FROM message WHERE token='1001'")[0][0] == ids.stable_id("direct:84901000001", "1001")


def test_invariants_hold(arc_path, export):
    run(arc_path, export)
    arc = schema.connect(arc_path)
    assert all(ok for _name, ok, _detail in check.invariants(arc))


def test_explicit_self_number(arc_path, export):
    res = pcimport.import_pc(arc_path, str(export), "pc-old", self_numbers=["+84 111 111 111"],
                             exclude_peers=["84999000999"])
    assert res["self_found"] == 1 and res["messages_created"] == 9


def test_raw_rows_are_kept(arc_path, export):
    run(arc_path, export)
    raw = json.loads(q(arc_path, "SELECT raw_json FROM message_version WHERE ver_token='1001'")[0][0])
    assert raw["Messages"]["Body"] == "hello" and raw["Events"]["Token"] == 1001
