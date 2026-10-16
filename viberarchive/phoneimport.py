"""Import the phone's Viber database (``viber_messages``) into the archive.

The phone table ``messages`` carries the same message tokens as the PC export, so the two sources are joined by
token and no guessing by text or time is needed. What is different:

  * ``msg_date`` is the delivery time. The PC ``TimeStamp`` is the composed time, so for a message that is
    already in the archive from the PC the phone time is only stored as ``sent_ms``. For a message that exists
    only on the phone, ``composed_ms`` is the delivery time and the row is flagged ``time_is_delivery``.
  * A row is a reaction record when its ``msg_info`` holds ``1on1reactions`` (same meaning as PC Events.Type 3).
  * The phone keeps no usable tick status, so outgoing messages that only the phone has get tick ``unknown``
    (flag ``tick_unknown``). Messages that the PC also has keep the PC tick.
  * ``extra_mime`` maps to the PC message type: 0 text, 1 image, 3 video, 4 sticker, 8 link, 10 file.
    Values from 1000 up are system records; they become standalone events unless the archive already has them.
  * Conversations are tied to archive chats by the tokens they share, so local conversation ids never matter.

The PC export must be imported first, because it holds the composed times. Importing the same file twice
changes nothing.
"""
import json
import re
import shutil
import sqlite3
from collections import Counter
from pathlib import Path

from viberkit import enrich

from . import ids, pcimport, schema
from .pcimport import _json, _now, _token

SOURCE = "phone-db"
MIME_TO_TYPE = {0: 1, 1: 2, 3: 3, 4: 4, 8: 9, 10: 11}
FILE_MIMES = {1, 3, 10}
SYSTEM_MIME = 1000
MIN_PURITY = 0.9
DELAY_MS = 60_000           # a phone time this much later than the PC time is a delivery delay
EARLY_MS = 5_000            # a phone time this much earlier is reported as odd
EXCLUDED = "excluded:by-token"


def _row_dict(row):
    out = {}
    for key in row.keys():  # pylint: disable=consider-using-dict-items
        value = row[key]
        out[key] = value.hex() if isinstance(value, (bytes, bytearray)) else value
    return out


def _info(raw):
    try:
        parsed = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_reaction(info):
    return isinstance(info.get("1on1reactions"), dict)


def _quote_token(info, quoted_raw):
    quote = info.get("quote")
    token = _token(quote.get("token")) if isinstance(quote, dict) else None
    if token is None:
        token = _token(_info(quoted_raw).get("token"))
    return token


