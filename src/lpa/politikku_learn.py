import argparse
from datetime import date
from pathlib import Path

from lpa.config import load_election_status
from lpa.domain import ElectionStatus
from lpa.politikku_shell import Language, render_shell

_LEARN_BASE_CSS = """
  .pk-learn-container { max-width: 720px; margin: 0 auto; padding: 2rem var(--gutter-mobile); }
  @media (min-width: 900px) { .pk-learn-container { padding: 4rem var(--gutter-desktop); } }

  :target { scroll-margin-top: 24px; }

  .opening {
    margin-bottom: clamp(24px, 4vw, 40px);
  }
  .pk-eyebrow {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--ink-secondary);
  }
  .opening h1 {
    font-family: var(--serif);
    font-weight: 500;
    font-size: clamp(32px, 4.5vw, 44px);
    letter-spacing: -.02em;
    margin: 8px 0 0;
  }
  .lede {
    font-family: var(--serif);
    font-size: 17px;
    line-height: 1.62;
    color: var(--ink-secondary);
    max-width: 64ch;
    margin: 12px 0 0;
  }
  .toc {
    list-style: none;
    padding: 0;
    margin: 20px 0 0;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .toc li { margin: 0; }
  .toc a {
    display: inline-block;
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: .04em;
    color: var(--ink-secondary);
    text-decoration: none;
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    padding: 4px 10px;
  }
  .toc a:hover {
    color: var(--ink);
    border-color: var(--ink-secondary);
  }
  .prose p {
    font-family: var(--serif);
    font-size: 17px;
    line-height: 1.62;
    color: var(--ink);
    margin: 0 0 1em;
  }
  .prose p:last-child { margin-bottom: 0; }
  .prose p a {
    color: inherit;
    border-bottom: 1px solid var(--line);
    text-decoration: none;
  }
  .prose p a:hover {
    border-bottom-color: var(--ink-secondary);
  }
  .gloss {
    font-family: var(--serif);
    font-style: italic;
    color: var(--ink-secondary);
    font-size: 15px;
    margin: 0 0 14px;
  }
""".strip()

_GLOSSARY_CSS = f"""{_LEARN_BASE_CSS}

  .term-entry {{ padding: clamp(34px, 5vw, 56px) 0 0; border-top: 1px solid var(--line-soft); }}
  .opening + .term-entry {{ border-top: none; }}
  .term-entry h2 {{
    font-family: var(--serif);
    font-weight: 500;
    font-size: clamp(26px, 3.4vw, 36px);
    letter-spacing: -.015em;
    margin: 0 0 4px;
  }}
  .sub-term {{
    margin-top: clamp(22px, 3.5vw, 34px);
    padding-left: clamp(16px, 2.5vw, 26px);
    border-left: 2px solid var(--line);
  }}
  .sub-term h3 {{
    font-family: var(--mono);
    font-size: 11.5px;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--ink-secondary);
    margin: 0 0 10px;
  }}
""".strip()

