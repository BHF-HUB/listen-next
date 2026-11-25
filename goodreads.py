"""Read Goodreads shelves from the public shelf web pages.

Goodreads closed its API in 2020 and retired shelf RSS feeds in November 2026,
so this reads the same page you see at
    https://www.goodreads.com/review/list/<user id>?shelf=to-read
one page at a time (?page=1,2,3...) until a page adds nothing new.

Works for profiles visible to "anyone". For a private profile, use the
Goodreads export CSV instead (see README).
"""
import csv
import re

from bs4 import BeautifulSoup

from . import http

LIST_URL = "https://www.goodreads.com/review/list/{uid}"
BASE = "https://www.goodreads.com"
MAX_PAGES = 30
PER_PAGE = 100

RATING_WORDS = {
    "did not like it": 1, "it was ok": 2, "liked it": 3,
    "really liked it": 4, "it was amazing": 5,
}


class GoodreadsError(Exception):
    pass


def _clean(s):
    return " ".join((s or "").split())


def _flip_author(name):
    """Shelf pages list authors as 'Corey, James S.A.' -> 'James S.A. Corey'."""
    name = _clean(name).rstrip("*").strip()
    if name.count(",") == 1:
        last, first = [p.strip() for p in name.split(",")]
        if first and last:
            return f"{first} {last}"
    return name


def _bigger_cover(src):
    """'.../12345._SY75_.jpg' -> '.../12345.jpg' (full-size cover)."""
    if not src or "nophoto" in src:
        return ""
    return re.sub(r"\._[A-Z0-9_,]+_(?=\.\w+$)", "", src)


def _field(tr, name):
    return tr.select_one(f"td.field.{name}")


def _value_text(tr, name):
    td = _field(tr, name)
    if not td:
        return ""
    v = td.select_one(".value") or td
    return _clean(v.get_text(" "))


def _rating(tr):
    td = _field(tr, "rating")
    if not td:
        return 0
    stars = td.select_one(".staticStars")
    if stars is not None:
        word = (stars.get("title") or "").strip().lower()
        if word in RATING_WORDS:
            return RATING_WORDS[word]
        # Star icons: p10 = full star, p5 = half star (half-stars arrived Oct 2026)
        full = len(stars.select(".staticStar.p10"))
        half = len(stars.select(".staticStar.p5"))
        if full or half:
            return full + 0.5 * half
    m = re.search(r"(\d(?:\.5)?)\s*(?:of 5|stars?)", td.get_text(" "), re.I)
    return float(m.group(1)) if m else 0


def _review_text(tr):
    td = _field(tr, "review")
    if not td:
        return ""
    # Goodreads puts the full text in a hidden span id="freeText<review id>",
    # and a truncated copy in id="freeTextContainer<review id>".
    full = [s for s in td.select("span[id^=freeText]") if not s["id"].startswith("freeTextContainer")]
    node = full[0] if full else (td.select("span")[-1] if td.select("span") else td.select_one(".value"))
    if node is None:
        return ""
    for br in node.find_all("br"):
        br.replace_with("\n")
    text = node.get_text().strip()
    text = re.sub(r"\s*\.\.\.more\s*$|\s*\(less\)\s*$", "", text)
    if text.lower() in ("write a review", "none"):
        return ""
    return text


def _date(tr, name):
    td = _field(tr, name)
    if not td:
        return ""
    span = td.select_one("span[title]")
    if span is not None and span.get("title"):
        return span["title"].strip()
    return _clean((td.select_one(".value") or td).get_text(" ")).replace("not set", "").strip()


def parse_shelf_page(html_text):
    """Return (owner_name, [book dicts]) from one shelf page."""
    soup = BeautifulSoup(html_text, "html.parser")
    rows = soup.select("table#books tr.review") or soup.select("table#books tr[id^=review_]")
    if not rows and soup.select_one("table#books") is None:
        page = soup.get_text(" ").lower()
        if "private" in page or "sign in" in page or "sign up" in page:
            raise GoodreadsError("Goodreads wouldn't show this shelf without signing in. "
                                 "Is the profile set to be visible to anyone?")
        raise GoodreadsError("Couldn't find the book table on the Goodreads shelf page "
                             "(Goodreads may have changed its page layout).")
    owner = ""
    title_tag = soup.find("title")
    if title_tag:
        m = re.match(r"\s*(.+?)[’']s?\s", title_tag.get_text())
        owner = m.group(1).strip() if m else ""

    books = []
    for tr in rows:
        link = None
        td_title = _field(tr, "title")
        if td_title:
            link = td_title.select_one("a[href*='/book/show/']")
        if link is None:
            continue
        m = re.search(r"/book/show/(\d+)", link.get("href", ""))
        if not m:
            continue
        title = _clean(link.get("title") or link.get_text(" "))
        td_author = _field(tr, "author")
        a = td_author.select_one("a") if td_author else None
        img = tr.select_one("td.field.cover img")
        review_id = (tr.get("id") or "").replace("review_", "")
        books.append({
            "goodreads_id": m.group(1),
            "title": title,
            "author": _flip_author(a.get_text(" ") if a else ""),
            "isbn": _value_text(tr, "isbn13") or _value_text(tr, "isbn"),
            "cover": _bigger_cover(img.get("src") if img else ""),
            "date_added": _date(tr, "date_added"),
            "avg_rating": _value_text(tr, "avg_rating"),
            "year": _value_text(tr, "date_pub"),
            "pages": _value_text(tr, "num_pages").replace("pp", "").strip(),
            "user_rating": _rating(tr),
            "user_review": _review_text(tr),
            "read_at": _date(tr, "date_read"),
            "review_url": f"{BASE}/review/show/{review_id}" if review_id.isdigit() else "",
        })
    return owner, books


def fetch_shelf(user_id, shelf, max_pages=MAX_PAGES):
    """All books on a shelf. Returns (owner_name_guess, books)."""
    seen, books, owner = set(), [], ""
    for page in range(1, max_pages + 1):
        r = http.get(LIST_URL.format(uid=user_id), host_key="goodreads", min_interval=1.5,
                     params={"shelf": shelf, "page": page, "per_page": PER_PAGE,
                             "sort": "date_added", "order": "d"})
        if r.status_code == 404:
            raise GoodreadsError(f"Goodreads user {user_id} not found.")
        if r.status_code != 200:
            raise GoodreadsError(f"Goodreads shelf page returned HTTP {r.status_code} for user {user_id}.")
        name, page_books = parse_shelf_page(r.text)
        owner = owner or name
        new = [b for b in page_books if b["goodreads_id"] not in seen]
        for b in new:
            seen.add(b["goodreads_id"])
        books.extend(new)
        if not new:
            break
    return owner, books


def load_export_csv(path, shelf="to-read"):
    """Fallback: Goodreads 'Export Library' CSV (My Books → Import and export)."""
    books = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("Exclusive Shelf") or "").strip() != shelf:
                continue
            isbn = (row.get("ISBN13") or row.get("ISBN") or "").strip('="')
            books.append({
                "goodreads_id": row.get("Book Id", "").strip(),
                "title": row.get("Title", "").strip(),
                "author": row.get("Author", "").strip(),
                "isbn": isbn,
                "cover": "",
                "date_added": row.get("Date Added", ""),
                "avg_rating": row.get("Average Rating", ""),
                "year": row.get("Original Publication Year", ""),
                "pages": row.get("Number of Pages", ""),
            })
    return books
