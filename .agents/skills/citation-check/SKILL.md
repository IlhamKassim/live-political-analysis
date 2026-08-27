---
name: citation-check
description: >-
  Verifies that factual claims on civic education and site-literacy pages (e.g. public/learn/*.html)
  trace directly to their cited sources using the automated judge loop.
---

# Citation Check Workflow

This skill explains how to run and interpret `lpa.citation_check` for hand-authored civic-education pages under `public/learn/` (e.g. `coalitions.html`, `ge16-process.html`, `glossary.html`).

Per issue #22's verification standard, every factual claim must trace to a cited source before content is considered complete.

---

## 1. Citation Convention in HTML

Wrap each factual claim in an element with `data-claim` and `data-cite`:

```html
<p data-claim data-cite="https://example.com/source-page">
  GPS was formed in 2018 after four Sarawak-based parties left Barisan Nasional.
</p>
```

- Each fact requires its own `data-claim` element (do not bundle multiple claims).
- Add an explicit `id` (`<p data-claim id="gps-founding" ...>`) for claims you expect to reference or override.
- Leaving `data-cite` empty will cause the check to flag the claim as uncited.

---

## 2. Running the Verification

Run the checker from the repository root:

```sh
.venv/bin/python -m lpa.citation_check public/learn/coalitions.html
```

### What Happens:
1. **Mechanical Pass**: Extracts claims, fetches URLs via HTTP, and flags `no_citation` or `fetch_failed`.
2. **Semantic Judge Pass**: Spawns an isolated subagent with the claim text and fetched source text (isolated in a temporary directory to avoid context pollution).
3. **Verdict**: Outputs `supported`, `contradicted`, or `unclear`.

Exit code is `0` only when all claims on the page evaluate to `supported`.

---

## 3. Handling Unresolved or Ambiguous Claims

- If a claim is ambiguous or the judge fails to resolve it, details are written to `public/learn/<page>.html.pending.json`.
- To provide a deliberate manual verdict override:
  ```sh
  .venv/bin/python -m lpa.citation_check public/learn/coalitions.html --verdicts verdicts.json
  ```
  Where `verdicts.json` contains:
  ```json
  [{"id": "gps-founding", "verdict": "supported", "detail": "Verified against party constitution records"}]
  ```

---

## 4. Reference Docs
- See `docs/agents/citation-check.md` for full implementation and safety notes.