_GLOSSARY_BODY = """
<main class="pk-learn-container">
<section class="opening">
    <div class="pk-eyebrow">What the projection assumes you know</div>
    <h1>Core terms</h1>
    <p class="lede">
      This page explains, in plain prose, the terms the GE16 projection
      uses throughout: what a Seat and a Majority are, where Sentiment
      comes from, how a Swing turns into a Projection, and what Election
      Status means. Each definition here is a plain-language restatement
      of this project's own glossary in <code>CONTEXT.md</code>, not a new
      claim about Malaysian politics.
    </p>
    <ul class="toc">
      <li><a href="#term-coalition">Coalition</a></li>
      <li><a href="#term-seat">Seat</a></li>
      <li><a href="#term-majority">Majority &amp; government</a></li>
      <li><a href="#term-baseline">Baseline</a></li>
      <li><a href="#term-sentiment">Sentiment</a></li>
      <li><a href="#term-swing">Swing</a></li>
      <li><a href="#term-projection">Projection</a></li>
      <li><a href="#term-election-status">Election Status</a></li>
    </ul>
  </section>

  <section class="prose term-entry" id="term-coalition">
    <h2>Coalition</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">a group of parties that contests and governs together</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A Coalition is a group of parties that contests and governs together.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The five Coalitions this site tracks are PH, BN, PN, GPS and GRS.</span>
      For how each of the five came to exist, including founding dates,
      member parties, and the splits and mergers behind them, see the
      <a href="coalitions.html">Coalitions page</a>.
    </p>
  </section>

  <section class="prose term-entry" id="term-seat">
    <h2>Seat</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">the unit an election is won or lost in</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The Dewan Rakyat has 222 Seats. "Seats" is the term this site uses for what are otherwise called parliamentary constituencies.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A Seat is the unit an election is actually won or lost in.</span>
    </p>
  </section>

  <section class="prose term-entry" id="term-majority">
    <h2>Majority, Government and Non-government</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">the threshold a Coalition needs to form government alone</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A Majority means holding more than half of the Dewan Rakyat's 222 Seats, that is 112 or more.</span><span data-live-majority></span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A Majority is the threshold a Coalition needs to form government on its own.</span>
    </p>

    <div class="sub-term">
      <h3>Government Coalition</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The Government Coalition, the current governing bloc, is made up of PH, BN, GPS and GRS together with minor parties.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The Government Coalition holds the Majority, as of the most recent count in the Dewan Rakyat.</span>
      </p>
    </div>

    <div class="sub-term">
      <h3>Non-government</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Non-government means every Seat or Coalition outside the Government Coalition.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">PN is the opposition, but WARISAN, KDM, PBM and independents are neither in the Government Coalition nor in opposition to it.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Calling those parties "opposition" would assert a political alignment they have not declared.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">This site's chamber of Seats runs along a single axis, from the safest Government Seat to the safest Non-government Seat.</span>
      </p>
    </div>
  </section>

  <section class="prose term-entry" id="term-baseline">
    <h2>Baseline</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">the fixed starting point every Projection is computed from</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A Seat's Baseline is its GE15 (2022) result and demographic profile: vote share, margin, and the ethnicity and age breakdown of its voters.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The Baseline is the fixed starting point every Projection is computed from.</span>
    </p>
  </section>

  <section class="prose term-entry" id="term-sentiment">
    <h2>Sentiment</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">the measured public political mood, derived from two sources</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Sentiment captures the measured public political mood, tagged per Coalition or party.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Sentiment draws on two sources: continuous News Sentiment and periodic Poll Calibration.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Sentiment is an input signal the Swing Model consumes.</span>
    </p>

    <div class="sub-term">
      <h3>News Sentiment</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">News Sentiment is computed with an open-source, self-hosted multilingual sentiment model that runs as local CPU inference, with no external API.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">News Sentiment draws on headlines and articles scraped from major Malaysian outlets, in both English and Bahasa Malaysia: FMT, Malay Mail, NST, The Star, The Vibes, Sinar Daily, Bernama, Berita Harian and Utusan Malaysia.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">News Sentiment is the continuous, day-to-day component of Sentiment.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md" id="claim-26">News Sentiment is zero-cost by default, not requirement.</span>
      </p>
    </div>

    <div class="sub-term">
      <h3>Poll Calibration</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Poll Calibration comes from Merdeka Center's periodically published survey results, such as approval ratings.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">When a new report drops, Poll Calibration is ingested to sanity-check News Sentiment against real survey data.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Poll Calibration is not continuous, but there is no API for it, so reports appear only every few months.</span>
      </p>
    </div>
  </section>

  <section class="prose term-entry" id="term-swing">
    <h2>Swing</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">derived from Sentiment, applied against the Baseline</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Swing measures the estimated shift in vote or seat share for a Coalition.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Derived from Sentiment, Swing is applied against the Baseline.</span>
    </p>

    <div class="sub-term">
      <h3>State Election Signal</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A State Election Signal comes from results of state elections held before GE16, such as the 2026 Johor and Malacca elections.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A State Election Signal is a leading-indicator input into the Swing Model.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A State Election Signal is distinct from the Baseline, which stays fixed at the GE15 federal results.</span>
      </p>
    </div>

    <div class="sub-term">
      <h3>Swing Model</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The Swing Model is the method for turning Sentiment into a per-Seat or per-Coalition Swing.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The Swing Model applies a uniform Swing within each state, with a State Election Signal blended in for the state that voted.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The Swing Model is the hard, research-grade part of this project, distinct from the Baseline, which is simply historical fact.</span>
      </p>
    </div>
  </section>

  <section class="prose term-entry" id="term-projection">
    <h2>Projection</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">the tool's output: a seat-count estimate per Coalition</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A Projection is the tool's output: a seat-count estimate per Coalition for GE16.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A Projection states whether the Government Coalition is projected to retain its Majority.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A Projection includes the Seat-Level Projection behind both of those figures.</span>
    </p>

    <div class="sub-term">
      <h3>Seat-Level Projection</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The Seat-Level Projection is the Coalition each of the 222 Seats is projected to fall to, with the projected margin, alongside the aggregate totals.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Because the Swing Model is uniform within a state and carries no Seat-specific signal, a Seat's call is arithmetic against its GE15 margin; it is never a bespoke judgement about that particular constituency, and it must not be presented as one.</span>
      </p>
    </div>

    <div class="sub-term">
      <h3>Seat Call</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">A Seat Call is one Seat's entry in the Seat-Level Projection: the Coalition projected to take it and the projected margin over the runner-up.</span>
      </p>
    </div>
  </section>

  <section class="prose term-entry" id="term-election-status">
    <h2>Election Status</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">context for reading a Projection, not an input to one</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Election Status tracks whether GE16 has been called yet, and the polling date once one is set.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">"Called" means the Dewan Rakyat has been dissolved, the act that starts a Malaysian general election.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The Election Commission announces the polling date after dissolution, so a general election can be called with no polling date set yet, which is a real state rather than missing information.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Election Status is context for reading a Projection, not an input that feeds into one.</span>
    </p>
  </section>
</main>
<script>
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

initLiveMajority();
</script>
""".strip()


