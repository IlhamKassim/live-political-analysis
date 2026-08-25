/* Live figures: enriches /learn definitions with today's projected numbers,
   read client-side from /projection.json (public_export.py, #46). Vanilla
   JS, no build step — the same pattern as register-a.js's initThemeToggle,
   kept in a separate file because it is not about theming and not every
   /learn page needs it (#56).

   Hard requirement (#56): the page must render exactly as it does today
   without this script running — fetch failure, JS disabled, or the file
   missing. Every hook element this targets ships empty in the HTML, so
   catch() below leaves it empty rather than showing an error, and nothing
   else on the page depends on this having run.

   Only Majority gets a live figure for now, per #56's scope note: force
   this everywhere and every term reads as a dashboard mirror instead of a
   glossary; Majority is the one case the issue names as genuinely live. */

var GOVERNMENT_COALITIONS = ["PH", "BN", "GPS", "GRS"];
var MAJORITY_THRESHOLD = 112;

function initLiveMajority() {
  var el = document.querySelector("[data-live-majority]");
  if (!el) return;

  fetch("../projection.json")
    .then(function (res) {
      if (!res.ok) throw new Error("projection.json: " + res.status);
      return res.json();
    })
    .then(function (data) {
      var totals = (data && data.coalition_seat_totals) || {};
      var seats = 0;
      GOVERNMENT_COALITIONS.forEach(function (code) {
        if (typeof totals[code] === "number") seats += totals[code];
      });
      /* MAJORITY_THRESHOLD, GOVERNMENT_COALITIONS above, and Dewan
         Rakyat's 222 Seats are the same facts the glossary text around
         this hook already states and cites — not new claims, just the
         arithmetic those facts support.

         Cross-check against the export's own `government_majority` bool
         rather than trusting GOVERNMENT_COALITIONS blindly: that list is
         hand-maintained here because the export doesn't carry the
         pipeline's `government_coalitions` config, so if the two ever
         disagree, the safer failure is to say nothing (the same
         no-JS/fetch-failure degrade this file already guarantees) rather
         than publish a seat count that may not match the pipeline's own
         Majority call. */
      var overMajority = seats >= MAJORITY_THRESHOLD;
      if (overMajority !== !!data.government_majority) return;

      /* Phrasing matches public_page.py's lede()/_stress(): "The
         Government Coalition is projected ... seats ..." — arithmetic
         framing, never "will win" or "wins". A sentence, not a dash
         fragment glued onto the claim span's own full stop. */
      el.textContent =
        " Today, the Government Coalition is projected at " +
        seats +
        " seats.";
    })
    .catch(function () {
      /* Leave the hook empty. No error UI: a reader with JS on but a
         failed fetch (offline, missing file, CORS) sees the same prose
         as a reader with JS off. */
    });
}