class PhoneContext:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Chats and authors of the phone database, resolved without using any local id as a key."""

    def __init__(self, phone, arc, self_numbers, exclude_peers):
        infos = {r["_id"]: r for r in phone.execute("SELECT * FROM participants_info")}
        self.infos = infos
        self.parts = {r["_id"]: r for r in phone.execute("SELECT * FROM participants")}
        members = {}
        for part in self.parts.values():
            info = infos.get(part["participant_info_id"])
            if info is not None:
                members.setdefault(part["conversation_id"], []).append(self._number(info))
        self.members = members
        self.convs = {r["_id"]: r for r in phone.execute("SELECT * FROM conversations")}
        tokens_of = {}
        for conv_id, token in phone.execute("SELECT conversation_id, token FROM messages WHERE token > 0"):
            tokens_of.setdefault(conv_id, []).append(str(token))
        explicit = {ids.digits(n) for n in self_numbers or [] if ids.digits(n)}
        self.self_numbers = explicit or self._infer_self(tokens_of)
        self.exclude = {f"direct:{ids.digits(p)}" for p in exclude_peers}
        archive_chat = dict(arc.execute("SELECT token, chat_key FROM message WHERE token IS NOT NULL"))
        archive_chat.update((t, EXCLUDED) for (t,) in arc.execute("SELECT token FROM excluded_token"))
        self.exclude.add(EXCLUDED)
        self.excluded_convs = set()
        self.chat_of = {}
        self.matched = {}
        for conv_id, tokens in tokens_of.items():
            self.chat_of[conv_id] = self._resolve(conv_id, tokens, archive_chat, arc)
        self.used_numbers = {n for conv_id in tokens_of if conv_id not in self.excluded_convs
                             for n in self.members.get(conv_id, [])}

    @staticmethod
    def _number(info):
        return ids.digits(info["number"]) or f"noid:{ids.stable_id(info['_id'], info['display_name'])}"

    def _infer_self(self, _tokens_of):
        """You are the one number that sits in (almost) every conversation that has two or more members."""
        lists = [set(m) for m in self.members.values() if len(set(m)) >= 2]
        if len(lists) < 3:
            return set()
        counts = Counter(n for members in lists for n in members)
        number, hits = counts.most_common(1)[0]
        return {number} if hits >= 0.8 * len(lists) else set()

    def _resolve(self, conv_id, tokens, archive_chat, arc):
        votes = Counter(archive_chat[t] for t in tokens if t in archive_chat)
        if votes:
            key, hits = votes.most_common(1)[0]
            if hits / sum(votes.values()) >= MIN_PURITY and key == EXCLUDED:
                self.excluded_convs.add(conv_id)
                return EXCLUDED, "excluded", "", []
            if hits / sum(votes.values()) >= MIN_PURITY:
                row = arc.execute("SELECT kind, title, peers_json FROM chat WHERE chat_key = ?", (key,)).fetchone()
                self.matched[conv_id] = key
                return key, row[0], row[1], json.loads(row[2] or "[]")
        peers = sorted(set(self.members.get(conv_id, [])) - self.self_numbers)
        conv = self.convs.get(conv_id)
        title = (conv["name"] if conv is not None else None) or ""
        if len(peers) == 1:
            return f"direct:{peers[0]}", "direct", title, peers
        if len(peers) > 1:
            return f"group:{ids.stable_id(*peers)[:12]}", "group", title, peers
        return f"unmapped:phone{conv_id}", "unmapped", title, []

    def chat(self, chat_id, _contact_id, _direction):
        return self.chat_of.get(chat_id) or (f"unmapped:phone{chat_id}", "unmapped", "", [])

    def author(self, contact_id, direction):
        return "self" if direction == 1 else (contact_id or None)

    def sender_number(self, row):
        """Digits of the sender of an incoming row; the sole peer is used when the id cannot be resolved."""
        part = self.parts.get(row["participant_id"])
        info = self.infos.get(part["participant_info_id"]) if part is not None else None
        if info is not None:
            return self._number(info)
        peers = sorted(set(self.members.get(row["conversation_id"], [])) - self.self_numbers)
        return peers[0] if len(peers) == 1 else None


class PhoneImporter(pcimport.Importer):
    """The PC importer, fed with phone rows. See the module docstring for the differences."""

    def __init__(self, arc, src, snapshot_id, ctx, run_id=None):  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self.run_id = run_id
        self.found = Counter()
        self.known = dict(arc.execute("SELECT token, id FROM message WHERE token IS NOT NULL"))
        self.known_chat = dict(arc.execute("SELECT id, chat_key FROM message"))
        self.standalone_tokens = {str(t) for (t,) in arc.execute(
            "SELECT json_extract(raw_json, '$.Events.Token') FROM standalone_event") if t is not None}
        super().__init__(arc, src, snapshot_id, SOURCE, ctx)
        self.msg_by_token.update(self.known)
        self.stats.update(merged=0, sent_time_set=0, chat_mismatch=0, skipped_system=0, phone_only_unticked=0)

    # -- scanning ----------------------------------------------------------------------------------------------
    def _scan(self, src):
        edit_of = {}
        all_tokens = set(self.known)
        for token, raw in src.execute("SELECT token, msg_info FROM messages WHERE token > 0"):
            info = _info(raw)
            if _is_reaction(info):
                continue
            token = _token(token)
            all_tokens.add(token)
            edit = info.get("edit")
            if isinstance(edit, dict) and _token(edit.get("token")):
                edit_of[token] = _token(edit["token"])
        return edit_of, all_tokens, {}

    # -- row translation ---------------------------------------------------------------------------------------
    def _translate(self, row):
        info = _info(row["msg_info"])
        mime = row["extra_mime"] or 0
        reaction = _is_reaction(info)
        direction = 1 if row["send_type"] == 1 else 0
        token = _token(row["token"]) if row["token"] and row["token"] > 0 else None
        ev = {"EventID": row["_id"], "Type": 3 if reaction else 0, "TimeStamp": row["msg_date"],
              "Direction": direction, "ChatID": row["conversation_id"],
              "ContactID": None if direction == 1 else self.ctx.sender_number(row), "Token": token,
              "SortOrder": row["order_key"], "Seq": row["seq"] or 0, "_row": _row_dict(row)}
        body = row["body"]
        if reaction:
            # The phone's body is the emoji code; the token of the message reacted to is in quote.token.
            body = _quote_token(info, row["quoted_message_data"])
        msg = {"Type": MIME_TO_TYPE.get(mime, mime), "Subject": None, "Body": body,
               "PayloadPath": (row["extra_uri"] or "") if mime in FILE_MIMES else "", "ThumbnailPath": "",
               "StickerID": row["sticker_id"] if mime == 4 else None, "Duration": row["extra_duration"],
               "Info": row["msg_info"], "PGIsLiked": None, "PGLikeCount": None, "SelfReaction": None,
               "MembersReactions": None, "AdminsReactions": None, "Status": None}
        system = mime >= SYSTEM_MIME and not reaction and token not in self.known
        return ev, msg, system

    def _raw(self, ev, msg):  # pylint: disable=unused-argument
        return _json({"Phone": ev["_row"]})

    # -- merging with what the PC already gave -----------------------------------------------------------------
    def _content(self, ev, msg, key):
        token = _token(ev["Token"])
        mid = self.known.get(token) if token else None
        if mid is None or pcimport._resolve_original(token, self.edit_of, self.all_tokens) is not None:  # pylint: disable=protected-access
            super()._content(ev, msg, key)
            return
        self.stats["merged"] += 1
        if self.known_chat.get(mid) != key:
            self.stats["chat_mismatch"] += 1
        before = self.arc.total_changes
        self.arc.execute(
            "UPDATE message SET sent_ms = ? WHERE id = ? AND sent_ms IS NULL AND composed_ms <> ?",
            (ev["TimeStamp"], mid, ev["TimeStamp"]))
        if self.arc.total_changes > before:
            self.stats["sent_time_set"] += 1
        self._lineage("message", mid, ev["EventID"])
        self._compare(mid, ev, msg)

    # -- differences between the two sources for the same message ----------------------------------------------
    def _finding(self, kind, mid, detail):
        self.found[kind] += 1
        if self.run_id is not None:
            self.arc.execute("INSERT INTO recon_finding(run_id, kind, message_id, detail_json) VALUES (?,?,?,?)",
                             (self.run_id, kind, mid, _json(detail)))

    def _compare(self, mid, ev, msg):  # pylint: disable=too-many-locals
        row = self.arc.execute(
            "SELECT m.author, m.composed_ms, m.direction, v.kind, v.text FROM message m JOIN message_version v"
            " ON v.message_id = m.id AND v.version = 0 WHERE m.id = ?", (mid,)).fetchone()
        if row is None:
            return
        author, composed, direction, kind, text = row
        desc = enrich.describe(dict(msg))
        if desc["kind"] != kind:
            self._finding("kind_diff", mid, {"pc": kind, "phone": desc["kind"]})
        elif kind == "text":
            phone_text = re.sub(r"\s+", " ", (msg["Body"] or "")).strip()
            if re.sub(r"\s+", " ", text or "").strip() != phone_text:
                self._finding("text_diff", mid, {"pc": text, "phone": msg["Body"]})
        if direction == "in" and author and ev["ContactID"] and author != ev["ContactID"]:
            self._finding("sender_diff", mid, {"pc": author, "phone": ev["ContactID"]})
        delta = ev["TimeStamp"] - composed
        if delta > DELAY_MS:
            self._finding("delivery_delay", mid, {"seconds": delta // 1000, "direction": direction})
        elif delta < -EARLY_MS:
            self._finding("time_early", mid, {"seconds": delta // 1000, "direction": direction})

    def finish(self):
        super().finish()
        self._check_reactions()
        self.stats.update({f"found_{k}": v for k, v in sorted(self.found.items())})

    def _check_reactions(self):
        """Compare the phone's own reaction columns with the reactions the archive ended up with."""
        effective = {(m, r): rid for m, r, rid in self.arc.execute(
            "SELECT message_id, reactor, reaction_id FROM reaction_effective")}
        for token, mine, likes in self.src.execute(
                "SELECT token, my_reaction, likes_count FROM messages"
                " WHERE token > 0 AND (my_reaction > 0 OR likes_count > 0)"):
            mid = self.msg_by_token.get(_token(token))
            if mid is None:
                continue
            got_me = effective.get((mid, "me"), 0)
            if got_me != (mine or 0):
                self._finding("reaction_disagree", mid, {"side": "me", "phone": mine, "archive": got_me})
            if likes and not mine and (mid, "peer") not in effective:
                self._finding("reaction_disagree", mid, {"side": "peer_missing", "phone_likes": likes})

    def _insert_message(self, ev, msg, key, token, flags):
        mid = super()._insert_message(ev, msg, key, token, flags + ["time_is_delivery"])
        row = self.arc.execute("SELECT first_snapshot, direction, flags FROM message WHERE id = ?", (mid,)).fetchone()
        if row[0] == self.snap and row[1] == "out":
            self.stats["phone_only_unticked"] += 1
            self.arc.execute("UPDATE message SET tick = 'unknown', flags = ? WHERE id = ?",
                             (_json(json.loads(row[2]) + ["tick_unknown"]), mid))
        return mid

    # -- main loop ---------------------------------------------------------------------------------------------
    def run(self):
        self.src.row_factory = sqlite3.Row
        count = 0
        for row in self.src.execute("SELECT * FROM messages ORDER BY msg_date, order_key, seq, _id"):
            ev, msg, system = self._translate(row)
            if system:
                token = ev["Token"]
                if token is not None and token in self.standalone_tokens:
                    self.stats["skipped_system"] += 1
                    continue
                msg = None
            self._handle(ev, msg)
            count += 1
            if count % pcimport.BATCH == 0:
                self.arc.commit()
        self.finish()

    def _contacts(self):
        for number in sorted(self.ctx.used_numbers - self.ctx.self_numbers):
            info = next((i for i in self.ctx.infos.values() if self.ctx._number(i) == number), None)  # pylint: disable=protected-access
            if info is None:
                continue
            name = info["contact_name"] or info["display_name"] or info["viber_name"]
            raw = {k: info[k] for k in ("number", "display_name", "contact_name", "viber_name", "viber_id")}
            self.arc.execute("INSERT OR IGNORE INTO contact VALUES (?,?,?,?,?)",
                             (number, name, None, _json(raw), self.snap))