def build_glossary_page(language: Language, updated_at: date, status: ElectionStatus) -> str:
    return render_shell(
        title="Core terms: reading this site | PolitikKu",
        description="A glossary of the terms this site's GE16 projection uses: Seat, Majority, Government, Sentiment, Swing, Projection and more, explained in plain prose for a reader with no prior background.",
        active_nav="glossary",
        language=language,
        page_path="learn/glossary.html",
        updated_at=updated_at,
        sources_count=0,
        status=status,
        body_html=f"<style>{_GLOSSARY_CSS}</style>\n{_GLOSSARY_BODY}",
        prefix="/",
    )


_COALITIONS_CSS = f"""{_LEARN_BASE_CSS}

  .coalition {{
    padding: clamp(34px, 5vw, 56px) 0 0;
    border-top: 1px solid var(--line-soft);
  }}
  .opening + .coalition {{ border-top: none; }}
  .coalition h2 {{
    font-family: var(--serif);
    font-weight: 500;
    font-size: clamp(26px, 3.4vw, 36px);
    letter-spacing: -.015em;
    margin: 0 0 4px;
  }}
  /* The abbreviation carries the coalition's ink, the
     same one the dashboard's chamber uses for that Coalition's Seats. */
  .coalition h2 .abbr {{ color: var(--ink-secondary); border-color: var(--line);
    font-family: var(--mono);
    font-size: .5em;
    letter-spacing: .08em;
    vertical-align: .35em;
    margin-left: 10px;
    padding: 2px 7px;
    border: 1px solid currentColor;
  }}

  /* The four structural facts, as a definition list rather than prose —
     they are the part of a Coalition profile a reader scans for. */
  .facts {{
    margin: 0 0 clamp(18px, 3vw, 28px);
    padding: 16px 0 4px;
    border-top: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
    display: grid;
    grid-template-columns: minmax(120px, 170px) 1fr;
    gap: 0;
  }}
  .facts dt {{
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--muted);
    padding: 0 16px 12px 0;
  }}
  .facts dd {{
    font-family: var(--serif);
    font-size: 15.5px;
    line-height: 1.45;
    color: var(--ink);
    margin: 0;
    padding: 0 0 12px;
  }}

  .sub-term {{
    margin-top: clamp(22px, 3.5vw, 34px);
    padding-left: clamp(16px, 2.5vw, 26px);
    border-left: 2px solid var(--line);
  }}
  .sub-term h3 {{
    font-family: var(--mono);
    font-size: 11.5px;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--ink-secondary);
    margin: 0 0 10px;
  }}

  @media (max-width: 560px) {{
    .facts {{ grid-template-columns: 1fr; }}
    .facts dt {{ padding-bottom: 4px; }}
    .facts dd {{ padding-bottom: 16px; }}
  }}
""".strip()

