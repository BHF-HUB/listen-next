# Listen Next: your Goodreads queue, with audiobook availability

A small site you can keep on your phone's home screen. It shows every book on your Goodreads **to-read** shelf and, for each one:

- **Libby**: whether the audiobook is in your library's catalogue, and either *Borrow now* or the waitlist (holds, copies and estimated wait). It works with several library cards.
- **Hoopla**: whether the audiobook is on Hoopla. Hoopla has no waitlists, so a match means you can borrow it now.
- **Buy**: the current Audible price, plus links to search Audible and Libro.fm.
- **Friends**: which of your Goodreads friends have read the book, with their star rating and review.

It syncs automatically every 6 hours. Books that just became available get a **NEW** tag. You can also get an optional push notification on your phone.

It's free. GitHub runs the sync on a schedule and hosts the page.

---

## Setup (about 15 minutes, once)

### 1. Put the code on GitHub
1. Create a free account at [github.com](https://github.com) if you don't have one.
2. Click **+ → New repository**. Name it `listen-next`, choose **Public**, and click **Create**. (Free GitHub Pages needs a public repo. See *Privacy* below.)
3. On the new repo page, click **uploading an existing file**. Drag in **everything inside** the `audiobook-queue` folder, including the hidden `.github` folder. On a Mac, press ⌘⇧. in Finder to show hidden files. Then click **Commit changes**.

### 2. Fill in your details
Open `config.yaml` on GitHub, click the ✏️ pencil, and set:

| Setting | Where to find it |
|---|---|
| `goodreads.user_id` | Already set to yours (**193243785**). It's the number in your shelf URL: `goodreads.com/review/list/`**`193243785`**`-betsy` |
| `libby.libraries[].key` | Open your library in Libby on the web. It's the word after `/library/` in `libbyapp.com/library/`**`lapl`** |
| `goodreads.friends` | The profile ID of each friend whose reviews you want to see. Optionally add a name. |

Then click **Commit changes**.

> **Goodreads privacy setting:** go to Goodreads → Settings → Privacy and set *Who can view my profile* to **anyone**. Do this for your own account, and ask friends to do the same. The sync reads shelf pages the same way a signed-out visitor sees them, so a private shelf comes back empty. If you want to keep your profile private, see *Private profile* below.

### 3. Turn on the website
1. In the repo, go to **Settings → Pages**. Under *Build and deployment → Source*, choose **GitHub Actions**.
2. Go to **Settings → Actions → General → Workflow permissions** and choose **Read and write permissions**. Save.
3. Go to the **Actions** tab. If asked, click **"I understand my workflows, go ahead and enable them"**. Then open **Sync audiobook queue** and click **Run workflow**.

The first run takes about 2–10 minutes, depending on how many books you have. When it finishes, your site is at:

```
https://<your-github-username>.github.io/listen-next/
```

### 4. Put it on your phone
Open that address on your phone. Then:
- **iPhone (Safari):** tap Share → **Add to Home Screen**
- **Android (Chrome):** tap ⋮ → **Add to Home screen**

It then opens like an app.

### 5. (Optional) Push notifications when a book becomes available
1. Install the free **ntfy** app ([iOS](https://apps.apple.com/app/ntfy/id1625396347) / [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)).
2. In the app, subscribe to a topic with a long, unguessable name, like `listen-next-k7q2m9x4`.
3. In GitHub, go to **Settings → Secrets and variables → Actions → New repository secret**. Name it `NTFY_TOPIC` and set the value to that topic name.

---

## Everyday use
- **Add a book on Goodreads:** it shows up after the next sync.
- **Sync now:** Actions tab → *Sync audiobook queue* → **Run workflow**.
- **Change how often it syncs:** edit the `cron:` line in `.github/workflows/sync.yml`.
- **Filters:** *Borrow now*, *Waitlist*, *Buy only*, *Friends read*, *Not found*. The app remembers your last filter and sort.

## Good to know
- **No official APIs.** Goodreads shut its API to new developers in 2020. Goodreads also retired its shelf RSS feeds in November 2026. This app reads your public shelf pages (the same pages a signed-out visitor sees). Libby data comes from the same public catalogue endpoint the Libby website uses. Hoopla data comes from the endpoint hoopladigital.com uses for logged-out search. Any of these can change without notice. When something breaks, the app still loads, shows a "Last sync had problems" note, and falls back to search links.
- **Hoopla** is the least certain piece. If every Hoopla row says *Search Hoopla ↗*, its search endpoint has changed or blocked the sync. Everything else keeps working.
- **Backup: export file.** If Goodreads blocks or changes its shelf pages, the sync falls back to an export file you upload. Go to Goodreads → My Books → *Import and export* → **Export Library**, then upload the CSV to the repo as `data/goodreads_library_export.csv`. Re-upload it when your shelf changes. Friends' reviews can't come from the export.
- **Private profile:** use the export file above instead of making your profile public. Friends' shelves still need to be public.
- **Friends** are matched by title and author, not just by edition, so a friend who read a different edition still counts. Their profiles must be public.
- **Audible prices** are from the US store, refreshed every 2 days.
- **Privacy:** a free GitHub Pages site is public to anyone who has the URL. It's not listed anywhere, but don't treat it as secret. It shows the same information as your public Goodreads shelf.

## Run it on your own computer (optional)
```bash
pip install -r requirements.txt
python -m sync --limit 10        # quick test with 10 books
python -m http.server -d site    # then open http://localhost:8000
```

## Files
```
config.yaml                 ← your settings
sync/                       ← the sync (Python)
  goodreads.py  libby.py  hoopla.py  buy.py  matching.py  notify.py
site/index.html             ← the phone app (one file, no build step)
.github/workflows/sync.yml  ← the schedule
data/                       ← memory between runs (auto-updated)
tests/                      ← offline tests: python -m unittest
```
