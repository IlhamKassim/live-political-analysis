# PolitikKu's constituency lookup (issue #77)

The one piece of PolitikKu with real client-side state (#70's own decision)
— a typed state machine that mounts into the Python-rendered homepage/
landing-page lookup markup (`data-pk-lookup-form` and its siblings) and
resolves a postcode, a constituency name, or (honestly, see below) a
geolocation fix to a Seat, entirely in the browser.

## Layout

- `src/types.ts` — the state model and the client index's shape.
- `src/resolve.ts` — pure postcode/name matching against the index.
- `src/geolocation.ts` — reads a real coordinate fix via
  `navigator.geolocation`, then deliberately does nothing with it: this
  pilot has no boundary/geometry data (ADR 0008) to resolve a coordinate
  against a Seat with, so faking a match would be worse than an honest
  "not supported yet" result. The privacy promise ("Location is read in
  your browser and never sent to us") holds because the coordinate is
  never inspected, sent, or stored — not because the button is hidden.
- `src/state-machine.ts` — a pure, synchronous reducer (`transition`), so
  every state transition is testable without a DOM.
- `src/storage.ts` — "Recently looked up" chips, `localStorage`, capped at
  four.
- `src/index-data.ts` — fetches `/politikku/data/lookup-index.json` once
  (built by `lpa.politikku_lookup_index`) and caches it in memory.
- `src/dom.ts` — mounts the state machine onto the existing markup and owns
  the dynamic results area (`[data-pk-lookup-results]`) for the
  `searching`/`locating`/`ambiguous`/`notFound`/`resolved` states, none of
  which are pre-rendered server-side.
- `src/lookup.ts` — the entry point, bundled to `lookup.js`.

## Commands

```sh
npm install
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm test            # vitest run
npm run build       # esbuild -> ../public/politikku/lookup.js (generated,
                     # not committed — see the repo root .gitignore)
```

`public/politikku/data/lookup-index.json` (the client index `index-data.ts`
fetches) is generated separately, by `python -m lpa.politikku_lookup_index`
— run both build steps before opening the pages locally.