_COALITIONS_BODY = """
<main class="pk-learn-container">
<section class="opening">
    <div class="pk-eyebrow">Who the projection is projecting</div>
    <h1>The five Coalitions</h1>
    <p class="lede">
      Every seat count on this site is reported per Coalition. This page
      says what each of the five is and how it came to exist: founding
      dates, the parties inside it, and the splits and mergers that
      produced it. It is a structural account only: it records what was
      formed, when, and out of which parties, and it leaves the question
      of <em>why</em> to the sources it cites.
    </p>
    <ul class="toc">
      <li><a href="#what-is-a-coalition">What a Coalition is</a></li>
      <li><a href="#ph">PH</a></li>
      <li><a href="#bn">BN</a></li>
      <li><a href="#pn">PN</a></li>
      <li><a href="#gps">GPS</a></li>
      <li><a href="#grs">GRS</a></li>
      <li><a href="#why-five">Why five</a></li>
    </ul>
  </section>

  <section class="prose coalition" id="what-is-a-coalition">
    <h2>What a Coalition is</h2>
    <p class="gloss">the unit this site counts Seats in</p>
    <p>
      <span data-claim id="coalition-definition" data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">On this site, a Coalition means a group of parties that contests and governs together.</span>
      <span data-claim id="coalition-five" data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The five Coalitions this site tracks are PH, BN, PN, GPS and GRS.</span>
      A Coalition is not a single party. Each of the five below is an
      agreement among parties that keep their own names, memberships and
      officers, and the profiles on this page describe those parties and
      the agreements that bind them, not what any of them believes or
      wants.
    </p>
    <p>
      Why there are five rather than three, and what separates two of them
      from the other three, is set out under
      <a href="#why-five">Why five</a> below.
    </p>
  </section>

  <section class="prose coalition" id="ph">
    <h2>Pakatan Harapan <span class="abbr">PH</span></h2>
    <p class="gloss">formed 2015, to succeed an earlier coalition</p>
    <dl class="facts">
      <dt>Founded</dt>
      <dd data-claim id="ph-founded" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan was founded on 22 September 2015.</dd>
      <dt>Registered</dt>
      <dd data-claim id="ph-legalised" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan was legalised on 16 May 2018.</dd>
      <dt>Formed from</dt>
      <dd data-claim id="ph-predecessor" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan's predecessor was the Pakatan Rakyat coalition, which it was formed to succeed.</dd>
      <dt>Component parties</dt>
      <dd data-claim id="ph-members" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan's member parties are PKR, DAP and AMANAH.</dd>
    </dl>
    <p>
      <span data-claim id="ph-succession" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan is a Malaysian political coalition which was formed in 2015 to succeed the Pakatan Rakyat coalition.</span>
      <span data-claim id="ph-gov-2018" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan led a single-coalition government from May 2018 to February 2020.</span>
      <span data-claim id="ph-gov-2022" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan has led a grand coalition government since November 2022.</span>
    </p>
  </section>

  <section class="prose coalition" id="bn">
    <h2>Barisan Nasional <span class="abbr">BN</span></h2>
    <p class="gloss">formed 1974, out of a coalition two decades older</p>
    <dl class="facts">
      <dt>Founded</dt>
      <dd data-claim id="bn-founded" data-cite="https://en.wikipedia.org/wiki/Barisan_Nasional?action=raw">Barisan Nasional was founded on 1 June 1974.</dd>
      <dt>Formed from</dt>
      <dd data-claim id="bn-predecessor" data-cite="https://en.wikipedia.org/wiki/Barisan_Nasional?action=raw">Barisan Nasional's predecessor was the Alliance Party.</dd>
      <dt>Component parties</dt>
      <dd data-claim id="bn-members" data-cite="https://en.wikipedia.org/wiki/Barisan_Nasional?action=raw">Barisan Nasional's member parties are UMNO, MCA, MIC, PBRS and PPP.</dd>
      <dt>Later split</dt>
      <dd data-claim id="bn-successor" data-cite="https://en.wikipedia.org/wiki/Barisan_Nasional?action=raw">Barisan Nasional's successor in Sarawak, from 2018, is Gabungan Parti Sarawak.</dd>
    </dl>
    <p>
      <span data-claim id="bn-founding" data-cite="https://en.wikipedia.org/wiki/Barisan_Nasional?action=raw">Barisan Nasional was founded in 1974 to succeed the Alliance Party, and first competed in the general election of that year.</span>
      Unlike the other four Coalitions on this page, Barisan Nasional's
      source gives no registration date distinct from its founding. It
      continued on from the Alliance Party's own registration rather than
      registering fresh, the way GPS, PN and GRS each did. That is why its
      fact table above has no Registered row.
    </p>

    <div class="sub-term">
      <h3>The Alliance Party, 1952–1974</h3>
      <p>
        <span data-claim id="alliance-members" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">The Alliance Party's membership comprised UMNO, MCA and MIC.</span>
        <span data-claim id="alliance-origin" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">The Alliance Party originated in a temporary electoral arrangement between local branches of UMNO and MCA to contest the Kuala Lumpur municipal election in 1952.</span>
        <span data-claim id="alliance-mic" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">MIC joined the alliance of UMNO and MCA in 1954.</span>
        <span data-claim id="alliance-registered" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">The Alliance Party was informally founded in 1952 and formally registered as a political organisation on 30 October 1957.</span>
      </p>
      <p>
        <span data-claim id="alliance-1971" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">Negotiations with former opposition parties began after the Malaysian Parliament reconvened in 1971.</span>
        <span data-claim id="alliance-expansion" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">Gerakan and the People's Progressive Party both joined the Alliance Party in 1972, quickly followed by PMIP.</span>
        <span data-claim id="alliance-to-bn" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">The Alliance Party was the ruling coalition of Malaya from 1957 to 1963 and of Malaysia from 1963 to 1974, and became known as Barisan Nasional in 1974.</span>
      </p>
    </div>
  </section>

  <section class="prose coalition" id="pn">
    <h2>Perikatan Nasional <span class="abbr">PN</span></h2>
    <p class="gloss">formed February 2020, registered that August</p>
    <dl class="facts">
      <dt>Founded</dt>
      <dd data-claim id="pn-founded" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional was founded on 29 February 2020.</dd>
      <dt>Registered</dt>
      <dd data-claim id="pn-registered" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional was registered on 7 August 2020.</dd>
      <dt>Split from</dt>
      <dd data-claim id="pn-split" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional split from Pakatan Harapan and Gagasan Sejahtera.</dd>
      <dt>At registration</dt>
      <dd data-claim id="pn-at-registration" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">As a formal coalition, Perikatan Nasional consisted of BERSATU, PAS and STAR at the time of its registration in August 2020.</dd>
    </dl>
    <p>
      <span data-claim id="pn-informal" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">According to Wikipedia's account, and as an informal coalition, Perikatan Nasional was formed by BERSATU, PAS, Barisan Nasional, Gabungan Parti Sarawak and STAR at the beginning of the 2020–2022 Malaysian political crisis.</span>
      <span data-claim id="pn-muhyiddin" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional's de facto leader Muhyiddin Yassin was sworn in as the 8th Prime Minister of Malaysia on 1 March 2020.</span>
      <span data-claim id="pn-govt" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional formed a coalition government with Barisan Nasional, Gabungan Parti Sarawak, Gabungan Rakyat Sabah and other political parties, which ruled from 2020 to 2022.</span>
    </p>
    <p>
      <span data-claim id="pn-accessions" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional was expanded to include SAPP in August 2020, GERAKAN in February 2021, and the Malaysian Indian People's Party in April 2024.</span>
      Those accessions are the ones the cited source records; PN's formal
      membership has continued to change since. A reader checking which
      parties sit inside PN today should read the cited source directly
      rather than treat this page as current on that point.
    </p>
  </section>

  <section class="prose coalition" id="gps">
    <h2>Gabungan Parti Sarawak <span class="abbr">GPS</span></h2>
    <p class="gloss">formed 2018, when four parties left BN</p>
    <dl class="facts">
      <dt>Founded</dt>
      <dd data-claim id="gps-founded" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak was founded on 12 June 2018.</dd>
      <dt>Registered</dt>
      <dd data-claim id="gps-legalised" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak was legalised on 19 November 2018.</dd>
      <dt>Split from</dt>
      <dd data-claim id="gps-split" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak split from Barisan Nasional.</dd>
      <dt>Component parties</dt>
      <dd data-claim id="gps-members" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak's member parties are PBB, PDP, SUPP and PRS.</dd>
    </dl>
    <p>
      <span data-claim id="gps-formation" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">GPS was formed on 12 June 2018, consisting of Parti Pesaka Bumiputera Bersatu, the Progressive Democratic Party, the Sarawak United Peoples' Party and Parti Rakyat Sarawak.</span>
      <span data-claim id="gps-from-bn" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">According to Wikipedia's account, Gabungan Parti Sarawak was established in 2018 by four former Barisan Nasional component parties operating solely in Sarawak, following the federal coalition's defeat in the 2018 Malaysian general election.</span>
      <span data-claim id="gps-sarawak-govt" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak forms the government in the state of Sarawak.</span>
    </p>
  </section>

  <section class="prose coalition" id="grs">
    <h2>Gabungan Rakyat Sabah <span class="abbr">GRS</span></h2>
    <p class="gloss">formed 2020 as an alliance, registered as a coalition in 2022</p>
    <dl class="facts">
      <dt>Founded</dt>
      <dd data-claim id="grs-founded" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah was established in September 2020, when Hajiji Noor set up an informal alliance of that name.</dd>
      <dt>Registered</dt>
      <dd data-claim id="grs-legalised" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah was legalised on 11 March 2022.</dd>
      <dt>Formed from</dt>
      <dd data-claim id="grs-predecessor" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah's predecessor was Gabungan Bersatu Sabah, the United Alliance of Sabah.</dd>
      <dt>Component parties</dt>
      <dd data-claim id="grs-members" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah's member parties are GAGASAN, PBS, UPKO, PHRS, LDP and PCS.</dd>
    </dl>
    <p>
      <span data-claim id="grs-sabah-based" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah is a Malaysian coalition of Sabah-based parties.</span>
      <span data-claim id="grs-established" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah was established in 2020 and then registered in 2022 by former component parties of the United Alliance of Sabah and the United Borneo Alliance, operating solely in Sabah.</span>
      <span data-claim id="grs-gps-formula" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">According to Wikipedia's account, Gabungan Rakyat Sabah was formed inspired by the formula of the Sarawak-based coalition Gabungan Parti Sarawak.</span>
    </p>
    <p>
      <span data-claim id="grs-upko" data-cite="https://www.malaymail.com/news/malaysia/2026/06/18/upko-joins-grs-expanding-sabah-ruling-coalition-to-six-parties/224325">Malay Mail reported that on 18 June 2026 Gabungan Rakyat Sabah officially accepted the United Progressive Kinabalu Organisation as its newest component party, expanding the Sabah ruling coalition to six parties.</span>
      That accession is why the component-party list above runs to six.
    </p>
  </section>

  <section class="prose coalition" id="why-five">
    <h2>Why five</h2>
    <p class="gloss">three federal Coalitions, two Borneo ones</p>
    <p>
      The count is five because two of the Coalitions are constituted for
      a single state each.
      <span data-claim id="why-gps-sarawak" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak is a Sarawak-based political alliance whose four founding parties operated solely in Sarawak.</span>
      <span data-claim id="why-grs-sabah" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah is a Malaysian coalition of Sabah-based parties.</span>
      Each is recorded above with the date it was formed and the parties
      that formed it.
    </p>
    <p>
      That is a structural distinction, not a claim about what any of these
      parties want. GPS is constituted for Sarawak and GRS for Sabah; the
      other three are not constituted for a single state.
      <span data-claim id="why-222-seats" data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">The Dewan Rakyat has 222 Seats.</span>
      Sarawak and Sabah each return their own share of those 222. A
      projection that ignored the two Borneo Coalitions would be
      projecting a chamber that does not exist, which is why this site
      counts five rather than three.
    </p>
  </section>
</main>

""".strip()


