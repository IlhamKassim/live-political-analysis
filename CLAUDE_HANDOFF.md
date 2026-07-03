# MyPolitik Claude Handoff

Date: 2026-07-02
Project path: `/Users/danialalias/Desktop/Experiments/mypolitik`
Local URL: `http://localhost:4178/#parlimen/parti`

## What This App Is

MyPolitik is a static/Workers web app showing Malaysian parliamentary and DUN seats on an SVG map. The main user flow is:

1. Start on the national map.
2. Toggle `Parliament`/`DUN` and `State`/`Party` from the top controls.
3. Tap a state/seat to isolate the state.
4. On mobile, the isolated state becomes the main map. The bottom card becomes the interaction surface for selecting districts and opening details.

The current design direction is a dark, dense, map-first product UI:

- Top-left: MyPolitik logo.
- Top-right: app icons/menu; on mobile controls are moved into a burger menu.
- Bottom: floating card with search, locate, state inspect controls, or district detail.
- Party mode is the default.
- State name is shown above the isolated map, so the card should avoid repeating unnecessary state information.

## Important Files

- `public/app.js`: main app state, SVG map behavior, card rendering, mobile state-inspect flow, animations.
- `public/styles.css`: layout, responsive mobile/desktop behavior, card styling, selected district texture, top/bottom chrome.
- `public/index.html`: static DOM shells for top bar, map, panel/card, dialogs.
- `public/i18n.js`: text keys for EN/BM.
- `public/lib.js` and `public/lib.test.mjs`: shared helpers and tests.
- `scripts/validate.sh`: validation script used after edits.
- `dev-server.py` / `npm run dev`: local static server on `:4178`.

## Current Git State

The worktree is dirty and includes many existing modifications not all made in the last exchange. Do not revert unrelated files. Recent relevant files:

- `public/app.js`
- `public/styles.css`
- `public/index.html`
- `public/i18n.js`
- `public/data/candidates-ge15.json`
- `public/data/candidates-dun-prn15.json`
- `public/data/voting-guide.json`

There are also unrelated/older modified files such as `README.md`, `package.json`, `pipeline/*`, `worker.js`, and `wrangler.jsonc`. Treat them as existing work unless explicitly asked.

## Key UX Decisions Already Made

### Global Layout

- Removed the old sidebar.
- Added top-left MyPolitik logo.
- Put app icons in the top-right area.
- On mobile, top controls/buttons are moved into a burger menu to leave more room for the map.
- Background grid was made uniform: remove the larger thicker square grid effect so it reads as one small-box grid.
- Removed map zoom controls (`+`, `-`, `1x`) from the UI.
- Removed hover tooltip/pop-up behavior on mobile because it was appearing at the bottom and cluttering the page.

### Defaults and Controls

- Party mode is default (`state.mode = "parti"`).
- `Parliament/DUN` and `State/Party` pills were moved to the top control area.
- The locate/target button sits on the same row as search where applicable.
- On mobile, header controls go into the burger menu.

### Map Behavior

- When a state is selected, the app isolates that state in the main map.
- On mobile main overview, district borders are hidden until a state is selected.
- Once a state is selected, district borders are visible.
- When a district is selected, it gets a selected line texture. The latest texture direction is thin, closer-spaced lines so it remains visible in small districts.
- In isolated district mode, district borders were strengthened with white/clear strokes.
- The isolated state map must always sit between the top nav and bottom card, without being pushed behind the top nav when viewport height shrinks.
- A state label is shown above the isolated map, positioned close to the map rather than too high.

### Mobile State/District Flow

The intended mobile flow is:

1. User taps a state.
2. State is isolated and displayed large.
3. Bottom card shows a compact state inspect tray with:
   - current selected district overview if a district is previewed,
   - district dropdown,
   - locate button,
   - `More` button when there is a selected district.
4. User can either tap a district on the map or choose a district from the dropdown.
5. Tapping/choosing a district updates the same dropdown/picker state; no extra instruction card.
6. Tapping `More` opens the full district details card.
7. In full district detail, the district picker + locate button stay fixed at the bottom of the card while details scroll above.
8. If the user taps the smaller map while detail is open, the card returns to compact inspect mode and the state map goes back to its original large isolated size so another district can be chosen.
9. Back from district detail should also return the map to the original isolated state size.

## Recent Important Code Areas

### Panel View State

`public/app.js` around `setPanelView(view)`:

- Panel classes:
  - `empty`
  - `state-summary`
  - `seat-detail`
- `setPanelView("state")` shows the state inspect/summary card.
- `setPanelView("seat")` shows district detail inside `#panel-state`.
- `STATE_ACTIONS` is hidden unless in seat detail.

### Animation Helpers

`public/app.js` contains:

- `animateRectFlip(el, first, last, duration)`
- `animateCardResize(card, mutate)`
- `swapCardWithMinimizePop(card, mutate)`

These make the bottom card and SVG map resize smoothly using transform/opacity FLIP-like animation. Reduced-motion users get the simpler path.

The `More` interaction currently uses `swapCardWithMinimizePop`:

- card collapses/minimizes,
- data/layout swaps,
- card pops back up with the full district detail.

### State Inspect Flow

