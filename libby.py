"""Libby availability via OverDrive's public 'thunder' API (the one libbyapp.com uses).

No login needed: it's the same catalogue anyone can browse in Libby.
"""
from urllib.parse import quote

from . import http
from .matching import authors_match, author_last, main_title, titles_match

BASE = "https://thunder.api.overdrive.com/v2/libraries/{key}"


def library_info(key):
    r = http.get(BASE.format(key=key), host_key="overdrive")
    if r.status_code != 200:
        return None
    return r.json()


def _creators(item):
    names = [c.get("name", "") for c in item.get("creators") or []]
    if item.get("firstCreatorName"):
        names.append(item["firstCreatorName"])
    return names


def _is_audiobook(item):
    t = (item.get("type") or {}).get("id", "")
    if t:
        return t == "audiobook"
    return any("audiobook" in (f.get("id") or "") for f in item.get("formats") or [])


def _search(key, query):
    r = http.get(
        BASE.format(key=key) + "/media",
        params={"query": query, "format": "audiobook-overdrive", "perPage": 24},
        host_key="overdrive",
    )
    if r.status_code != 200:
        raise RuntimeError(f"OverDrive search HTTP {r.status_code}")
    return r.json().get("items") or []


def find_audiobook(key, title, author):
    """Return the best-matching audiobook item from the library's catalogue, or None."""
    queries = [f"{main_title(title)} {author_last(author)}".strip(), main_title(title)]
    for q in dict.fromkeys(queries):  # de-dupe, keep order
        items = _search(key, q)
        for item in items:
            if not _is_audiobook(item):
                continue
            if titles_match(title, item.get("title", "")) and authors_match(author, _creators(item)):
                return item
    return None


def summarise(item, key, library_name):
    if item is None:
        return {"library": key, "library_name": library_name, "status": "not_owned",
                "search_url": f"https://libbyapp.com/search/{key}/search/page-1"}
    always = item.get("availabilityType") == "always"
    available = bool(item.get("isAvailable"))
    status = "always" if always else ("available" if available else "hold")
    return {
        "library": key,
        "library_name": library_name,
        "status": status,
        "media_id": str(item.get("id", "")),
        "url": f"https://libbyapp.com/library/{key}/everything/page-1/{item.get('id')}",
        "share_url": f"https://share.libbyapp.com/title/{item.get('id')}",
        "owned": item.get("ownedCopies"),
        "available_copies": item.get("availableCopies"),
        "holds": item.get("holdsCount"),
        "wait_days": item.get("estimatedWaitDays"),
        "narrators": [c.get("name") for c in item.get("creators") or []
                      if (c.get("role") or "").lower() == "narrator"],
    }


def check(key, library_name, title, author):
    item = find_audiobook(key, title, author)
    result = summarise(item, key, library_name)
    if item is None:
        result["search_url"] = (
            f"https://libbyapp.com/search/{key}/search/query-{quote(main_title(title))}/page-1"
        )
    return result
