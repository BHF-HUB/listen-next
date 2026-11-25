"""Hoopla lookup.

Hoopla's partner API needs a library partner token, so this uses the same
GraphQL endpoint the hoopladigital.com website calls for its (logged-out)
search. That endpoint is undocumented and could change; when it fails we fall
back to a ready-made Hoopla search link, so the app keeps working.

Hoopla "Instant" titles never have a waitlist, so "found" means "borrow now"
(subject to your library's monthly borrow limit).
"""
from urllib.parse import quote

from . import http
from .matching import authors_match, author_last, main_title, titles_match

GRAPHQL = "https://patron-api-gateway.hoopladigital.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.hoopladigital.com",
    "Referer": "https://www.hoopladigital.com/",
    "apollographql-client-name": "hoopla-www",
    "app": "WWW",
    "device-version": "web",
}

# Tried in order; the first one the server accepts is remembered for the run.
QUERIES = [
    """query FilterSearch($criteria: SearchCriteria!) {
         search(criteria: $criteria) { found hits { id title artistName kind { name } } } }""",
    """query FilterSearch($criteria: SearchCriteria!) {
         search(criteria: $criteria) { found hits { id title kind { name } } } }""",
]

_working_query = None
_disabled_reason = None


def search_url(title, author):
    q = quote(f"{main_title(title)} {author_last(author)}".strip())
    return f"https://www.hoopladigital.com/search?q={q}&scope=everything&type=direct"


def _graphql_search(q):
    global _working_query, _disabled_reason
    candidates = [_working_query] if _working_query else QUERIES
    last_err = None
    for query in candidates:
        r = http.post(GRAPHQL, headers=HEADERS, host_key="hoopla", min_interval=0.6, json={
            "operationName": "FilterSearch",
            "query": query,
            "variables": {"criteria": {
                "q": q,
                "availability": "ALL_TITLES",
                "pagination": {"page": 1, "pageSize": 24},
            }},
        })
        if r.status_code != 200:
            last_err = f"HTTP {r.status_code}"
            continue
        body = r.json()
        if body.get("errors"):
            last_err = body["errors"][0].get("message", "GraphQL error")
            continue
        _working_query = query
        return ((body.get("data") or {}).get("search") or {}).get("hits") or []
    _disabled_reason = last_err
    raise RuntimeError(f"Hoopla search unavailable: {last_err}")


def check(title, author):
    link = search_url(title, author)
    if _disabled_reason:
        return {"status": "unknown", "search_url": link, "note": _disabled_reason}
    try:
        for q in dict.fromkeys([f"{main_title(title)} {author_last(author)}", main_title(title)]):
            for hit in _graphql_search(q):
                kind = ((hit.get("kind") or {}).get("name") or "").upper()
                if kind != "AUDIOBOOK":
                    continue
                artist = hit.get("artistName")
                if titles_match(title, hit.get("title", "")) and (
                        artist is None or authors_match(author, [artist])):
                    return {"status": "available", "title_id": str(hit.get("id")),
                            "url": f"https://www.hoopladigital.com/title/{hit.get('id')}"}
        return {"status": "not_found", "search_url": link}
    except Exception as e:  # network or schema change — degrade to a link
        return {"status": "unknown", "search_url": link, "note": str(e)[:160]}
