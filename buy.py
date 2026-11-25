"""Where to buy the audiobook: Audible price lookup + Libro.fm link."""
from urllib.parse import quote

from . import http
from .matching import authors_match, author_last, main_title, titles_match

AUDIBLE_API = "https://api.audible.com/1.0/catalog/products"


def audible_lookup(title, author):
    r = http.get(AUDIBLE_API, host_key="audible", min_interval=0.5, params={
        "title": main_title(title),
        "author": author,
        "num_results": 10,
        "products_sort_by": "Relevance",
        "response_groups": "contributors,product_attrs,price",
    })
    if r.status_code != 200:
        raise RuntimeError(f"Audible HTTP {r.status_code}")
    for p in r.json().get("products") or []:
        authors = [a.get("name", "") for a in p.get("authors") or []]
        if not titles_match(title, p.get("title", "")) or not authors_match(author, authors):
            continue
        price = p.get("price") or {}
        amount = None
        for k in ("lowest_price", "list_price"):
            if isinstance(price.get(k), dict) and price[k].get("base") is not None:
                amount = price[k]["base"]
                break
        asin = p.get("asin")
        return {
            "asin": asin,
            "price": amount,
            "currency": ((price.get("list_price") or {}).get("currency_code") or "USD"),
            "url": f"https://www.audible.com/pd/{asin}",
            "narrators": [n.get("name") for n in p.get("narrators") or []],
            "runtime_min": p.get("runtime_length_min"),
        }
    return None


def links(title, author):
    q = quote(f"{main_title(title)} {author_last(author)}".strip())
    return {
        "audible_search": f"https://www.audible.com/search?keywords={q}",
        "librofm_search": f"https://libro.fm/search?q={q}",
    }
