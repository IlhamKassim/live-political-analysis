# Serve the public page as static HTML, and keep Streamlit as the internal view

The public dashboard (#17) is a designed page — full-bleed hemicycle, a custom
type pairing, hairline rules, a press-grain overlay, a theme toggle. The
question was whether to rebuild it Streamlit-native inside the existing app or
publish it as a static file.

Decision: a renderer reads the same Storage and writes an HTML file, and the
daily GitHub Action gains a step that renders and publishes it. Hosting must
satisfy [ADR 0002](0002-zero-cost-self-hosted-sentiment-stack.md)'s zero-cost
rule; GitHub Pages is the expected answer, in the repository that already runs
the Action.

The page is read-only, updates once a day and needs no server-side
interactivity — which is the whole of what Streamlit provides. Its costs here
are not hypothetical:

- Custom markup goes through `components.html`, which lands in a sandboxed
  iframe with a fixed height and its own scrollbar. A full-bleed hero does not
  survive that.
- Streamlit ships its own theme toggle, which collides with the page's.
- Community Cloud apps sleep, and a first hit after that takes roughly thirty
  seconds — on a page whose credibility rests on looking considered.
- A public Streamlit app holds a live connection to the free-tier Postgres, so
  traffic reaches the database.

Static removes all four. It also means the database is only ever touched by the
Action, so public traffic cannot exhaust a free-tier connection limit, and the
page cannot be down because a host slept.

The trade-off accepted is that anything genuinely interactive — filtering,
drill-down, a date scrubber — is out of reach without client-side code and a
data file to go with it. Nothing on this page needs that today. Hover and
keyboard affordances on the chamber are plain HTML and are unaffected.

`src/lpa/dashboard.py` stays exactly as it is: the internal view, where the
Sentiment series, the Poll Calibration comparison and the trend line live. It is
not deleted, not redesigned, and not the thing being published. Two surfaces
over one Storage, with different audiences — the public page states one day's
Projection, the Streamlit app is for looking at how it moved and why.
