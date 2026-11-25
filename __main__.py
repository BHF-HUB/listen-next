"""Run a full sync:  python -m sync  [--limit N] [--config config.yaml]

Writes site/data.json (what the app shows) and data/state.json + data/cache.json
(memory between runs, committed back to the repo by the GitHub Action).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import buy, goodreads, hoopla, libby, notify
from .matching import book_key, strip_series

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
CSV_FALLBACK = DATA_DIR / "goodreads_library_export.csv"

HOOPLA_TTL = timedelta(days=5)
AUDIBLE_TTL = timedelta(days=2)


def now():
    return datetime.now(timezone.utc)


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def fresh(entry, ttl):
    if not entry:
        return False
    try:
        return now() - datetime.fromisoformat(entry["checked"]) < ttl
    except (KeyError, ValueError):
        return False


def log(msg):
    print(msg, flush=True)


def load_shelf(cfg, errors):
    gr = cfg["goodreads"]
    try:
        _, books = goodreads.fetch_shelf(str(gr["user_id"]), gr.get("shelf", "to-read"))
        log(f"Goodreads: {len(books)} books on '{gr.get('shelf', 'to-read')}'")
        if books:
            return books
    except Exception as e:
        errors.append(f"Goodreads shelf: {e}")
        log(f"!! Goodreads shelf page failed: {e}")
    if CSV_FALLBACK.exists():
        books = goodreads.load_export_csv(CSV_FALLBACK, gr.get("shelf", "to-read"))
        log(f"Using Goodreads export CSV fallback: {len(books)} books")
        return books
    return []


def load_friends(cfg, errors):
    """Index of what friends have read: by Goodreads book id and by title|author key."""
    by_id, by_key = {}, {}
    for f in cfg["goodreads"].get("friends") or []:
        fid = str(f["id"] if isinstance(f, dict) else f)
        try:
            owner, books = goodreads.fetch_shelf(fid, "read", max_pages=15)
        except Exception as e:
            errors.append(f"Friend {fid}: {e}")
            log(f"!! friend {fid}: {e}")
            continue
        name = (f.get("name") if isinstance(f, dict) else None) or owner or f"Friend {fid}"
        log(f"Friend {name}: {len(books)} read")
        for b in books:
            entry = {
                "name": name,
                "profile_url": f"https://www.goodreads.com/user/show/{fid}",
                "rating": b.get("user_rating") or 0,
                "review": (b.get("user_review") or "")[:600],
                "review_url": b.get("review_url"),
                "read_at": b.get("read_at"),
            }
            by_id.setdefault(b["goodreads_id"], []).append(entry)
            by_key.setdefault(book_key(b["title"], b["author"]), []).append(entry)
    return by_id, by_key


def best_status(rec):
    statuses = [l["status"] for l in rec["libby"]]
    if "available" in statuses or "always" in statuses or rec["hoopla"]["status"] == "available":
        return "now"
    if "hold" in statuses:
        return "hold"
    if (rec["buy"].get("audible") or {}).get("asin"):
        return "buy"
    return "none"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--limit", type=int, default=0, help="only process the first N books (testing)")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text())
    DATA_DIR.mkdir(exist_ok=True)
    SITE_DIR.mkdir(exist_ok=True)
    cache = load_json(DATA_DIR / "cache.json", {"hoopla": {}, "audible": {}})
    state = load_json(DATA_DIR / "state.json", {"books": {}})
    errors, started = [], time.time()

    books = load_shelf(cfg, errors)
    if args.limit:
        books = books[: args.limit]
    friends_by_id, friends_by_key = load_friends(cfg, errors)

    libraries = []
    for lib in cfg.get("libby", {}).get("libraries") or []:
        key = lib["key"]
        name = lib.get("name")
        if not name:
            info = libby.library_info(key) or {}
            name = info.get("name") or key
        libraries.append({"key": key, "name": name})

    hoopla_on = cfg.get("hoopla", {}).get("enabled", True)
    buy_cfg = cfg.get("buy", {})
    out, newly = [], []

    for i, b in enumerate(books, 1):
        gid, title, author = b["goodreads_id"], b["title"], b["author"]
        log(f"[{i}/{len(books)}] {title} — {author}")
        rec = {
            "id": gid,
            "title": strip_series(title),
            "full_title": title,
            "author": author,
            "cover": b.get("cover") or "",
            "goodreads_url": f"https://www.goodreads.com/book/show/{gid}",
            "date_added": b.get("date_added", ""),
            "avg_rating": b.get("avg_rating", ""),
            "year": b.get("year", ""),
            "libby": [],
            "hoopla": {"status": "off"},
            "buy": buy.links(title, author),
        }

        for lib in libraries:
            try:
                rec["libby"].append(libby.check(lib["key"], lib["name"], title, author))
            except Exception as e:
                rec["libby"].append({"library": lib["key"], "library_name": lib["name"],
                                     "status": "error", "note": str(e)[:160]})

        if hoopla_on:
            c = cache["hoopla"].get(gid)
            if fresh(c, HOOPLA_TTL) and c["result"]["status"] != "unknown":
                rec["hoopla"] = c["result"]
            else:
                rec["hoopla"] = hoopla.check(title, author)
                cache["hoopla"][gid] = {"checked": now().isoformat(), "result": rec["hoopla"]}

        if buy_cfg.get("audible_prices", True):
            c = cache["audible"].get(gid)
            if fresh(c, AUDIBLE_TTL):
                rec["buy"]["audible"] = c["result"]
            else:
                try:
                    rec["buy"]["audible"] = buy.audible_lookup(title, author)
                    cache["audible"][gid] = {"checked": now().isoformat(),
                                             "result": rec["buy"]["audible"]}
                except Exception as e:
                    rec["buy"]["audible"] = None
                    rec["buy"]["audible_error"] = str(e)[:120]
        if not buy_cfg.get("librofm_link", True):
            rec["buy"].pop("librofm_search", None)

        # Friends who read it (same edition id, or same title+author on another edition)
        seen, friends = set(), []
        for f in friends_by_id.get(gid, []) + friends_by_key.get(book_key(title, author), []):
            if f["name"] not in seen:
                seen.add(f["name"])
                friends.append(f)
        rec["friends"] = friends

        # Change tracking
        rec["best"] = best_status(rec)
        prev = state["books"].get(gid, {})
        since = prev.get("now_since") if prev.get("best") == "now" else None
        if rec["best"] == "now" and prev.get("best") != "now":
            since = now().isoformat()
            if prev:  # don't notify for books seen for the first time
                newly.append(rec)
        rec["available_since"] = since
        state["books"][gid] = {"best": rec["best"], "now_since": since}
        out.append(rec)

    # Forget books that left the shelf
    ids = {r["id"] for r in out}
    state["books"] = {k: v for k, v in state["books"].items() if k in ids}

    payload = {
        "generated_at": now().isoformat(),
        "duration_sec": round(time.time() - started),
        "goodreads_user": str(cfg["goodreads"]["user_id"]),
        "shelf": cfg["goodreads"].get("shelf", "to-read"),
        "libraries": libraries,
        "friends_tracked": len(cfg["goodreads"].get("friends") or []),
        "errors": errors,
        "books": out,
    }
    (SITE_DIR / "data.json").write_text(json.dumps(payload, indent=1))
    (DATA_DIR / "state.json").write_text(json.dumps(state, indent=1))
    (DATA_DIR / "cache.json").write_text(json.dumps(cache, indent=1))

    if newly and cfg.get("notifications", {}).get("notify_on_new_availability", True):
        names = ", ".join(r["title"] for r in newly[:5])
        more = f" (+{len(newly) - 5} more)" if len(newly) > 5 else ""
        site = os.environ.get("SITE_URL") or None
        notify.send(f"{len(newly)} audiobook(s) ready to borrow", names + more, site)

    counts = {}
    for r in out:
        counts[r["best"]] = counts.get(r["best"], 0) + 1
    log(f"Done: {len(out)} books {counts}; newly available: {len(newly)}; errors: {len(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
