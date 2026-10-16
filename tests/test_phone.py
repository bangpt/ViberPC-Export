"""Tests for the phone database importer, on synthetic data."""
import json
import sqlite3

import pytest

from tests import fixture_export, fixture_phone
from viberarchive import check, pcimport, phoneimport, reconcile


@pytest.fixture(name="arc_path")
def arc_path_fixture(tmp_path):
    return str(tmp_path / "archive.db")


@pytest.fixture(name="phone")
def phone_fixture(tmp_path):
    path = tmp_path / "viber_messages"
    fixture_phone.standard(str(path))
    return path


@pytest.fixture(name="both")
def both_fixture(tmp_path, arc_path, phone):
    export = tmp_path / "viber_export.db"
    fixture_export.standard(str(export))
    pcimport.import_pc(arc_path, str(export), "pc-old", exclude_peers=["84999000999"])
    return phoneimport.import_phone_db(arc_path, str(phone), label="test"), arc_path


def q(arc_path, sql, *args):
    con = sqlite3.connect(arc_path)
    rows = con.execute(sql, args).fetchall()
    con.close()
    return rows


def test_pc_must_come_first(arc_path, phone):
    with pytest.raises(ValueError):
        phoneimport.import_phone_db(arc_path, str(phone))


def test_counts_and_chat_matching(both):
    res, arc_path = both
    assert res["status"] == "imported"
    assert res["conversations"] == 4 and res["conversations_matched"] == 2 and res["self_found"] == 1
    assert res["merged"] == 6                     # 1001 1002 1003 1009 1010 1011 are ordinary and shared
    assert res["chat_mismatch"] == 0
    # phone-only: 5001, 5002, 5005 (the edit 5004 becomes a version, the reaction 5003 a reaction)
    assert res["messages_created"] == 3
    assert q(arc_path, "SELECT count(*) FROM message")[0][0] == 9 + 3


def test_composed_time_stays_and_delivery_time_is_added(both):
    _res, arc_path = both
    composed, sent = q(arc_path, "SELECT composed_ms, sent_ms FROM message WHERE token = '1001'")[0]
    assert composed == fixture_export.T0 and sent == fixture_phone.at(0)


def test_phone_only_messages(both):
    _res, arc_path = both
    flags, tick, composed, source = q(
        arc_path, "SELECT flags, tick, composed_ms, source FROM message WHERE token = '5002'")[0]
    assert source == "phone-db" and tick == "unknown" and composed == fixture_phone.at(210, 0)
    assert "time_is_delivery" in json.loads(flags) and "tick_unknown" in json.loads(flags)
    assert q(arc_path, "SELECT tick FROM message WHERE token = '5001'")[0][0] == "none"
    assert q(arc_path, "SELECT tick FROM message WHERE token = '1002'")[0][0] == "seen"


def test_phone_edit_attaches_to_pc_original(both):
    res, arc_path = both
    assert res["versions_created"] == 1
    count, text = q(arc_path, "SELECT version_count, text FROM message WHERE token = '1002'")[0]
    assert count == 4 and text == "hi there again"


def test_reactions_merge_without_duplicates(both):
    _res, arc_path = both
    assert q(arc_path, "SELECT count(*) FROM reaction")[0][0] == 6 + 1
    rid, mid = q(arc_path, "SELECT reaction_id, message_id FROM reaction WHERE target_token = '1009'")[0]
    assert rid == 1 and mid is not None
    assert q(arc_path, "SELECT count(*) FROM reaction WHERE id IN (SELECT entity_id FROM source_record "
                       "WHERE snapshot_id = 2 AND entity = 'reaction')")[0][0] == 4 + 1


def test_unmatched_conversation_gets_a_group_key_and_contacts(both):
    _res, arc_path = both
    key, kind, title = q(arc_path, "SELECT c.chat_key, c.kind, c.title FROM message m JOIN chat c "
                                   "ON c.chat_key = m.chat_key WHERE m.token = '5005'")[0]
    assert key.startswith("group:") and kind == "group" and title == "Old group"
    assert q(arc_path, "SELECT name FROM contact WHERE number = '84777000333'")[0][0] == "Friend"
    author = q(arc_path, "SELECT author FROM message WHERE token = '5005'")[0][0]
    assert author == "84777000333"


def test_system_records(both):
    res, arc_path = both
    assert res["skipped_system"] == 1
    assert q(arc_path, "SELECT count(*) FROM standalone_event")[0][0] == 2


def test_second_import_changes_nothing_and_copy_is_kept(tmp_path, arc_path, phone, both):
    _first, _ = both
    before = q(arc_path, "SELECT count(*) FROM message")[0][0]
    again = phoneimport.import_phone_db(arc_path, str(phone), copy_to=str(tmp_path / "keep"))
    assert again["status"] == "already_imported"
    assert q(arc_path, "SELECT count(*) FROM message")[0][0] == before


def test_copy_is_made(tmp_path, arc_path, phone):
    export = tmp_path / "viber_export.db"
    fixture_export.standard(str(export))
    pcimport.import_pc(arc_path, str(export), "pc-old", exclude_peers=["84999000999"])
    res = phoneimport.import_phone_db(arc_path, str(phone), copy_to=str(tmp_path / "keep"))
    assert (tmp_path / "keep").glob("phone-db-*/viber_messages") and res["copy"].endswith("viber_messages")


def test_invariants_hold_after_phone_import(both):
    _res, arc_path = both
    con = sqlite3.connect(arc_path)
    assert all(ok for _name, ok, _detail in check.invariants(con))
    con.close()


def test_excluded_chat_stays_out_even_without_a_matching_number(both):
    res, arc_path = both
    assert res["conversations_excluded"] == 1 and res["excluded_events"] == 2
    assert q(arc_path, "SELECT count(*) FROM message WHERE token IN ('1012', '5007')")[0][0] == 0
    assert q(arc_path, "SELECT count(*) FROM contact WHERE number = '84999000999' AND first_snapshot = 2")[0][0] == 0
    assert q(arc_path, "SELECT count(*) FROM chat WHERE chat_key LIKE 'excluded%'")[0][0] == 0


def test_differences_between_the_sources_are_recorded(both):
    res, arc_path = both
    found = {k: v for k, v in res.items() if k.startswith("found_")}
    assert found == {"found_delivery_delay": 1, "found_reaction_disagree": 1, "found_text_diff": 1}
    kinds = q(arc_path, "SELECT kind, detail_json FROM recon_finding ORDER BY kind")
    detail = {k: json.loads(d) for k, d in kinds}
    assert detail["delivery_delay"]["seconds"] == 120
    assert detail["reaction_disagree"] == {"side": "me", "phone": 2, "archive": 0}
    assert detail["text_diff"] == {"pc": "hello", "phone": "hello!"}
    assert q(arc_path, "SELECT finished_utc IS NOT NULL FROM recon_run")[0][0] == 1


def test_report_files(both, tmp_path):
    _res, arc_path = both
    path = reconcile.write_report(arc_path, str(tmp_path / "out"))
    text = path.read_text(encoding="utf-8")
    assert "## Differences between the sources" in text and "text_diff" in text and "delivery_delay" in text
    assert "hello" not in text and "oops" not in text            # no message text in the report
    findings = (tmp_path / "out" / "findings.csv").read_text(encoding="utf-8-sig")
    assert "pc_length" in findings and "hello" not in findings
    assert (tmp_path / "out" / "gaps.csv").exists()
    month = [line for line in text.splitlines() if line.startswith("| 2025-")]
    assert month and "| 6 |" in month[0]                         # six messages are in both sources
