"""Offline tests: every network call is faked, so these run anywhere.

    python -m unittest discover tests
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sync import __main__ as runner
from sync import goodreads, http, libby, matching

STARS = {0: "", 1: "did not like it", 2: "it was ok", 3: "liked it",
         4: "really liked it", 5: "it was amazing"}
PAGE_TEMPLATE = """<!DOCTYPE html><html><head><title>{owner}’s {shelf} books on Goodreads ({n} books)</title></head>
<body><table id="books" class="table stacked"><thead><tr><th>cover</th></tr></thead><tbody id="booksBody">{rows}</tbody></table></body></html>"""
ROW = """<tr id="review_{rid}" class="bookalike review">
<td class="field cover"><div class="value"><a href="/book/show/{bid}-x"><img alt="{title}" src="https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/books/1/{bid}._SY75_.jpg"></a></div></td>
<td class="field title"><label>title</label><div class="value"><a title="{title}" href="/book/show/{bid}-slug">{title}</a></div></td>
<td class="field author"><label>author</label><div class="value"><a href="/author/show/1.x">{author_lf}</a>*</div></td>
<td class="field isbn"><label>isbn</label><div class="value">9780000000{bid}</div></td>
<td class="field avg_rating"><label>avg rating</label><div class="value">4.12</div></td>
<td class="field rating"><label>Betsy's rating</label><div class="value">{stars}</div></td>
<td class="field review"><label>review</label><div class="value">{review}</div></td>
<td class="field date_read"><label>date read</label><div class="value"><span class="date_read_value">Oct 01, 2026</span></div></td>
<td class="field date_added"><label>date added</label><div class="value"><span title="November 3, 2026">Nov 03, 2026</span></div></td>
</tr>"""


def stars_html(r):
    if not r:
        return '<span class=" staticStars notranslate"></span>'
    if r != int(r):  # half-star rating, no text title
        icons = '<span class="staticStar p10"></span>' * int(r) + '<span class="staticStar p5"></span>'
        return f'<span class=" staticStars notranslate">{icons}</span>'
    return f'<span class=" staticStars notranslate" title="{STARS[int(r)]}"></span>'


def review_html(rid, text):
    if not text:
        return '<a href="/review/edit/1">Write a review</a>'
    return (f'<span id="freeTextContainer{rid}">{text[:20]}</span>'
            f'<span id="freeText{rid}" style="display:none">{text}</span>')


def lf(name):  # "Andy Weir" -> "Weir, Andy"
    first, _, last = name.rpartition(" ")
    return f"{last}, {first}" if first else name


def page(owner, shelf, books):
    rows = "".join(ROW.format(rid=1000 + i, bid=b[0], title=b[1], author_lf=lf(b[2]),
                              stars=stars_html(b[3] if len(b) > 3 else 0),
                              review=review_html(1000 + i, b[4] if len(b) > 4 else ""))
                   for i, b in enumerate(books))
    return PAGE_TEMPLATE.format(owner=owner, shelf=shelf, n=len(books), rows=rows)


MY_SHELF = [
    ("1", "Leviathan Wakes (The Expanse, #1)", "James S.A. Corey"),
    ("2", "Educated: A Memoir", "Tara Westover"),
    ("3", "Some Obscure Small Press Book", "Nobody Known"),
    ("4", "Project Hail Mary", "Andy Weir"),
]
FRIEND_SHELF = [
    ("999", "Educated", "Tara Westover", 5, "Couldn't put it down.<br/>Read it!"),  # other edition
    ("4", "Project Hail Mary", "Andy Weir", 4.5, ""),
]

OD_ITEMS = {
    "Leviathan Wakes": [{"id": 101, "title": "Leviathan Wakes", "type": {"id": "audiobook"},
                         "creators": [{"name": "James S. A. Corey", "role": "Author"},
                                      {"name": "Jefferson Mays", "role": "Narrator"}],
                         "isAvailable": True, "ownedCopies": 3, "availableCopies": 1, "holdsCount": 0}],
    "Educated": [{"id": 202, "title": "Educated", "subtitle": "A Memoir", "type": {"id": "ebook"},
                  "creators": [{"name": "Tara Westover", "role": "Author"}], "isAvailable": True},
                 {"id": 203, "title": "Educated", "type": {"id": "audiobook"},
                  "creators": [{"name": "Tara Westover", "role": "Author"}], "isAvailable": False,
                  "ownedCopies": 10, "availableCopies": 0, "holdsCount": 42, "estimatedWaitDays": 35}],
    "Project Hail Mary": [{"id": 404, "title": "Project Hail Mary", "type": {"id": "audiobook"},
                           "creators": [{"name": "Andy Weir"}], "availabilityType": "always",
                           "isAvailable": True}],
}


class FakeResp:
    def __init__(self, status=200, text="", payload=None):
        self.status_code, self.text, self._p = status, text, payload

    def json(self):
        return self._p if self._p is not None else json.loads(self.text)


def fake_get(url, host_key=None, min_interval=0, params=None, **kw):
    params = params or {}
    if "goodreads.com/review/list/" in url:
        if params.get("page", 1) > 1:   # Goodreads repeats/ends; we stop when nothing new
            return FakeResp(text=page("x", "x", []))
        if url.endswith("/555"):
            return FakeResp(text=page("Sam", "read", FRIEND_SHELF))
        return FakeResp(text=page("Betsy", "to-read", MY_SHELF))
    if "thunder.api.overdrive.com" in url:
        q = params.get("query", "")
        for k, items in OD_ITEMS.items():
            if q.startswith(k):
                return FakeResp(payload={"items": items})
        return FakeResp(payload={"items": []})
    if "api.audible.com" in url:
        if params.get("title") == "Some Obscure Small Press Book":
            return FakeResp(payload={"products": []})
        return FakeResp(payload={"products": [{
            "asin": "B0TEST" + params["title"][:2].upper(), "title": params["title"],
            "authors": [{"name": params["author"]}], "narrators": [{"name": "Reader"}],
            "price": {"list_price": {"base": 24.95, "currency_code": "USD"},
                      "lowest_price": {"base": 17.47}}}]})
    raise AssertionError("unexpected GET " + url)


def fake_post(url, host_key=None, min_interval=0, json=None, **kw):
    if "hoopladigital" in url:
        q = json["variables"]["criteria"]["q"]
        if q.startswith("Leviathan"):
            return FakeResp(payload={"data": {"search": {"found": 1, "hits": [
                {"id": 777, "title": "Leviathan Wakes", "artistName": "James S. A. Corey",
                 "kind": {"name": "AUDIOBOOK"}}]}}})
        return FakeResp(payload={"data": {"search": {"found": 0, "hits": []}}})
    if "ntfy.sh" in url:
        return FakeResp()
    raise AssertionError("unexpected POST " + url)


class Matching(unittest.TestCase):
    def test_titles(self):
        self.assertEqual(matching.strip_series("Leviathan Wakes (The Expanse, #1)"), "Leviathan Wakes")
        self.assertEqual(matching.main_title("Educated: A Memoir"), "Educated")
        self.assertTrue(matching.titles_match("The Hobbit", "Hobbit (Unabridged)"))
        self.assertTrue(matching.titles_match("Educated: A Memoir", "Educated"))
        self.assertFalse(matching.titles_match("Dune", "Dune Messiah"))

    def test_authors(self):
        self.assertTrue(matching.authors_match("James S.A. Corey", ["James S. A. Corey"]))
        self.assertTrue(matching.authors_match("Gabriel García Márquez", ["Gabriel Garcia Marquez"]))
        self.assertFalse(matching.authors_match("Andy Weir", ["Martha Wells"]))


class Parsing(unittest.TestCase):
    def test_shelf_page(self):
        owner, books = goodreads.parse_shelf_page(page("Jane", "read", FRIEND_SHELF))
        self.assertEqual(owner, "Jane")
        b = books[0]
        self.assertEqual((b["goodreads_id"], b["title"], b["author"]), ("999", "Educated", "Tara Westover"))
        self.assertEqual(b["user_rating"], 5)
        self.assertEqual(b["user_review"], "Couldn't put it down.\nRead it!")
        self.assertEqual(b["review_url"], "https://www.goodreads.com/review/show/1000")
        self.assertEqual(b["date_added"], "November 3, 2026")
        self.assertTrue(b["cover"].endswith("/999.jpg"))
        self.assertEqual(books[1]["user_rating"], 4.5)   # half stars
        self.assertEqual(books[1]["user_review"], "")

    def test_series_title_and_author(self):
        _, books = goodreads.parse_shelf_page(page("Me", "to-read", MY_SHELF))
        self.assertEqual(books[0]["title"], "Leviathan Wakes (The Expanse, #1)")
        self.assertEqual(books[0]["author"], "James S.A. Corey")

    def test_private_profile(self):
        with self.assertRaises(goodreads.GoodreadsError):
            goodreads.parse_shelf_page("<html><body>This profile is private. Sign in</body></html>")

    def test_layout_change(self):
        with self.assertRaises(goodreads.GoodreadsError):
            goodreads.parse_shelf_page("<html><body><div>new layout</div></body></html>")

    def test_libby_summary(self):
        s = libby.summarise(OD_ITEMS["Educated"][1], "lapl", "LAPL")
        self.assertEqual((s["status"], s["holds"], s["wait_days"]), ("hold", 42, 35))


class EndToEnd(unittest.TestCase):
    def test_full_sync(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = tmp / "config.yaml"
            cfg.write_text("""
