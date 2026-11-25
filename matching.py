"""Title/author normalisation so the same book matches across services."""
import html
import re
import unicodedata

_SERIES_SUFFIX = re.compile(r"\s*\([^()]*#\s*[\d.]+[^()]*\)\s*$")  # "(The Expanse, #1)"
_ANY_PAREN_SUFFIX = re.compile(r"\s*\([^()]*\)\s*$")
_SUBTITLE = re.compile(r"\s*[:—–]\s.*$|\s*:\s*.*$")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_ARTICLES = re.compile(r"^(the|a|an) ")
_AUDIO_NOISE = re.compile(
    r"\b(unabridged|abridged|a novel|audiobook|audio edition|dramatized)\b"
)


def _ascii(s):
    s = html.unescape(s or "")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def strip_series(title):
    """'Leviathan Wakes (The Expanse, #1)' -> 'Leviathan Wakes'."""
    t = _SERIES_SUFFIX.sub("", title or "")
    return t.strip()


def main_title(title):
    """Drop series suffix and subtitle: 'Educated: A Memoir' -> 'Educated'."""
    t = strip_series(title)
    t = _ANY_PAREN_SUFFIX.sub("", t)
    t = _SUBTITLE.sub("", t)
    return t.strip()


def norm_title(title):
    t = _ascii(main_title(title)).lower().replace("&", " and ")
    t = _NON_ALNUM.sub(" ", t)
    t = _AUDIO_NOISE.sub(" ", t)
    t = " ".join(t.split())
    return _ARTICLES.sub("", t)


def author_last(name):
    n = _ascii(name).lower()
    n = re.sub(r"\b(jr|sr|ii|iii|phd|md)\b\.?", "", n)
    n = _NON_ALNUM.sub(" ", n)
    parts = n.split()
    return parts[-1] if parts else ""


def titles_match(a, b):
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Allow one to be a prefix of the other when the shorter one is substantial
    short, long_ = sorted((na, nb), key=len)
    return len(short) >= 8 and long_.startswith(short)


def authors_match(wanted, candidates):
    """wanted: a single author name. candidates: list of names from the other service."""
    w = author_last(wanted)
    if not w:
        return True  # nothing to compare — don't block on it
    return any(author_last(c) == w for c in candidates if c)


def book_key(title, author):
    return f"{norm_title(title)}|{author_last(author)}"
