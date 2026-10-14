"""Import one upstream PC export (viber_export.db) into the archive.

Rules (see the design spec):
  * Events.Type 0 = content, 3 = reaction record, anything else without a message row = standalone.
  * A message is identified by its original Token. Edit events point to it through Info.edit.token and
    become versions of that message; the latest version is what the message shows.
  * Edit events whose original is not in the database stay ordinary messages and are flagged edit_ref_missing.
  * Reactions: the last row per (target, reactor) wins and id 0 clears it. Your own rows with an empty Info
    are recovered from the target's MembersReactions.
  * Importing the same file twice changes nothing; importing a newer export adds only what is new.
"""
import json
import sqlite3
from datetime import datetime, timezone

from viberkit import enrich

from . import ids, schema

MESSAGE_COLS = (
    "Type", "Subject", "Body", "PayloadPath", "ThumbnailPath", "StickerID", "Duration", "Info",
    "PGIsLiked", "PGLikeCount", "SelfReaction", "MembersReactions", "AdminsReactions", "Status",
)
EVENT_COLS = ("EventID", "Type", "TimeStamp", "Direction", "ChatID", "ContactID", "Token", "SortOrder", "Seq")
BATCH = 5000
MAX_CHAIN = 10


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _token(value):
    return None if value is None or str(value).strip() == "" else str(value).strip()


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


class Context:
    """Everything an import needs: lookups built from the export's small tables."""

    def __init__(self, src, self_numbers, exclude_peers):
        self.contacts = {}          # ContactID -> (name, digits, client_name, raw dict)
        for row in src.execute("SELECT * FROM Contact"):
            raw = dict(row)
            number = ids.digits(raw.get("Number"))
            self.contacts[raw["ContactID"]] = (raw.get("Name"), number, raw.get("ClientName"), raw)
        self.chat_names = {r["ChatID"]: r["Name"] for r in src.execute("SELECT ChatID, Name FROM ChatInfo")}
        self.members = {}
        for row in src.execute("SELECT ChatID, ContactID FROM ChatRelation"):
            self.members.setdefault(row["ChatID"], []).append(row["ContactID"])
        self.self_ids = self._find_self(self_numbers)
        self.exclude = {f"direct:{ids.digits(p)}" for p in exclude_peers}
        self.chat_cache = {}

    def _find_self(self, self_numbers):
        wanted = {ids.digits(n) for n in self_numbers or [] if ids.digits(n)}
        if wanted:
            return {cid for cid, (_n, num, _c, _r) in self.contacts.items() if num in wanted}
        chats = [m for m in self.members.values() if m]
        counts = {}
        for members in chats:
            for cid in set(members):
                counts[cid] = counts.get(cid, 0) + 1
        return {cid for cid, n in counts.items() if n == len(chats) and n >= 2}

    def author(self, contact_id, direction):
        if direction == 1:
            return "self"
        entry = self.contacts.get(contact_id)
        return (entry[1] or None) if entry else None

    def chat(self, chat_id, contact_id, direction):
        """Return (chat_key, kind, title, peers) for a local ChatID."""
        key = (chat_id, contact_id if direction == 0 else None)
        if key in self.chat_cache:
            return self.chat_cache[key]
        peers = sorted({self.contacts[c][1] or f"noid:{ids.stable_id(self.contacts[c][0])}"
                        for c in self.members.get(chat_id, []) if c in self.contacts and c not in self.self_ids})
        title = self.chat_names.get(chat_id) or ""
        if len(peers) > 1:
            result = (f"group:{ids.stable_id(*peers)[:12]}", "group", title, peers)
        elif len(peers) == 1:
            result = (f"direct:{peers[0]}", "direct", title, peers)
        elif self.members.get(chat_id):
            result = ("notes", "notes", title or "My Notes", [])
        else:
            number = self.author(contact_id, direction)
            if number and number != "self":
                result = (f"direct:{number}", "direct", title, [number])
            else:
                result = (f"unmapped:{chat_id}", "unmapped", title, [])
        self.chat_cache[key] = result
        return result


