"""Builds a small synthetic phone database (viber_messages) that goes with fixture_export.standard()."""
import json
import sqlite3

from tests.fixture_export import T0

COLS = ("_id", "conversation_id", "order_key", "msg_date", "token", "participant_id", "send_type", "extra_mime",
        "extra_uri", "extra_duration", "sticker_id", "body", "msg_info", "seq",
        "quoted_message_data", "my_reaction", "likes_count")


class Phone:
    """Collects phone rows and writes the database."""

    def __init__(self):
        self.rows, self.next_id = [], 1

    def add(self, token, ts_ms, conv, send_type, body="", mime=0, info=None, uri=None, pid=0,  # pylint: disable=too-many-arguments,too-many-positional-arguments
            mine=0, likes=0):
        self.rows.append((self.next_id, conv, token, ts_ms, token, pid, send_type, mime, uri, None, None, body,
                          json.dumps(info) if info is not None else "", None, "", mine, likes))
        self.next_id += 1

    def write(self, path):
        con = sqlite3.connect(path)
        con.executescript(f"""
            CREATE TABLE messages({", ".join(COLS)});
            CREATE TABLE conversations(_id INTEGER PRIMARY KEY, conversation_type INTEGER, name TEXT);
            CREATE TABLE participants(_id INTEGER PRIMARY KEY, conversation_id INTEGER, participant_info_id INTEGER);
            CREATE TABLE participants_info(_id INTEGER PRIMARY KEY, number TEXT, display_name TEXT,
                contact_name TEXT, viber_name TEXT, viber_id TEXT);
        """)
        con.executemany(f"INSERT INTO messages VALUES ({','.join('?' * len(COLS))})", self.rows)
        con.executemany("INSERT INTO conversations VALUES (?,?,?)",
                        [(1, 0, None), (2, 0, None), (3, 2, "Old group"), (4, 0, None)])
        con.executemany("INSERT INTO participants_info VALUES (?,?,?,?,?,?)", [
            (1, "+84111111111", "Me", "Me", None, None), (2, "+84 901 000 001", "Partner", "Partner", None, None),
            (3, "84777000333", "Friend", None, "Friend", "f1"), (4, "84999000999", "Son", None, None, None)])
        con.executemany("INSERT INTO participants VALUES (?,?,?)", [
            (10, 1, 1), (11, 1, 2), (12, 2, 1), (13, 3, 1), (14, 3, 2), (15, 3, 3), (16, 4, 1), (17, 4, 4)])
        con.commit()
        con.close()


def at(offset_s, delay_s=2):
    """Phone time of a message the PC composed at offset_s: the phone shows the delivery time."""
    return T0 + offset_s * 1000 + delay_s * 1000


def reaction(rid, target):
    """A phone reaction row: body is the emoji code, the target token sits in quote.token."""
    return {"1on1reactions": {"reaction": rid}, "quote": {"token": int(target), "type": 0}}


def standard(path):
    """Phone side of the standard fixture: most PC messages, plus rows only the phone has."""
    p = Phone()
    p.add(1001, at(0), 1, 0, "hello!", pid=11, mine=4, likes=1)       # text differs; my sad matches
    p.add(1002, at(10), 1, 1, "hi")
    p.add(1003, at(20, 120), 1, 1, "oops")                                # delivered two minutes late
    p.add(1004, at(3000), 1, 1, "hi there", info={"edit": {"token": "1002"}})
    p.add(1005, at(4000), 1, 1, "hi there!", info={"edit": {"token": "1002"}})
    p.add(1009, at(60) - 2 ** 31, 1, 0, "caption", mime=1, uri="content://media/photo.jpg", pid=11, likes=1)
    p.add(1010, at(70), 1, 0, "http://a.example", mime=8, pid=11)
    p.add(1011, at(80), 2, 1, "note to self", mine=2, likes=1)            # reaction the archive does not have
    p.add(2001, at(100), 1, 0, "(heart)", info=reaction(1, 1002), pid=11)
    p.add(2002, at(110), 1, 1, "(heart)", info=reaction(2, 1001))
    p.add(2003, at(120), 1, 1, "(heart)", info=reaction(4, 1001))
    p.add(2004, at(130), 1, 0, "(heart)", info=reaction(0, 1002), pid=11)
    p.add(1012, at(90), 4, 0, "son test", pid=17)                # the chat the PC import left out
    p.add(5007, at(260, 0), 4, 0, "son phone only", pid=17)
    p.add(3001, at(160), 1, 0, "", mime=1002, pid=11)                      # system record the PC also has
    # only on the phone:
    p.add(5001, at(200, 0), 1, 0, "phone only in", pid=11)
    p.add(5002, at(210, 0), 1, 1, "phone only out")
    p.add(5003, at(220, 0), 1, 0, "(heart)", info=reaction(1, 1009), pid=11)        # a reaction row the PC lacks
    p.add(5004, at(5000, 0), 1, 1, "hi there again", info={"edit": {"token": "1002"}})   # edit of a PC message
    p.add(5005, at(240, 0), 3, 0, "old group hello", pid=15)
    p.add(5008, at(260, 0) - 2 ** 31, 1, 0, "wrapped date", pid=11)       # the phone's date is 2**31 ms too early
    p.add(5006, at(250, 0), 1, 0, "", mime=1002, pid=11)                   # system record, new
    p.write(path)
