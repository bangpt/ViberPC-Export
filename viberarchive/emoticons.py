"""Viber's text emoticons: the typed codes and the (name) forms are the same big picture in the app.

The archive keeps the text exactly as it was received. The viewer only changes how it is drawn: a message that is
nothing but an emoticon becomes a big picture (a PNG from --emoticons <folder> named <name>.png if you have one,
otherwise a standard emoji). Names and codes below are the common Viber set; extend EMOTICONS if one is missing.
"""
import re

# name: (typed codes, fallback emoji)
EMOTICONS = {
    "smiley": ((":)", ":-)", "=)"), "🙂"),
    "teeth": ((":D", ":-D", "=D"), "😁"),
    "sad": ((":(", ":-(", "=("), "🙁"),
    "wink": ((";)", ";-)"), "😉"),
    "tongue": ((":P", ":-P", ":p"), "😛"),
    "surprised": ((":O", ":-O", ":o"), "😮"),
    "cry": ((":'(",), "😢"),
    "neutral": ((":|", ":-|"), "😐"),
    "cool": (("B)", "B-)", "8)"), "😎"),
    "kiss": ((":*", ":-*"), "😘"),
    "heart": (("<3", "(heart)"), "❤️"),
}
_BY_TEXT = {}
for _name, (_codes, _emoji) in EMOTICONS.items():
    _BY_TEXT[f"({_name})"] = _name
    for _code in _codes:
        _BY_TEXT[_code] = _name
_NAME_RE = re.compile(r"\((\w+)\)")


def lookup(text):
    """Canonical name when the whole message is one emoticon (either spelling), else None."""
    text = (text or "").strip()
    found = _BY_TEXT.get(text)
    if found:
        return found
    named = _NAME_RE.fullmatch(text)
    return named.group(1).lower() if named and named.group(1).lower() in EMOTICONS else None


def emoji(name):
    """Fallback emoji for a canonical name."""
    return EMOTICONS[name][1]
