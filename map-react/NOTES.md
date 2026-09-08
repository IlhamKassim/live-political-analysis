# React Map Island Pilot — Findings & Architecture Notes

**Branch**: `experiment/react-map-island-pilot`  
**Focus**: Scoped test of declarative state management for the seat-detail panel ("Seat spotlight") and tooltip vs. the mobile pinned-tooltip bug in `frontend/public/app.js`.

---

## 1. The Core Finding: Did React Fix the Bug?

**Yes, structurally — provided state is modelled as a single source of truth.**

### The Vanilla JS Root Cause (`frontend/public/app.js`)
In the vanilla JS map app (~9,500 lines), `#tooltip` is a persistent global DOM element (`document.getElementById("tooltip")`). Its visibility is controlled via imperative mutations:
```javascript
// scattered throughout mousemove, click, and leave handlers:
TOOLTIP.hidden = true;
```
When mobile tap-to-inspect and state-open flows were introduced (`setMapInspect`, bottom tray gestures, locate me, etc.), dismissal branches in touch and drawer flows failed to invoke `TOOLTIP.hidden = true`. Because DOM state is stateful and decoupled from the application's logical selection state, the tooltip element remained rendered in the browser at its last coordinate, permanently overlapping the coalition legend.

### The React Structural Solution
In the React prototype (`map-react/`):
```jsx
// Single source of truth in App.jsx
const [selectedSeat, setSelectedSeat] = useState(null);

// Tooltip is a pure projection of selectedSeat
export function SeatTooltip({ seat, anchorPos }) {
  if (!seat) return null; // React unmounts DOM node completely
  return <div id="tooltip">...</div>;
}
```
There is **no imperative hiding call**. There is **no separate `isTooltipVisible` flag**.
When any of the four dismiss pathways trigger:
1. **Tap elsewhere** (outside click) → `setSelectedSeat(null)`
2. **Tap another seat** → `setSelectedSeat(newCode)` (synchronous transition)
3. **Press Escape** → `setSelectedSeat(null)`
4. **Close panel (✕)** → `setSelectedSeat(null)`

Because `selectedSeat` becomes `null`, React unmounts the `#tooltip` element from the DOM entirely. It is **structurally impossible** for the tooltip to remain rendered when the seat detail panel is closed or unselected.

---

## 2. Is it Still Possible to Leave State Stuck in React?

**Yes, if you commit the dual-state anti-pattern.**

If a developer writes:
```jsx
// ANTI-PATTERN: Dual independent flags
const [selectedSeat, setSelectedSeat] = useState(null);
const [isTooltipOpen, setIsTooltipOpen] = useState(false);

const handleClosePanel = () => {
  setSelectedSeat(null);
  // FORGOT: setIsTooltipOpen(false); -> Recreates the exact same bug!
};
```
In this scenario, React does not automatically save you from orphaned UI.

However, React provides two strong cultural and mechanical safeguards that vanilla DOM scripts lack:
1. **Derived State Idiom**: React linters, code reviews, and idiomatic component design strongly discourage redundant booleans when one value (`selectedSeat !== null`) fully implies the other.
2. **Component Lifecycle Teardown**: When a parent unmounts an island or clears a selected object, all child lifecycle nodes and DOM subtrees are pruned automatically without requiring explicit cleanup across 15 different event listeners.

### React-Specific Pitfalls to Watch For
- **Portals without unmount gates**: If using `createPortal(..., document.body)` for tooltips, forgetting to wrap the portal in `if (!selectedSeat) return null;` leaves orphaned elements in `document.body`.
- **Global event listener stale closures**: For Escape key listeners, omitting `[selectedSeat]` from the `useEffect` dependency array captures a stale `selectedSeat` value, causing the listener to no-op. (In our prototype, this is handled via clean `useEffect` lifecycle bindings).

---

## 3. Architecture Assessment: Full Migration vs. Island Architecture

| Approach | Bundle Impact | Rendering Performance (222 Seats) | State Predictability | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **A. Vanilla JS (Status Quo)** | 0 kB framework overhead | Fast DOM diffing, but 9.5k lines of imperative entanglement | High bug rate (pinned tooltips, race conditions) | High maintenance burden |
| **B. Full React Rewrite** | +42 kB (React + ReactDOM) | High risk of re-render lag on vector map pan/zoom without heavy memoization | High | High risk, unnecessary for vector SVG |
| **C. React Island Hybrid (Recommended)** | +42 kB (or ~4 kB with Preact) | **Best**: SVG map stays raw DOM / canvas at 60fps; UI panels & overlays use declarative state | **Best**: Eliminates dismiss & modal bugs completely | **Optimal Path** |

### Recommendation
If the team moves forward with React on the map, adopt **Option C (Island Architecture)**:
- Leave the heavy SVG projection and pan/drag engine in vanilla JS / lightweight canvas emitting custom DOM events (`seat:select`, `seat:dismiss`).
- Mount a React root solely over the overlay layer (the seat spotlight bento tile, the inspect tray, and tooltips).
- Both components consume a unified `selectedSeat` state, eliminating the pinned-tooltip bug permanently.

---

## 4. Verification Checklist

Run locally:
```bash
npm --prefix map-react install
npm --prefix map-react run dev
```
Open `http://localhost:5184` and verify the 4 dismiss pathways on the live audit panel:
- [x] **Path 1**: Click a seat, then click outside anywhere on the background. (Both dismiss)
- [x] **Path 2**: Click a seat, then click a different seat. (Synchronous switch, no ghost tooltips)
- [x] **Path 3**: Click a seat, press the `Escape` key. (Both dismiss)
- [x] **Path 4**: Click a seat, click the `✕` close button on the seat spotlight card. (Both dismiss)
- [x] **Mobile simulation**: Switch toggle to "Mobile View (390px)" to verify touch/drawer dismiss behavior.
