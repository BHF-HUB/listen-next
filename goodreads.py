"""Read Goodreads shelves via their public RSS feeds (the official API is closed).

Each RSS page holds up to 100 books, so we walk ?page=1,2,3... until a page
adds nothing new.
"""
import csv
import html
import re
import xml.etree.ElementTree as ET

from . import http

RSS_URL = "https://www.goodreads.com/review/list_rss/{uid}"
MAX_PAGES = 30


class GoodreadsError(Exception):
    pass


def _text(item, tag):
    el = item.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


def _strip_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def parse_rss(xml_text):
    """Return (channel_title, [book dicts]) from one RSS page."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise GoodreadsError(f"Goodreads returned something that isn't RSS ({e}). "
                             "Is the profile public?") from e
    channel = root.find("channel")
    if channel is None:
        raise GoodreadsError("Goodreads RSS had no <channel>.")
    books = []
    for item in channel.findall("item"):
        book_el = item.find("book")
        pages = ""
        if book_el is not None:
            np_el = book_el.find("num_pages")
            pages = (np_el.text or "").strip() if np_el is not None and np_el.text else ""
        cover = _text(item, "book_large_image_url") or _text(item, "book_image_url")
        books.append({
            "goodreads_id": _text(item, "book_id"),
            "title": html.unescape(_text(item, "title")),
            "author": html.unescape(_text(item, "author_name")),
            "isbn": _text(item, "isbn"),
            "cover": cover,
            "date_added": _text(item, "user_date_added"),
            "avg_rating": _text(item, "average_rating"),
            "year": _text(item, "book_published"),
            "pages": pages,
            "user_rating": _text(item, "user_rating"),
            "user_review": _strip_html(_text(item, "user_review")),
            "read_at": _text(item, "user_read_at"),
            "review_url": _text(item, "link").split("?")[0],
        })
    return _text(channel, "title"), books


def fetch_shelf(user_id, shelf, rss_key="", max_pages=MAX_PAGES):
    """All books on a shelf. Returns (owner_name_guess, books)."""
    seen, books, owner = set(), [], ""
    for page in range(1, max_pages + 1):
        params = {"shelf": shelf, "page": page}
        if rss_key:
            params["key"] = rss_key
        r = http.get(RSS_URL.format(uid=user_id), params=params,
                     host_key="goodreads", min_interval=1.0)
        if r.status_code == 404:
            raise GoodreadsError(f"Goodreads user {user_id} not found.")
        if r.status_code != 200:
            raise GoodreadsError(f"Goodreads RSS returned HTTP {r.status_code} for user {user_id}.")
        title, page_books = parse_rss(r.text)
        if page == 1:
            # "Jane's bookshelf: read" -> "Jane"
            owner = re.sub(r"[’']s bookshelf.*$", "", title).strip()
        new = [b for b in page_books if b["goodreads_id"] and b["goodreads_id"] not in seen]
        for b in new:
            seen.add(b["goodreads_id"])
        books.extend(new)
        if not new or len(page_books) < 100:
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