def build_coalitions_page(language: Language, updated_at: date, status: ElectionStatus) -> str:
    return render_shell(
        title="The five Coalitions: reading this site | PolitikKu",
        description="What a Coalition is in Malaysian politics, and how each of the five this site tracks, PH, BN, PN, GPS and GRS, was formed: founding dates, component parties, and the splits and mergers behind them, each traced to a cited source.",
        active_nav="coalitions",
        language=language,
        page_path="learn/coalitions.html",
        updated_at=updated_at,
        sources_count=0,
        status=status,
        body_html=f"<style>{_COALITIONS_CSS}</style>\n{_COALITIONS_BODY}",
        prefix="/",
    )


_PROCESS_CSS = f"""{_LEARN_BASE_CSS}

  .step {{
    position: relative;
    padding: clamp(30px, 5vw, 48px) 0 clamp(30px, 5vw, 48px) clamp(52px, 8vw, 76px);
    border-top: 1px solid var(--line-soft);
  }}
  .opening + .step {{ border-top: none; padding-top: clamp(10px, 2vw, 18px); }}
  .step-index {{
    position: absolute;
    left: 0;
    top: clamp(32px, 5.4vw, 50px);
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: .04em;
    color: var(--muted);
    width: clamp(38px, 6vw, 56px);
    text-align: right;
    padding-right: 14px;
    border-right: 2px solid var(--line);
  }}
  .opening + .step .step-index {{ top: clamp(12px, 2.4vw, 20px); }}
  .step h2 {{
    font-family: var(--serif);
    font-weight: 500;
    font-size: clamp(26px, 3.4vw, 36px);
    letter-spacing: -.015em;
    margin: 0 0 4px;
  }}
  .states {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
    margin: clamp(24px, 4vw, 36px) 0 0;
    border-top: 2px solid var(--ink);
  }}
  .state-block {{
    padding: clamp(18px, 3vw, 26px) clamp(16px, 2.5vw, 22px);
    border-right: 1px solid var(--line);
  }}
  .state-block:last-child {{ border-right: none; }}
  .state-tag {{
    display: inline-block;
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--ink-secondary);
    border: 1px solid var(--line);
    padding: 3px 8px;
    margin: 0 0 12px;
  }}
  .state-block h3 {{
    font-family: var(--serif);
    font-weight: 400;
    font-size: 18px;
    letter-spacing: -.01em;
    margin: 0 0 10px;
  }}
  .state-block p {{
    font-family: var(--serif);
    font-size: 14.5px;
    line-height: 1.55;
    color: var(--ink);
    margin: 0 0 .9em;
  }}
  .state-block p:last-child {{ margin-bottom: 0; }}

  @media (max-width: 760px) {{
    .states {{ grid-template-columns: 1fr; }}
    .state-block {{ border-right: none; border-bottom: 1px solid var(--line); }}
    .state-block:last-child {{ border-bottom: none; }}
  }}
""".strip()

