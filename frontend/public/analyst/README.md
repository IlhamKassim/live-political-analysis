# PolitikKu Analyst, Direction B

Instrument Console. Standalone HTML, CSS and GSAP/ScrollTrigger 3.13.0. Direction A has not been started.

## Preview

From the repository root:

```sh
python3 -m http.server 4178 --bind 127.0.0.1 --directory scrollcraft/builds/analyst-b
```

Open http://127.0.0.1:4178/. All fonts and animation dependencies are local. No build step, account, API or recurring service is required.

## Design

The hero opens three glass plates while its dial and slider move with scrolling. A second pinned section changes between the Swing-model sandbox, source-level sentiment drill-down, and full data export. The short statement between them reveals with scroll.

All three features are marked In pilot. The console is explicitly an illustration, with no live data, Projection calculation, download, subscription or signup. The functional range control changes only the illustration.

At widths of 900px and below, the instrument illustrations sit directly beneath their feature descriptions in normal document flow. Reduced-motion preference and the footer motion button also remove pinning and show every feature. Without JavaScript, the content remains readable.

## References

- https://politikku.my/ inspected live on 10 September 2026. Uses the existing mark, Space/Plex fonts, #101E23 ink, cream/lime palette, and ↗ links. Extends “A nation. In perspective.”
- https://politikku.my/methodology.html inspected live on 10 September 2026. Supports the distinction between the GE15 Baseline and modelled output, provisional constants, and state-uniform Swing.
- https://aiautomationsociety.ai/ inspected live and scrolled. The technique reference was its transition through foreground/background layers into an interface. No branding, copy, imagery, testimonials or customer claims were copied.

## Verification

Browser review completed in Chrome through the live local server:

- Screenshot pass: hero, opened layers, all three console states, methodology, closing section, and mobile hero/feature.
- Two pin spacers on desktop; none in motion-off/mobile mode.
- Hero assembly and dial transforms change with scroll.
- All three chapters appear when scrolling forward. Reverse scrolling restores the previous chapter.
- Chapter links navigate to the intended scroll positions.
- Keyboard ArrowRight updates the illustrative slider and displayed value.
- Hidden animated panels are inert, preventing focus on hidden links and inputs.
- Motion-off shows all three chapters with their illustrations; resume restores animation.
- No horizontal overflow at 375, 390, 768, 1024 and default 1470px widths.
- No browser console errors or warnings observed.
- The initial screenshot review found a pinned container alignment issue and a short-viewport height issue. Both were corrected and reviewed again at 1470 × 669.
- `.venv/bin/pytest`: 644 passed, 9 deselected. Required local socket access for the existing prerender-server test.
- `.venv/bin/ruff check`: passed.
- `.venv/bin/mypy`: passed, 39 source files.

These repository checks cover the existing Python application. The new static concept was verified through the browser interactions and screenshot review above.
