# MyPolitik GAP Analysis - 2026-07-04

Audit time: 2026-07-04 22:26 +08  
Auditor: Codex  
App tested: local dev server at `http://127.0.0.1:4178/#parlimen/parti`  
Raw artifacts: `/private/tmp/mypolitik-audit/targeted-audit.json` and screenshots in `/private/tmp/mypolitik-audit/`

## Scope

Full product-UI and motion pass over the current MyPolitik build:

- Baseline syntax/data checks.
- Desktop 1440x965.
- Short desktop 1201x760.
- Mobile 390x844.
- Tablet/mobile breakpoint 768x1024.
- Reduced-motion mobile 390x844.
- Topbar/menu controls, language, tier/mode tabs, search, geolocation, state drill, district finder, seat tabs, share-card entry points, PRN Johor mode, keyboard focus order, hit-target inventory, console/network noise, and animation/reduced-motion coverage.

## Verification Baseline

Passed:

- `node --test public/lib.test.mjs` - 90/90 tests passing.
- `node --check public/app.js` - pass.
- `node --check public/lib.js` - pass.
- `scripts/validate.sh` - pass:
  - app syntax
  - pipeline Python compile
  - public data JSON parse
  - GE15 coalition tally

Existing worktree before report:

- Only pre-existing untracked file: `scratchpad-sweep.js`.

## What Works

- Desktop overview loads 222 Parliament seats and DUN toggle loads 613 DUN paths.
- Topbar info card opens/closes correctly on desktop.
- Mobile hamburger opens the hidden controls; info and language actions work correctly from the menu.
- EN/BM language switching updates the search placeholder.
- State/party and Parliament/DUN tabs update without JS errors.
- Overview search finds `Bandar Kuching`; keyboard ArrowDown + Enter selects `P.195`.
- Desktop state/seat detail renders the district finder and seat tabs.
- Seat tabs switch between Overview, Results, Candidates, and Voting.
- PRN Johor badge opens election mode on desktop and mobile.
- Mobile map-tap flow works:
  - tap a state -> compact state inspect tray;
  - tap a district -> preview row with `More`;
  - tap `More` -> full detail card with sticky district switcher.
- Mobile geolocation with mocked KLCC coords resolves to a DUN seat (`10_N.21`) and opens the state.
- Reduced-motion mode does not leave active animations running in the tested states.
- No unlabeled visible buttons were found in the automated inventory.
- Most controls have visible focus rings and tactile `:active` feedback.

## Bugs

### P0 - Mobile search results are visible but not tappable

Evidence:

- Test: mobile 390x844, type `Bandar Kuching`.
- First result exists at `{ x: 26, y: 726, w: 282, h: 35 }`.
- `document.elementFromPoint()` at the center of that result returns `svg#map`, not the result button.
- Playwright touch/click fails because the map intercepts pointer events.
- Keyboard ArrowDown + Enter still selects the result, so this is a touch hit-testing/layering bug.

Likely cause:

- The result dropdown is inside the bottom panel but appears in the map's hit-test layer on mobile. The visual stack and pointer-event stack disagree.

Fix direction:

- Raise the panel/search results above `#stage/#map` in stacking context during search, or render mobile search results inside a fixed portal above the panel.
- Add a regression check: mobile typed search -> tap first result -> hash changes to selected seat.

Screenshot:

- `/private/tmp/mypolitik-audit/mobile-search-result-intercept.png`

### P1 - Search input keyboard focus ring is overridden

Evidence:

- Focus sweep on desktop/mobile shows `input#q` computed outline as `3px none`.
- Source has an early `.search input:focus-visible` ring, but a later `.search input:focus { border-color: var(--line-2); outline: none; }` overrides the outline.

Impact:

- Keyboard users can tab to search, but focus is not clearly visible.

Fix direction:

- Move/repeat `.search input:focus-visible` after the later `.search input:focus` rule, or make the later focus rule not reset `outline`.

### P1 - Share link/card actions are hidden in seat detail

Evidence:

- In seat detail, `#share-link` and `#share-card` exist but are not visible in desktop or mobile tests.
- `setPanelView("seat")` sets `STATE_ACTIONS.hidden = false`, but CSS hides the whole header: `#panel.seat-detail #panel-state > .state-head { display: none; }`.

Impact:

- The "shareable seat card" growth path is unavailable at the moment a citizen is viewing a seat.

Fix direction:

- Move share actions into `.seat-detail-main` or the sticky district switcher area.
- Keep the redundant state header hidden, but do not hide the seat-level share/download affordances.

### P1 - Keyboard district selection leaves the dropdown open

Evidence:

- Short desktop 1201x760:
  - Open district finder in seat detail.
  - ArrowDown + Enter.
  - Hash remains `#parlimen/parti/P.195`.
  - `aria-expanded` remains `true`; list remains visible.
  - `elementFromPoint()` over the seat tab returns `.map-inspect-option`, so the dropdown blocks tab clicks.