_PROCESS_BODY = """
<main class="pk-learn-container">
<section class="opening">
    <div class="pk-eyebrow">How the election actually unfolds</div>
    <h1>The GE16 process</h1>
    <p class="lede">
      This dashboard tracks three states for GE16: not called, called with
      no polling date yet, and called with a polling date set. This page
      explains the sequence behind those states, from dissolution to
      nomination to polling, and why the middle state, called but undated,
      is a real stage of the process rather than a gap in the record.
    </p>
    <ul class="toc">
      <li><a href="#step-dissolution">Dissolution</a></li>
      <li><a href="#step-nomination">Nomination</a></li>
      <li><a href="#step-polling">Polling</a></li>
      <li><a href="#the-three-states">The three states</a></li>
    </ul>
  </section>

  <section class="prose step" id="step-dissolution">
    <span class="step-index">01</span>
    <h2>Dissolution</h2>
    <p class="gloss">the act that starts a Malaysian general election</p>
    <p>
      <span data-claim data-cite="https://www.malaysianbar.org.my/legal/general_news/royal_powers_after_dissolution.html" id="dissolution-starts-it">A Malaysian general election begins with the dissolution of the Dewan Rakyat, Parliament's elected lower house, the event that opens the interim period running through to the appointment of the next elected government.</span>
      <span data-claim data-cite="https://www.malaysianbar.org.my/legal/general_news/royal_powers_after_dissolution.html" id="dissolution-two-routes">Unless elections are called prematurely, the Dewan Rakyat's five-year term simply runs its course and dissolution follows.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="dissolution-early-is-ordinary">Dissolving early is the ordinary case this project's own data notes describe, rather than the exception.</span>
    </p>
    <p>
      <span data-claim data-cite="https://www.malaysianbar.org.my/legal/general_news/royal_powers_after_dissolution.html" id="deadline-60-days">Article 55(4) of the Federal Constitution requires a general election to be held within 60 days of the Dewan Rakyat's dissolution.</span>
      <span data-claim data-cite="https://www.malaysianbar.org.my/legal/general_news/by_elections_and_the_constitution.html" id="art-55-3">The Dewan Rakyat's five-year mandate expires under Article 55(3) of the Federal Constitution.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="deadline-worked-example">Combined, the two provisions fix GE16's own deadline: the current Dewan Rakyat's first sitting was on 19 December 2022, so it dissolves automatically five years later, on 19 December 2027, if not dissolved earlier, putting the last possible date for GE16 at 17 February 2028.</span>
    </p>
  </section>

  <section class="prose step" id="step-nomination">
    <span class="step-index">02</span>
    <h2>Nomination</h2>
    <p class="gloss">where the Election Commission sets the dates dissolution itself doesn't fix</p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="dissolution-doesnt-set-dates">Dissolution does not itself fix when nomination day or polling day fall. The Election Commission of Malaysia sets and announces those separately, after dissolution has already happened.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="gap-is-typical">This project's own data notes record that gap as typically running a week or two.</span>
    </p>
    <p>
      <span data-claim data-cite="https://www.malaysianbar.org.my/article/news/legal-and-general-news/members-opinions/ge13-abiding-by-the-nomination-process" id="nomination-centres">On nomination day, candidates present their nomination papers to the returning officer for their constituency, and those papers can be rejected if they don't comply with the Elections (Conduct of Elections) Regulations.</span>
    </p>
  </section>

  <section class="prose step" id="step-polling">
    <span class="step-index">03</span>
    <h2>Polling</h2>
    <p class="gloss">where voters decide, inside the window dissolution opened</p>
    <p>
      Polling day itself falls inside the same 60-day window Article 55(4)
      sets running from dissolution (see <a href="#step-dissolution">Dissolution</a>
      above). Nomination, the campaign that follows it, and polling all
      have to land inside that one constitutional deadline. For what a
      Seat is and how many the Dewan Rakyat has, see the
      <a href="glossary.html#term-seat">glossary</a>.
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md" id="polling-not-model-input">Once a polling date is set, it is context for reading this site's Projection, not an input the Swing Model consumes.</span>
    </p>
  </section>

  <section class="prose step" id="the-three-states">
    <div class="pk-eyebrow">What the dashboard actually renders</div>
    <h2>The three states</h2>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="three-states-summary">This dashboard's Election Status is driven by three dates, when the Dewan Rakyat was dissolved, when nomination occurs, and when polling was set, and derives what it displays from which of those three dates are present.</span>
    </p>

    <div class="states">
      <div class="state-block">
        <span class="state-tag">Not called</span>
        <h3>No dissolution date</h3>
        <p>
          <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="state-not-called">Before the Dewan Rakyat is dissolved, GE16 has simply not been called, and this dashboard records no dissolution date and no polling date.</span>
          <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="state-not-called-deadline">The Dewan Rakyat continues sitting, bound only by the constitutional deadline the five-year term and the 60-day rule together set.</span>
        </p>
      </div>
      <div class="state-block">
        <span class="state-tag">Called, no polling date</span>
        <h3>Dissolved, dates not yet announced</h3>
        <p>
          <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="state-called-no-polling">Between dissolution and the Election Commission's announcement of the timetable, this dashboard records a dissolution date and no polling date.</span>
          <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="state-called-no-polling-no-guess">This dashboard leaves the polling field unset for that interval rather than filling it with a guess.</span>
        </p>
      </div>
      <div class="state-block">
        <span class="state-tag">Called, polling date set</span>
        <h3>Both dates on record</h3>
        <p>
          <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="state-called-with-polling">Once the Election Commission announces the timetable, this dashboard's record has both dates: the dissolution date set earlier, and the polling date the Commission has now announced.</span>
        </p>
      </div>
    </div>
  </section>
</main>

""".strip()