def _open_source(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _scan_edits(src):
    """First pass over Info: which events are edit events, and the MembersReactions of targets."""
    edit_of = {}            # edit event token -> original token it points to
    all_tokens = set()
    for token, info in src.execute(
            "SELECT e.Token, m.Info FROM Events e JOIN Messages m ON m.EventID = e.EventID WHERE e.Type = 0"):
        token = _token(token)
        if token is None:
            continue
        all_tokens.add(token)
        parsed = enrich.parse_info(info)
        edit = parsed.get("edit")
        if isinstance(edit, dict) and _token(edit.get("token")):
            edit_of[token] = _token(edit["token"])
    members_reactions = {}
    for token, mr in src.execute(
            "SELECT e.Token, m.MembersReactions FROM Events e JOIN Messages m ON m.EventID = e.EventID "
            "WHERE e.Type = 0 AND m.MembersReactions IS NOT NULL AND m.MembersReactions <> ''"):
        if _token(token):
            members_reactions[_token(token)] = mr
    return edit_of, all_tokens, members_reactions


def _resolve_original(token, edit_of, all_tokens):
    """Follow edit pointers to the original message token; None when this is not a resolvable edit."""
    if token not in edit_of:
        return None
    current = edit_of[token]
    for _ in range(MAX_CHAIN):
        if current not in all_tokens:
            return None
        if current not in edit_of:
            return current
        current = edit_of[current]
    return None


def _reaction_id(info, direction, target_token, members_reactions):
    """Return (reaction_id or None, flags)."""
    flags = []
    parsed = enrich.parse_info(info).get("1on1reactions")
    if isinstance(parsed, dict):
        rid = parsed.get("reaction")
        if rid is None:
            rid = parsed.get("reaction_v1")
        try:
            return int(rid), flags
        except (TypeError, ValueError):
            flags.append("reaction_unreadable")
            return None, flags
    if direction == 1 and target_token in members_reactions:
        try:
            keys = sorted(json.loads(members_reactions[target_token]).keys())
        except (ValueError, AttributeError):
            keys = []
        if len(keys) == 1 and keys[0].lstrip("-").isdigit():
            return int(keys[0]), ["recovered_from_target"]
        flags.append("recovery_ambiguous" if keys else "reaction_unreadable")
        return None, flags
    flags.append("reaction_unreadable")
    return None, flags


def _tick(direction, status):
    if direction != 1:
        return "none", []
    if status == 130:
        return "seen", []
    if status == 129:
        return "sent", ["status_129"]
    return "none", []


class Importer:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """One import run. Use import_pc() instead of constructing this directly."""

    def __init__(self, arc, src, snapshot_id, source, ctx):
        self.arc, self.src, self.snap, self.source, self.ctx = arc, src, snapshot_id, source, ctx
        self.edit_of, self.all_tokens, self.members_reactions = _scan_edits(src)
        self.msg_by_token = {}      # token -> message id (originals and ordinary messages only)
        self.pending_edits = []
        self.pending_reactions = []
        self.stats = {k: 0 for k in (
            "events_total", "content_total", "reaction_total", "standalone_total", "excluded_events",
            "excluded_messages", "messages_created", "edits_attached", "edit_ref_missing",
            "reactions_created", "reactions_orphan", "reactions_recovered", "reactions_unreadable",
            "versions_created", "tokenless")}
        self.first_ms = self.last_ms = None
        self.touched = set()

    # -- helpers -----------------------------------------------------------------------------------------
    def _lineage(self, entity, entity_id, event_id):
        self.arc.execute("INSERT OR IGNORE INTO source_record VALUES (?,?,?,?)",
                         (self.snap, entity, entity_id, event_id))

    def _ensure_chat(self, key, kind, title, peers):
        self.arc.execute("INSERT OR IGNORE INTO chat VALUES (?,?,?,?,?)",
                         (key, kind, title, _json(peers), self.snap))

    def _raw(self, ev, msg):
        return _json({"Events": ev, "Messages": msg})

    # -- one event -----------------------------------------------------------------------------------------
    def _handle(self, ev, msg):
        self.stats["events_total"] += 1
        ts = ev["TimeStamp"]
        self.first_ms = ts if self.first_ms is None else min(self.first_ms, ts)
        self.last_ms = ts if self.last_ms is None else max(self.last_ms, ts)
        key, kind, title, peers = self.ctx.chat(ev["ChatID"], ev["ContactID"], ev["Direction"])
        if msg is None:
            self.stats["standalone_total"] += 1
        elif ev["Type"] == 3:
            self.stats["reaction_total"] += 1
        else:
            self.stats["content_total"] += 1
        if key in self.ctx.exclude:
            self.stats["excluded_events"] += 1
            if msg is not None and ev["Type"] == 0 and _resolve_original(
                    _token(ev["Token"]), self.edit_of, self.all_tokens) is None:
                self.stats["excluded_messages"] += 1
            return
        self._ensure_chat(key, kind, title, peers)
        if msg is None:
            self._standalone(ev, key)
        elif ev["Type"] == 3:
            self.pending_reactions.append((ev, msg, key))
        else:
            self._content(ev, msg, key)

    def _standalone(self, ev, key):
        sid = ids.stable_id(key, "standalone", ev["Type"], ev["TimeStamp"], ev["SortOrder"], ev["Token"])
        self.arc.execute("INSERT OR IGNORE INTO standalone_event VALUES (?,?,?,?,?,?)",
                         (sid, key, ev["Type"], ev["TimeStamp"], _json({"Events": ev}), self.snap))
        self._lineage("standalone", sid, ev["EventID"])

    def _content(self, ev, msg, key):
        token = _token(ev["Token"])
        if token is None:
            self.stats["tokenless"] += 1
        original = _resolve_original(token, self.edit_of, self.all_tokens) if token else None
        if original is not None:
            self.pending_edits.append((ev, msg, key, original))
            return
        flags = []
        info = enrich.parse_info(msg["Info"])
        if "edit" in info or "editedWithToken" in info:
            flags.append("edit_ref_missing")
            self.stats["edit_ref_missing"] += 1
        if token is None:
            flags.append("no_token")
        self._insert_message(ev, msg, key, token, flags)

    def _insert_message(self, ev, msg, key, token, flags):
        mid = ids.stable_id(key, token) if token else ids.stable_id(
            key, "tokenless", ev["TimeStamp"], ev["SortOrder"], ev["Seq"], ev["Direction"], msg["Body"])
        desc = enrich.describe(dict(msg))
        text = desc["url"] if desc["kind"] == "link" else (msg["Body"] or "").strip()
        info = enrich.parse_info(msg["Info"])
        reply = info.get("quote")
        tick, tick_flags = _tick(ev["Direction"], msg["Status"])
        before = self.arc.total_changes
        self.arc.execute(
            "INSERT OR IGNORE INTO message(id, chat_key, token, direction, author, composed_ms, sort_order, seq,"
            " kind, text, caption, reply_json, media_path, status, tick, flags, source, first_snapshot)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid, key, token, "out" if ev["Direction"] == 1 else "in",
             self.ctx.author(ev["ContactID"], ev["Direction"]),
             ev["TimeStamp"], ev["SortOrder"], ev["Seq"], desc["kind"], text, desc["caption"],
             _json(reply) if reply is not None else None, desc["media_path"] or None, msg["Status"], tick,
             _json(flags + tick_flags), self.source, self.snap))
        created = self.arc.total_changes > before
        if created:
            self.stats["messages_created"] += 1
        if token:
            self.msg_by_token[token] = mid
        ver_token = token or mid
        self.arc.execute(
            "INSERT OR IGNORE INTO message_version VALUES (?,?,?,?,?,?,?,?,?)",
            (mid, ver_token, 0, ev["TimeStamp"], desc["kind"], text, desc["caption"], self._raw(ev, msg), self.snap))
        self._lineage("message", mid, ev["EventID"])
        return mid

    # -- deferred work -----------------------------------------------------------------------------------------
    def _attach_edits(self):
        for ev, msg, key, original in self.pending_edits:
            mid = self.msg_by_token.get(original)
            if mid is None:
                # The original is not imported (for example it sits in an excluded chat): keep it as a message.
                self._insert_message(ev, msg, key, _token(ev["Token"]), ["edit_ref_missing"])
                self.stats["edit_ref_missing"] += 1
                continue
            desc = enrich.describe(dict(msg))
            text = desc["url"] if desc["kind"] == "link" else (msg["Body"] or "").strip()
            before = self.arc.total_changes
            self.arc.execute(
                "INSERT OR IGNORE INTO message_version VALUES (?,?,?,?,?,?,?,?,?)",
                (mid, _token(ev["Token"]), 1, ev["TimeStamp"], desc["kind"], text, desc["caption"],
                 self._raw(ev, msg), self.snap))
            if self.arc.total_changes > before:
                self.stats["versions_created"] += 1
                self.touched.add(mid)
            self.stats["edits_attached"] += 1
            self._lineage("version", f"{mid}:{_token(ev['Token'])}", ev["EventID"])

    def _renumber(self):
        """Recompute version numbers and the displayed (latest) content of every message that gained edits."""
        for mid in self.touched:
            rows = self.arc.execute(
                "SELECT ver_token, composed_ms, kind, text, caption FROM message_version WHERE message_id = ?"
                " ORDER BY CASE WHEN version = 0 THEN 0 ELSE 1 END, composed_ms, ver_token", (mid,)).fetchall()
            for number, row in enumerate(rows):
                self.arc.execute("UPDATE message_version SET version = ? WHERE message_id = ? AND ver_token = ?",
                                 (number, mid, row[0]))
            last = rows[-1]
            self.arc.execute(
                "UPDATE message SET kind = ?, text = ?, caption = ?, version_count = ?, edited_ms = ? WHERE id = ?",
                (last[2], last[3], last[4], len(rows), last[1] if len(rows) > 1 else None, mid))

    def _store_reactions(self):
        for ev, msg, key in self.pending_reactions:
            target = _token(msg["Body"])
            token = _token(ev["Token"])
            mid = self.msg_by_token.get(target)
            rid, flags = _reaction_id(msg["Info"], ev["Direction"], target, self.members_reactions)
            if mid is None:
                flags.append("orphan")
                self.stats["reactions_orphan"] += 1
            if "recovered_from_target" in flags:
                self.stats["reactions_recovered"] += 1
            if rid is None:
                self.stats["reactions_unreadable"] += 1
            reaction_key = ids.stable_id(key, "reaction", token or (ev["TimeStamp"], ev["SortOrder"], ev["Seq"]))
            before = self.arc.total_changes
            self.arc.execute(
                "INSERT OR IGNORE INTO reaction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (reaction_key, key, mid, target, "me" if ev["Direction"] == 1 else "peer", rid, ev["TimeStamp"],
                 ev["SortOrder"], _json(flags), self._raw(ev, msg), self.snap))
            if self.arc.total_changes > before:
                self.stats["reactions_created"] += 1
            self._lineage("reaction", reaction_key, ev["EventID"])

    def _contacts(self):
        for _cid, (name, number, client, raw) in self.ctx.contacts.items():
            key = number or f"noid:{ids.stable_id(name, client)}"
            self.arc.execute("INSERT OR IGNORE INTO contact VALUES (?,?,?,?,?)",
                             (key, name, client, _json(raw), self.snap))

    # -- main loop -----------------------------------------------------------------------------------------
    def run(self):
        event_sel = ", ".join(f"e.{c} AS e_{c}" for c in EVENT_COLS)
        msg_sel = ", ".join(f"m.{c} AS m_{c}" for c in MESSAGE_COLS)
        query = (f"SELECT {event_sel}, m.EventID AS m_EventID, {msg_sel} FROM Events e "
                 "LEFT JOIN Messages m ON m.EventID = e.EventID ORDER BY e.TimeStamp, e.SortOrder, e.Seq")
        count = 0
        for row in self.src.execute(query):
            ev = {c: row[f"e_{c}"] for c in EVENT_COLS}
            msg = None if row["m_EventID"] is None else {c: row[f"m_{c}"] for c in MESSAGE_COLS}
            self._handle(ev, msg)
            count += 1
            if count % BATCH == 0:
                self.arc.commit()
        self._attach_edits()
        self._renumber()
        self._store_reactions()
        self._contacts()