Important functions in `public/app.js`:

- `districtOptionsForOpenState()`
- `districtSelectHTML(selectedCode)`
- `mapInspectLocateHTML()`
- `districtSwitchRowHTML(selectedCode, includeMore)`
- `seatDistrictSwitcherHTML(selectedCode)`
- `setDistrictPickerOpen(open, focusOption)`
- `renderMapInspectTray()`
- `setMapInspect(open)`
- `previewDistrict(code, zoom = false)`
- `showMapInspectDetails(options = {})`
- `locateMapInspectDistrict(btn, options = {})`

`renderMapInspectTray()` renders the compact mobile card contents. It includes the overview, dropdown, locate button, and optionally `More`.

`showMapInspectDetails({ pop: true })` handles the minimized-pop transition from compact inspect to detail.

### Refit Bug Fix

There was a bug where returning from district detail to state inspect left the state map too small. The fix added `refitOpenStateMapSettled()`:

```js
function refitOpenStateMapSettled() {
  refitOpenStateMap();
  refitOpenStateMap(140);
  refitOpenStateMap(360);
}
```

`setMapInspect(open)` now calls the settled refit when entering or re-entering inspect mode. This matters because card/map layout can still be settling when the first refit fires.

Browser verification was previously done and showed the returned state width matched the original isolated width exactly (`widthRatio: 1`).

### Sticky Bottom District Picker in Detail

Recent change:

- `seatCardHTML()` wraps the district detail content in:

```html
<div class="seat-detail-main">...</div>
```

- The district picker remains outside this wrapper via `seatDistrictSwitcherHTML(seat.code)`.
- Mobile CSS makes only `.seat-detail-main` scroll and keeps `.seat-district-switcher` fixed at the bottom of the detail card.

Relevant CSS:

- `.seat-detail-main { min-width: 0; }`
- `#panel.seat-detail #state-info { display:flex; flex-direction:column; ... }`
- `#panel.seat-detail .seat-detail-main { overflow-y:auto; ... }`
- `#panel.seat-detail .seat-district-switcher { flex:0 0 auto; ... }`

### Removed Redundant District Detail Header

Latest user request before this handoff:

- Remove the redundant card header row that showed:
  - `Sarawak`
  - `31 Parliament seats`
  - expand/share/card icons

Implemented in CSS:

```css
#panel.seat-detail #panel-state > .state-head {
  display: none;
}

#panel.seat-detail #state-info {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}
```

Also removed the redundant `State Sarawak` line in isolated district detail:

- `seatCardHTML(seat, options = {})` accepts `showStateLine`.
- `stateSeatCardHTML(seat)` calls `seatCardHTML` with `showStateLine: false`.
- Normal seat cards outside isolated state flow still keep the state line.

## Current Desired UI State

When mobile user has selected a state and then opens a district detail:

- State name appears above the map, not inside the card.
- The detail card should not repeat state-level header/count/actions.
- The detail card should start directly with district information:
  - code/name
  - tabs
  - content
- Bottom of detail card should keep district dropdown + locate button fixed.
- Scrolling should only scroll the district detail content, not the bottom picker.

## Validation Already Run

After the latest changes, these passed:

```bash
node --check public/app.js
node --test --test-reporter=dot public/lib.test.mjs
scripts/validate.sh
```

`scripts/validate.sh` output included:

- `PASS node --check public/app.js`
- `PASS python3 -m py_compile pipeline/*.py`
- `PASS JSON.parse public/data/*.json`
- `PASS GE15 coalition tally`

## Browser Verification Caveat

Some browser/screenshot verification was done earlier with Playwright/CDP and local `http://localhost:4178/#parlimen/parti`.

In the most recent attempt, the environment rejected creation of a temporary browser-check script due to usage-limit policy. Do not try to work around that restriction. If visual confirmation is needed, use the normal local browser manually or use allowed tooling.

## Local Dev and Deployment

Run local server:

```bash
npm run dev
```

README says this serves:

```text
http://localhost:4178
```

Useful route:

```text
http://localhost:4178/#parlimen/parti
```

Staging info from README:

- staging domain: `staging.mypolitik.krackeddevs.com`
- deploy command noted there:

```bash
npx wrangler deploy --env staging
```

Earlier in the session the user asked to push/deploy to staging and test local staging URL, but this handoff focuses on the UI work and current local state. Check git branch/status and deployment conventions before pushing.

## Suggested Next Steps for Claude

1. Open `public/app.js` and `public/styles.css`.
2. Confirm the latest visual issue is gone on mobile:
   - choose Sarawak,
   - choose a district like `P.195 · Bandar Kuching`,
   - tap `More`,
   - verify the card no longer shows the redundant Sarawak header row,
   - verify the district picker remains fixed at bottom while details scroll.
3. If the user asks for staging, run validations first, inspect branch/status, then deploy using the repo's staging workflow.
4. Avoid broad refactors. Most desired changes have been small, visual, and interaction-specific.

## Tone/Preference Notes From User

The user is iterating visually and expects fast product UI changes. They often provide screenshots and direct instructions. Interpret typos generously. Keep the map large on mobile, remove repeated information, and preserve the district-switching flow.