- Mouse-clicking an option does close the list and changes the hash, so this is keyboard-specific.

Impact:

- Keyboard users can get stuck behind an open dropdown.
- On shorter screens, the dropdown covers seat tabs/content.

Fix direction:

- On Enter in the dropdown list, select the focused option, close the list, and return focus to the toggle.
- Consider closing the dropdown on any outside pointerdown before normal click handling.

### P2 - PRN local dev emits console 404s

Evidence:

- Console logs repeated 404 errors for:
  - `data/scores.json`
  - `/api/live/johor`
- `scores.json` is intentionally absent because Skor is gated.
- `/api/live/johor` exists in the Worker, but the local Python static server does not serve it; the app then falls back to `data/live-johor.json`.

Impact:

- Expected optional missing resources show as console errors and can mask real failures during QA.

Fix direction:

- For dev, prefer asset fallback before `/api/live/johor`, or have `dev-server.py` return the baked `public/data/live-johor.json` for `/api/live/johor`.
- For `scores.json`, use a manifest flag or avoid fetching the absent file until Skor is intentionally unlocked.

### P2 - PRN badge hit target is under 44px high

Evidence:

- Automated target audit flagged only one recurring small target: `#live-badge`.
- Size is about `168x28` across desktop/mobile.

Impact:

- Width is generous, but height misses the touch target bar.

Fix direction:

- Increase minimum height to 44px or add an invisible hit area via `::before`.

### P3 - PRN mobile mode hides campaign summary behind district-first tray

Evidence:

- Mobile PRN screenshot shows Johor map + `Choose district...` tray only.
- Desktop PRN shows countdown, dates, candidate sharebar, source, exit button in the card.

Impact:

- Mobile users entering PRN mode lose the election-context summary and are pushed straight into district selection.

Fix direction:

- Add a compact PRN summary row above the district picker on mobile, or make the bottom sheet expand by default when PRN mode opens.

Screenshot:

- `/private/tmp/mypolitik-audit/mobile-390-prn.png`

## Motion Findings

- Main animations are transform/opacity based: `reset-in`, `hint-in`, `pop-up/down`, `fade-in-only`, `live-pulse`, spinner.
- `prefers-reduced-motion` appears 11 times in CSS and disabled active animations in the reduced-motion browser pass.
- `DETAIL_POP_MS = 600` is long compared with the rest of the motion system. It may be acceptable for the large map/card transition, but it should be interruptible and should not block further interaction.
- The live PRN dot loops indefinitely. It is disabled under reduced motion, which is good.

Improvement:

- Replace ad hoc durations with shared motion tokens already implied by the skill: 100/150/200/300/400/500ms.
- Keep More/detail as the only "big" 500-600ms transition; keep repeated UI state changes <=200ms.

## Accessibility / Interaction Gaps

- Search input focus ring must be fixed.
- PRN badge needs a 44px hit target.
- Mobile search result tap must be fixed; it is currently the most important citizen-first action.
- Seat-detail share controls need to be reachable by keyboard and touch.
- District dropdown needs full keyboard close/select semantics.
- Mobile menu currently works, but the controls are hidden until the hamburger is opened; tests must open the menu before checking topbar actions.

## UX / Product Improvement Backlog

### Highest leverage

1. Fix mobile search result tap layering.
2. Restore seat-detail share/link/card actions.
3. Fix search input focus-visible override.
4. Fix keyboard district dropdown close/select behavior.
5. Add a dev-server `/api/live/johor` fallback to remove expected 404 noise.

### Product polish

1. Add a visible "Share" action inside the seat detail card, not only in hidden header actions.
2. Add a compact PRN mobile campaign strip: `PRN Johor 2026 · 7 days · 172 candidates · polling 11 Jul`.
3. Add a subtle scroll affordance when state/PRN cards overflow on desktop.
4. Increase `#live-badge` touch area without making the visual heavier.
5. Add a regression browser script to CI/manual QA:
   - mobile search tap;
   - seat share card visible/open;
   - district dropdown keyboard Enter closes;
   - focus ring on search;
   - PRN badge opens and mobile summary is visible.

## Evidence Files

Primary JSON:

- `/private/tmp/mypolitik-audit/targeted-audit.json`

Key screenshots:

- `/private/tmp/mypolitik-audit/mobile-search-result-intercept.png`
- `/private/tmp/mypolitik-audit/mobile-main-map-district-more.png`
- `/private/tmp/mypolitik-audit/desktop-short-1201-district-finder-and-seat-tabs-fail.png`
- `/private/tmp/mypolitik-audit/desktop-1440-prn.png`
- `/private/tmp/mypolitik-audit/mobile-390-prn.png`

## Next Suggested Fix Order

1. CSS stacking fix for mobile search results.
2. CSS focus-visible fix for `#q`.
3. Move share actions into seat detail content.
4. Dropdown keyboard close/select fix.
5. Dev-server fallback for `/api/live/johor`.
6. PRN mobile summary strip.
