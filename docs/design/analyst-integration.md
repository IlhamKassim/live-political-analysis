# Analyst integration

The approved source stays at `scrollcraft/builds/analyst-b`. This is already beside the Observatory source at `scrollcraft/builds/observatory` and shared assets at `scrollcraft/builds/shared`, matching `_OBSERVATORY_ROOT`. No relocation or source edits are necessary.

`lpa.politikku_analyst` copies every file with `shutil.copy2` into `public/analyst/`, preserving relative paths. It then replaces only the copied HTML header with the homepage's `_observatory_header(Language.EN)`. Homepage fragment links become `/#perspective`, `/#chamber`, and `/#find`. Header-only CSS and mobile-menu JS are added separately so the approved stylesheet and animation script remain byte-identical.

**Update, 2026-09-11: Analyst now has a BM page.** `scrollcraft/builds/analyst-b/index.ms.html` is a hand-translated copy of `index.html` (label: *Penganalisis*). The adapter builds it to `public/ms/analyst/index.html` with the BM header, pointing its assets at the EN copies in `../../analyst/`, and never copies the source into `public/analyst/`. Both pages carry the header's EN/BM toggle, rewritten to switch between `/analyst/` and `/ms/analyst/`. The homepage, `NAV_LINKS` (no longer `en_only`) and the SPA sidebar (`nav_analyst` / `nav_analyst_href` in `i18n.js`) link it in BM. Any copy change to one page must be made in the other. The internal "Direction B / Concept B" labels were removed from both. `app.js` now reads its motion-button labels and Swing unit from `data-` attributes, so it is no longer byte-identical to the original concept.

Before that update, the language toggle was omitted because the page had no BM translation, and the navigation entry was `en_only`.

GSAP 3.13.0 and ScrollTrigger are local files in `assets/`; the fonts are local too. There is no CDN dependency.

The copied main content is byte-identical to the approved source. This preserves every In pilot badge and all disclosures about illustrative Swing controls, conceptual source tracing, and proposed export fields. There are no live inputs or calculations.

## Delivery choice

Keep the prepared `public/analyst/` tree under version control, alongside its design source and adapter. The daily Action uploads all of `public/` and does not delete this directory. Rerun the command when the design or shared header changes:

```sh
.venv/bin/python -m lpa.politikku_analyst
```

This is a copy-and-header preparation command, not a compilation step. The delivered files run as-is.

The request's Learn comparison is out of date: `.github/workflows/daily.yml` now runs `python -m lpa.politikku_learn`; `.gitignore` excludes generated Learn HTML. Its renderer loads election status and the current date. Analyst has neither dependency, so it does not need that daily step. No `daily.yml` change is proposed. Prepared files must be included in the eventual commit, or a fresh checkout's deployment will not contain the page. No commit or deployment has been performed.

## Pending shared changes

`analyst-integration-shared.patch` is a proposed, unapplied diff for:

- `src/lpa/politikku_landing.py`: add an English Analyst link to the homepage header.
- `src/lpa/politikku_shell.py`: register Analyst in `NAV_LINKS`.
- `frontend/public/index.html`: add the matching SPA sidebar destination, required by the existing navigation parity test.
- `tests/test_politikku_site_links.py`: include the prepared page in the route sweep and assert its deliberate absence of language links.

The shared files remain untouched pending the requested review. After applying the reviewed patch, rerun the adapter so the copied header includes the new navigation entry, then run the route sweep and full checks.

## Pilot workbench (2026-09)

Functional analyst tools live at **`/analyst/tools/`** — a dense workbench (not the scroll concept page):

1. **Swing-model sandbox** — client-side replay of `swing_model.py` against exported Baseline + inputs.
2. **Source-level sentiment drill-down** — article-level scores from `scored_article` Storage.
3. **Full data export** — `analyst-bundle.zip` with IDEAS topic folders.

Data is written by `lpa.release_data` into `public/analyst/data/`. See [analyst-pilot.md](analyst-pilot.md).

### Model governance

Sandbox slider changes are local what-if only in the browser. Changing production Swing Model constants requires a recorded edit in `data/` and an ADR note. This pilot does not expose a production settings editor.

## Verification of prepared files

647 tests passed, 9 deselected. Ruff and mypy passed. The new tests check source immutability, identical main content and assets, all local resource paths, notices, English-only navigation, repeatable preparation, and a missing-source failure.

Chrome loaded `http://127.0.0.1:4179/analyst/`. Desktop screenshots confirmed the shared header and preserved pinned source-trace transition. At 390px, the shared menu opened and closed with its button and Escape. No console warnings or errors were observed. The proposed shared patch passes `git apply --check`; it has not been applied or tested as an integrated change.