goodreads: {user_id: "111", shelf: to-read, friends: [{id: "555"}]}
libby: {libraries: [{key: lapl, name: LA Public Library}]}
hoopla: {enabled: true}
buy: {audible_prices: true, librofm_link: true}
notifications: {notify_on_new_availability: true}
""")
            with mock.patch.object(runner, "DATA_DIR", tmp / "data"), \
                 mock.patch.object(runner, "SITE_DIR", tmp / "site"), \
                 mock.patch.object(http, "get", side_effect=fake_get), \
                 mock.patch.object(http, "post", side_effect=fake_post):
                self.assertEqual(runner.main(["--config", str(cfg)]), 0)
                data = json.loads((tmp / "site" / "data.json").read_text())
                by = {b["id"]: b for b in data["books"]}

                self.assertEqual(by["1"]["best"], "now")
                self.assertEqual(by["1"]["title"], "Leviathan Wakes")
                self.assertEqual(by["1"]["hoopla"]["status"], "available")
                self.assertEqual(by["1"]["libby"][0]["narrators"], ["Jefferson Mays"])
                self.assertEqual(by["2"]["best"], "hold")           # ebook ignored, audiobook on hold
                self.assertEqual(by["2"]["libby"][0]["media_id"], "203")
                self.assertEqual([f["name"] for f in by["2"]["friends"]], ["Sam"])  # other edition
                self.assertEqual(by["2"]["friends"][0]["rating"], 5)
                self.assertEqual(by["3"]["best"], "none")
                self.assertEqual(by["3"]["libby"][0]["status"], "not_owned")
                self.assertEqual(by["4"]["libby"][0]["status"], "always")
                self.assertEqual(by["4"]["buy"]["audible"]["price"], 17.47)
                self.assertEqual(by["4"]["friends"][0]["rating"], 4.5)

                # Second run: book 2 becomes available -> counted as newly available + notified
                OD_ITEMS["Educated"][1].update(isAvailable=True, availableCopies=1)
                with mock.patch("sync.notify.send") as send:
                    runner.main(["--config", str(cfg)])
                    send.assert_called_once()
                    self.assertIn("Educated", send.call_args[0][1])
                OD_ITEMS["Educated"][1].update(isAvailable=False, availableCopies=0)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