def import_phone_db(archive_path, phone_db, label=None,  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
                    self_numbers=None, exclude_peers=(), copy_to=None):
    """Import the phone's messages database into an archive that already holds the PC export."""
    arc = schema.connect(archive_path)
    if not arc.execute("SELECT 1 FROM source_snapshot WHERE source LIKE 'pc-%'").fetchone():
        arc.close()
        raise ValueError("Import the PC export first: it holds the composed times the phone does not have.")
    sha = ids.file_sha256(phone_db)
    known = arc.execute("SELECT id FROM source_snapshot WHERE sha256 = ?", (sha,)).fetchone()
    if known:
        arc.close()
        return {"status": "already_imported", "snapshot_id": known[0]}
    kept = None
    if copy_to:
        target = Path(copy_to) / f"phone-db-{sha[:8]}"
        target.mkdir(parents=True, exist_ok=True)
        kept = target / Path(phone_db).name
        if not kept.exists():
            shutil.copy2(phone_db, kept)
    src = pcimport._open_source(phone_db)  # pylint: disable=protected-access
    cur = arc.execute("INSERT INTO source_snapshot(source, label, path, sha256, imported_utc) VALUES (?,?,?,?,?)",
                      (SOURCE, label, str(phone_db), sha, _now()))
    snap = cur.lastrowid
    run_id = arc.execute("INSERT INTO recon_run(started_utc, params_json) VALUES (?,?)",
                         (_now(), _json({"kind": "phone-import", "snapshot": snap}))).lastrowid
    ctx = PhoneContext(src, arc, self_numbers, exclude_peers)
    importer = PhoneImporter(arc, src, snap, ctx, run_id)
    stats = pcimport.run_import(importer)
    arc = schema.connect(archive_path)
    arc.execute("UPDATE recon_run SET finished_utc = ? WHERE id = ?", (_now(), run_id))
    arc.commit()
    arc.close()
    return {"status": "imported", "snapshot_id": snap, "conversations": len(ctx.chat_of),
            "conversations_matched": len(ctx.matched), "conversations_excluded": len(ctx.excluded_convs),
            "self_found": len(ctx.self_numbers), "copy": str(kept) if kept else None, **stats}
