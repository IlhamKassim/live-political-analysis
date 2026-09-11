# Site checks and publication

The hourly workflow calls the same CI workflow used for pushes and pull requests.
Only the main branch can proceed from those checks to the production build.

The order is:

1. Check Python, TypeScript, frontend JavaScript, the Worker, browser rendering,
   Postgres operations, and committed secrets.
2. Scrape and store the latest snapshot.
3. Copy frontend assets into the output directory.
4. Export the Projection and Sentiment into that output directory.
5. Render the pages from those exported app files, render other pages and cards,
   generate redirects and the sitemap, and render the feed.
6. Check export hashes, matching snapshot dates, Coalition totals, browser routes,
   the postcode lookup, and Projection search.
7. Attempt the existing dated-permalink archive, then upload the checked site.
8. Deploy that artifact in a separate job with Pages permissions.
9. Send Telegram notifications after deployment succeeds.

A failed required check prevents upload or deployment. Notification failure cannot
undo a successful deployment. The existing best-effort permalink archive remains
an exception: a rejected archive push is reported but does not prevent deployment.

## Shared data

`python -m lpa.release_data` writes the downloadable Projection JSON/CSV and the
app's Projection and Sentiment JSON. The two Projection JSON copies are identical.
The release manifest records the date and hashes of all four files.

Prerendering reads `public/app`, so its input is the same data shipped to visitors.
Dated Projection pages use the dataset date, including runs that cross midnight.
The workflow's existing `storage-write` concurrency group covers checks, building,
deployment and notification, and also serializes the Baseline bootstrap workflow.

`python -m lpa.release_data --check` rejects changed files, mismatched dates, or
Coalition totals that disagree with the Seat Calls. `python -m lpa.release_check`
opens the completed site in local Chromium before upload.

## Notifications and RSS

`python -m lpa.telegram_post --feed-only` renders previously logged posts without
sending messages or marking new triggers handled. It is safe to run before upload.
Normal Telegram processing runs only after successful deployment. Its new entries
reach the published RSS feed on the next successful hourly build.

## Local verification

The ordinary suite stays fast:

```sh
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src scripts/deepseek_agent.py
node --test frontend/public/lib.test.mjs frontend/public/worker.test.mjs
```

For browser verification, first build the lookup bundle from `ts/` with
`npm ci && npm run build`. Install the project's `prerender` extra and Chromium,
then run:

```sh
.venv/bin/pytest -m browser tests/test_release_browser.py
```

The browser test builds real pages in a temporary directory using a temporary
SQLite database and synthetic Sentiment. It does not access production Storage
or publish its output. It includes every top-level app section in both languages,
the landing pages, and one MP Profile in both languages.

The Postgres job provisions its own Postgres 16 service. For a local run, provide
`TEST_POSTGRES_URL` pointing to a disposable local database named `lpa_test`:

```sh
.venv/bin/pytest -m postgres tests/test_postgres_integration.py
```

The test uses a unique schema, checks snapshot replacement and transaction
rollback, and removes that schema afterward. It rejects non-local hosts and
other database names. It never reads `DATABASE_URL`.

Live model and external-network tests remain separate. These changes do not
automate Cloudflare Worker deployment or change branch protection settings.
