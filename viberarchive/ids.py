"""Deterministic identifiers. Local ids (EventID, ChatID, ContactID) are never used as keys."""
import hashlib
import re


def stable_id(*parts):
    """24 hex chars derived only from the given parts, so a re-import yields the same id."""
    raw = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def digits(number):
    """Phone numbers compare as digits only: '+84 912 345' and '84912345' are the same."""
    return re.sub(r"\D", "", number or "")


def file_sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()
