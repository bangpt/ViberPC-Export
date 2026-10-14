"""Builds a small synthetic viber_export.db with the shapes the real export has (no real data)."""
import json
import sqlite3

MESSAGE_SCHEMA = (
    "EventID INTEGER, Type INTEGER, Subject TEXT, Body TEXT, PayloadPath TEXT, ThumbnailPath TEXT, "
    "StickerID INTEGER, Duration INTEGER, Info TEXT, PGIsLiked INTEGER, PGLikeCount INTEGER, "
    "SelfReaction TEXT, MembersReactions TEXT, AdminsReactions TEXT, Status INTEGER"
)
T0 = 1_752_587_000_000      # an arbitrary UTC millisecond timestamp


class Builder:
    """Collects events and writes the database."""

    def __init__(self):
        self.events, self.messages, self.next_id = [], [], 1

    def add(self, token, ts_offset_s, direction, chat, kind=1, body="", info=None,  # pylint: disable=too-many-arguments,too-many-positional-arguments
            status=None, event_type=0, members_reactions=None, payload=None, has_message=True):
        eid = self.next_id
        self.next_id += 1
        contact = 1 if direction == 1 else (3 if chat == 40 else 2)
        ts = T0 + ts_offset_s * 1000
        self.events.append((eid, event_type, ts, direction, chat, contact, token, int(token or 0), 0))
        if has_message:
            if status is None:
                status = 130 if direction == 1 and event_type == 0 else 0
            self.messages.append((eid, kind, None, body, payload, None, 0, 0,
                                  json.dumps(info) if info is not None else None, 0, 0, None,
                                  members_reactions, None, status))
        return eid

    def write(self, path):
        con = sqlite3.connect(path)
        con.executescript(f"""
            CREATE TABLE Events(EventID INTEGER PRIMARY KEY, Type INTEGER, TimeStamp INTEGER, Direction INTEGER,
                ChatID INTEGER, ContactID INTEGER, Token INTEGER, SortOrder INTEGER, Seq INTEGER);
            CREATE TABLE Messages({MESSAGE_SCHEMA});
            CREATE TABLE Contact(ContactID INTEGER PRIMARY KEY, Name TEXT, Number TEXT, ClientName TEXT);
            CREATE TABLE ChatInfo(ChatID INTEGER, Name TEXT);
            CREATE TABLE ChatRelation(ChatID INTEGER, ContactID INTEGER);
        """)
        con.executemany("INSERT INTO Events VALUES (?,?,?,?,?,?,?,?,?)", self.events)
        con.executemany("INSERT INTO Messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", self.messages)
        con.executemany("INSERT INTO Contact VALUES (?,?,?,?)", [
            (1, "Me", "+84111111111", None), (2, "Partner", "+84 901 000 001", None), (3, "Son", "84999000999", None)])
        con.executemany("INSERT INTO ChatInfo VALUES (?,?)", [(1, "My Notes"), (2, None), (40, None)])
        con.executemany("INSERT INTO ChatRelation VALUES (?,?)", [(1, 1), (2, 1), (2, 2), (40, 1), (40, 3)])
        con.commit()
        con.close()


def reaction(rid, **extra):
    info = {"1on1reactions": {"reaction": rid, **extra}}
    return info


def standard(path):
    """The standard fixture. Tokens: 1001.. are content, 2001.. are reaction rows."""
    b = Builder()
    b.add(1001, 0, 0, 2, body="hello")                                   # incoming text
    b.add(1002, 10, 1, 2, body="hi")                                     # outgoing, later edited twice
    b.add(1003, 20, 1, 2, body="oops", status=129)                       # sent, never delivered
    b.add(1004, 3000, 1, 2, body="hi there", info={"edit": {"token": "1002"}})
    b.add(1005, 4000, 1, 2, body="hi there!", info={"edit": {"token": "1002"}})
    b.add(1006, 30, 1, 2, body="x", info={"edit": {"token": "9999"}})    # edit whose original is gone
    b.add(1007, 40, 1, 2, body="y", info={"editedWithToken": "8888"})    # only the weaker marker
    b.add(1008, 50, 1, 2, body="z", info={"edit": {}})                   # empty edit field
    b.add(1009, 60, 0, 2, kind=2, body="caption", payload="C:/x/photo.jpg")
    b.add(1010, 70, 0, 2, kind=9, body="http://a.example", info={"URL": "http://a.example", "Title": "A"},
          members_reactions='{"3":1}')
    b.add(1011, 80, 1, 1, body="note to self")                           # My Notes
    b.add(1012, 90, 0, 40, body="son test")                              # chat to leave out
    b.add(2001, 100, 0, 2, kind=0, body="1002", info=reaction(1), event_type=3)     # her heart on 1002
    b.add(2002, 110, 1, 2, kind=0, body="1001", info=reaction(2), event_type=3)     # my laugh, changed below
    b.add(2003, 120, 1, 2, kind=0, body="1001", info=reaction(4), event_type=3)     # my sad wins
    b.add(2004, 130, 0, 2, kind=0, body="1002", info=reaction(0), event_type=3)     # her reaction cleared
    b.add(2005, 140, 1, 2, kind=0, body="1010", info=None, event_type=3)            # empty Info, recovered
    b.add(2006, 150, 0, 2, kind=0, body="777777", info=reaction(1), event_type=3)   # orphan
    b.add(3001, 160, 0, 2, event_type=1, has_message=False)                         # event with no message
    b.write(path)