def import_pc(archive_path, export_db, source, label=None,  # pylint: disable=too-many-arguments,too-many-positional-arguments
              self_numbers=None, exclude_peers=()):
    """Import export_db into the archive. Returns a dict with the outcome and the counts."""
    if source not in ("pc-old", "pc-new"):
        raise ValueError("source must be pc-old or pc-new")
    sha = ids.file_sha256(export_db)
    arc = schema.connect(archive_path)
    known = arc.execute("SELECT id FROM source_snapshot WHERE sha256 = ?", (sha,)).fetchone()
    if known:
        arc.execute("INSERT INTO import_log(at_utc, snapshot_id, level, message) VALUES (?,?,?,?)",
                    (_now(), known[0], "info", "skipped: this exact export was already imported"))
        arc.commit()
        arc.close()
        return {"status": "already_imported", "snapshot_id": known[0]}
    src = _open_source(export_db)
    cur = arc.execute("INSERT INTO source_snapshot(source, label, path, sha256, imported_utc) VALUES (?,?,?,?,?)",
                      (source, label, str(export_db), sha, _now()))
    snap = cur.lastrowid
    ctx = Context(src, self_numbers, exclude_peers)
    importer = Importer(arc, src, snap, source, ctx)
    importer.run()
    stats = importer.stats
    arc.execute(
        "UPDATE source_snapshot SET first_event_ms=?, last_event_ms=?, events_total=?, content_total=?,"
        " reaction_total=?, standalone_total=?, excluded_events=?, excluded_messages=?, messages_created=?,"
        " edits_attached=?, edit_ref_missing=? WHERE id=?",
        (importer.first_ms, importer.last_ms, stats["events_total"], stats["content_total"],
         stats["reaction_total"], stats["standalone_total"], stats["excluded_events"], stats["excluded_messages"],
         stats["messages_created"], stats["edits_attached"], stats["edit_ref_missing"], snap))
    arc.execute("INSERT INTO import_log(at_utc, snapshot_id, level, message) VALUES (?,?,?,?)",
                (_now(), snap, "info", _json(stats)))
    arc.commit()
    arc.close()
    src.close()
    return {"status": "imported", "snapshot_id": snap, "self_found": len(ctx.self_ids), **stats}