def build_process_page(language: Language, updated_at: date, status: ElectionStatus) -> str:
    return render_shell(
        title="The GE16 process: reading this site | PolitikKu",
        description="How GE16 actually unfolds, from dissolution to nomination to polling, and why 'called, no polling date yet' is a real, distinct state this dashboard tracks, not a half-filled record.",
        active_nav="process",
        language=language,
        page_path="learn/ge16-process.html",
        updated_at=updated_at,
        sources_count=0,
        status=status,
        body_html=f"<style>{_PROCESS_CSS}</style>\n{_PROCESS_BODY}",
        prefix="/",
    )


def main(*, output_dir: str = "public") -> None:
    parser = argparse.ArgumentParser(description="Render the Learn pages")
    parser.add_argument("--output-dir", default=output_dir, help="Directory to write the pages to")
    args = parser.parse_args()

    out_dir = Path(args.output_dir) / "learn"
    out_dir.mkdir(parents=True, exist_ok=True)

    status = load_election_status()
    today = date.today()  # noqa: DTZ011

    pages = [
        ("glossary.html", build_glossary_page),
        ("coalitions.html", build_coalitions_page),
        ("ge16-process.html", build_process_page),
    ]

    for page_name, builder in pages:
        for lang in [Language.EN, Language.MS]:
            lang_dir = out_dir if lang == Language.EN else Path(args.output_dir) / "ms" / "learn"
            lang_dir.mkdir(parents=True, exist_ok=True)
            out_path = lang_dir / page_name
            out_path.write_text(builder(lang, today, status), encoding="utf-8")
            print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
