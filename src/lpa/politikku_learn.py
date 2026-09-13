import argparse
from datetime import date
from pathlib import Path

from lpa.config import load_election_status
from lpa.domain import ElectionStatus
from lpa.politikku_shell import Language, render_shell, t

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
  .pk-learn-callout {
    margin: 0 0 1.6rem;
    padding: 0.9rem 1.1rem;
    border-left: 3px solid var(--accent, #d6ed9a);
    background: var(--surface-soft, #192b30);
    border-radius: 0 6px 6px 0;
    font-size: 1rem;
    line-height: 1.55;
  }
  .pk-learn-callout a { color: var(--accent, #d6ed9a); font-weight: 600; }
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
    display: inline-flex;
    align-items: center;
    min-height: 44px;
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: .04em;
    color: var(--ink-secondary);
    text-decoration: none;
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    padding: 4px 12px;
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

_GLOSSARY_BODY_EN = """
<div class="pk-learn-container">
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
</div>
""".strip()


_GLOSSARY_BODY_MS = """
<div class="pk-learn-container">
<section class="opening">
    <div class="pk-eyebrow">Apa yang unjuran ini andaikan anda tahu</div>
    <h1>Istilah teras</h1>
    <p class="lede">
      Halaman ini menerangkan, dalam bahasa yang mudah, istilah yang
      digunakan oleh unjuran PRU16 dari hujung ke hujung: apa itu Kerusi
      dan Majoriti, dari mana Sentimen datang, bagaimana Peralihan bertukar
      menjadi Unjuran, dan apa maksud Status Pilihan Raya. Setiap takrif di
      sini ialah penyataan semula dalam bahasa mudah bagi glosari projek ini
      sendiri dalam <code>CONTEXT.md</code>, bukan dakwaan baharu tentang
      politik Malaysia.
    </p>
    <ul class="toc">
      <li><a href="#term-coalition">Gabungan</a></li>
      <li><a href="#term-seat">Kerusi</a></li>
      <li><a href="#term-majority">Majoriti &amp; kerajaan</a></li>
      <li><a href="#term-baseline">Asas</a></li>
      <li><a href="#term-sentiment">Sentimen</a></li>
      <li><a href="#term-swing">Peralihan</a></li>
      <li><a href="#term-projection">Unjuran</a></li>
      <li><a href="#term-election-status">Status Pilihan Raya</a></li>
    </ul>
  </section>

  <section class="prose term-entry" id="term-coalition">
    <h2>Gabungan</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">sekumpulan parti yang bertanding dan memerintah bersama</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Gabungan ialah sekumpulan parti yang bertanding dan memerintah bersama.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Lima Gabungan yang dijejaki laman ini ialah PH, BN, PN, GPS dan GRS.</span>
      Untuk melihat bagaimana setiap satu daripada lima itu terbentuk,
      termasuk tarikh penubuhan, parti komponen, serta perpecahan dan
      percantuman di sebaliknya, lihat
      <a href="coalitions.html">halaman Gabungan</a>.
    </p>
  </section>

  <section class="prose term-entry" id="term-seat">
    <h2>Kerusi</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">unit yang menentukan menang atau kalah dalam pilihan raya</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Dewan Rakyat mempunyai 222 Kerusi. "Kerusi" ialah istilah yang digunakan laman ini bagi apa yang biasanya disebut kawasan pilihan raya parlimen.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Kerusi ialah unit yang sebenarnya menentukan sesuatu pilihan raya dimenangi atau ditewaskan.</span>
    </p>
  </section>

  <section class="prose term-entry" id="term-majority">
    <h2>Majoriti, Kerajaan dan Bukan Kerajaan</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">ambang yang diperlukan sesebuah Gabungan untuk membentuk kerajaan bersendirian</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Majoriti bermaksud memegang lebih daripada separuh daripada 222 Kerusi Dewan Rakyat, iaitu 112 atau lebih.</span><span data-live-majority></span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Majoriti ialah ambang yang diperlukan sesebuah Gabungan untuk membentuk kerajaan bersendirian.</span>
    </p>

    <div class="sub-term">
      <h3>Gabungan Kerajaan</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Gabungan Kerajaan, blok pemerintah semasa, terdiri daripada PH, BN, GPS dan GRS bersama parti-parti kecil.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Gabungan Kerajaan memegang Majoriti, setakat kiraan terkini dalam Dewan Rakyat.</span>
      </p>
    </div>

    <div class="sub-term">
      <h3>Bukan Kerajaan</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Bukan Kerajaan bermaksud setiap Kerusi atau Gabungan di luar Gabungan Kerajaan.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">PN ialah pembangkang, tetapi WARISAN, KDM, PBM dan calon bebas bukan sebahagian daripada Gabungan Kerajaan dan bukan juga pembangkang kepadanya.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Menyebut parti-parti itu sebagai "pembangkang" bermakna mengandaikan satu pendirian politik yang tidak pernah mereka isytiharkan.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Dewan Kerusi di laman ini disusun pada satu paksi tunggal, daripada Kerusi Kerajaan paling selamat hingga ke Kerusi Bukan Kerajaan paling selamat.</span>
      </p>
    </div>
  </section>

  <section class="prose term-entry" id="term-baseline">
    <h2>Asas</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">titik permulaan tetap yang menjadi kiraan setiap Unjuran</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Asas sesuatu Kerusi ialah keputusan PRU15 (2022) dan profil demografinya: peratusan undi, jidar kemenangan, serta pecahan etnik dan umur pengundinya.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Asas ialah titik permulaan tetap yang menjadi kiraan setiap Unjuran.</span>
    </p>
  </section>

  <section class="prose term-entry" id="term-sentiment">
    <h2>Sentimen</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">suasana politik awam yang diukur, diambil daripada dua sumber</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Sentimen merakam suasana politik awam yang diukur, ditandakan mengikut Gabungan atau parti.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Sentimen bersandarkan dua sumber: Sentimen Berita yang berterusan dan Penentukuran Tinjauan yang berkala.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Sentimen ialah isyarat input yang digunakan oleh Model Peralihan.</span>
    </p>

    <div class="sub-term">
      <h3>Sentimen Berita</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Sentimen Berita dikira menggunakan model sentimen berbilang bahasa yang bersumber terbuka dan dihoskan sendiri, dijalankan sebagai inferens CPU setempat, tanpa sebarang API luaran.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Sentimen Berita bersandarkan tajuk berita dan artikel yang dikutip daripada portal berita utama Malaysia, dalam bahasa Inggeris dan Bahasa Malaysia: FMT, Malay Mail, NST, The Star, The Vibes, Sinar Daily, Bernama, Berita Harian dan Utusan Malaysia.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Sentimen Berita ialah komponen Sentimen yang berterusan dari hari ke hari.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md" id="claim-26">Sentimen Berita tidak berkos secara lalai, bukan sebagai syarat.</span>
      </p>
    </div>

    <div class="sub-term">
      <h3>Penentukuran Tinjauan</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Penentukuran Tinjauan datang daripada keputusan tinjauan yang diterbitkan secara berkala oleh Merdeka Center, seperti penarafan penerimaan.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Apabila laporan baharu keluar, Penentukuran Tinjauan diambil masuk untuk menyemak kewarasan Sentimen Berita berbanding data tinjauan sebenar.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Penentukuran Tinjauan tidak berterusan, dan kerana tiada API untuknya, laporan hanya muncul setiap beberapa bulan.</span>
      </p>
    </div>
  </section>

  <section class="prose term-entry" id="term-swing">
    <h2>Peralihan</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">diterbitkan daripada Sentimen, dikenakan terhadap Asas</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Peralihan mengukur anggaran anjakan dalam peratusan undi atau kerusi bagi sesebuah Gabungan.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Diterbitkan daripada Sentimen, Peralihan dikenakan terhadap Asas.</span>
    </p>

    <div class="sub-term">
      <h3>Isyarat Pilihan Raya Negeri</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Isyarat Pilihan Raya Negeri datang daripada keputusan pilihan raya negeri yang diadakan sebelum PRU16, seperti pilihan raya Johor dan Melaka 2026.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Isyarat Pilihan Raya Negeri ialah input penunjuk awal kepada Model Peralihan.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Isyarat Pilihan Raya Negeri berbeza daripada Asas, yang kekal tetap pada keputusan persekutuan PRU15.</span>
      </p>
    </div>

    <div class="sub-term">
      <h3>Model Peralihan</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Model Peralihan ialah kaedah untuk menukarkan Sentimen menjadi Peralihan bagi setiap Kerusi atau setiap Gabungan.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Model Peralihan mengenakan Peralihan yang seragam dalam setiap negeri, dengan Isyarat Pilihan Raya Negeri digabungkan bagi negeri yang telah mengundi.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Model Peralihan ialah bahagian projek ini yang sukar dan bertaraf penyelidikan, berbeza daripada Asas, yang hanyalah fakta sejarah.</span>
      </p>
    </div>
  </section>

  <section class="prose term-entry" id="term-projection">
    <h2>Unjuran</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">hasil alat ini: anggaran jumlah kerusi bagi setiap Gabungan</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Unjuran ialah hasil alat ini: anggaran jumlah kerusi bagi setiap Gabungan untuk PRU16.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Unjuran menyatakan sama ada Gabungan Kerajaan diunjurkan mengekalkan Majoritinya.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Unjuran merangkumi Unjuran Peringkat Kerusi di sebalik kedua-dua angka itu.</span>
    </p>

    <div class="sub-term">
      <h3>Unjuran Peringkat Kerusi</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Unjuran Peringkat Kerusi ialah Gabungan yang diunjurkan memenangi setiap satu daripada 222 Kerusi, berserta jidar yang diunjurkan, di samping jumlah keseluruhan.</span>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Oleh sebab Model Peralihan adalah seragam dalam sesebuah negeri dan tidak membawa isyarat khusus bagi sesuatu Kerusi, keputusan sesuatu Kerusi ialah pengiraan berbanding jidar PRU15-nya; ia sama sekali bukan pertimbangan khusus tentang kawasan itu, dan ia tidak boleh dipersembahkan sebagai pertimbangan sedemikian.</span>
      </p>
    </div>

    <div class="sub-term">
      <h3>Seat Call</h3>
      <p>
        <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Seat Call ialah catatan satu Kerusi dalam Unjuran Peringkat Kerusi: Gabungan yang diunjurkan memenanginya dan jidar yang diunjurkan mengatasi pesaing terdekat.</span>
      </p>
    </div>
  </section>

  <section class="prose term-entry" id="term-election-status">
    <h2>Status Pilihan Raya</h2>
    <p class="gloss"><span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">konteks untuk membaca sesuatu Unjuran, bukan input kepadanya</span></p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Status Pilihan Raya menjejaki sama ada PRU16 sudah diisytiharkan, dan tarikh mengundi setelah satu ditetapkan.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">"Diisytiharkan" bermaksud Dewan Rakyat telah dibubarkan, iaitu tindakan yang memulakan pilihan raya umum Malaysia.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Suruhanjaya Pilihan Raya mengumumkan tarikh mengundi selepas pembubaran, jadi sesuatu pilihan raya umum boleh diisytiharkan tanpa tarikh mengundi ditetapkan lagi, dan itu keadaan yang sebenar, bukan maklumat yang hilang.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Status Pilihan Raya ialah konteks untuk membaca sesuatu Unjuran, bukan input yang menyuap kepadanya.</span>
    </p>
  </section>
</div>
""".strip()


_LIVE_MAJORITY_SCRIPT = """<script>
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

var LIVE_MAJORITY_PREFIX = "{prefix}";
var LIVE_MAJORITY_SUFFIX = "{suffix}";
var GOVERNMENT_COALITIONS = ["PH", "BN", "GPS", "GRS"];
var MAJORITY_THRESHOLD = 112;

function initLiveMajority() {
  var el = document.querySelector("[data-live-majority]");
  if (!el) return;

  /* Root-absolute, not "../projection.json": this page is built at both
     /learn/glossary.html and /ms/learn/glossary.html, and the relative form
     resolves to /ms/projection.json on the BM copy, which does not exist.
     The export is written once, at the root (public_export.py, #46). The
     site is served from its own apex via public/CNAME, so a leading slash
     is the site root — the same reasoning as the root-relative /learn/
     links in public_page.py. */
  fetch("/projection.json")
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
      el.textContent = LIVE_MAJORITY_PREFIX + seats + LIVE_MAJORITY_SUFFIX;
    })
    .catch(function () {
      /* Leave the hook empty. No error UI: a reader with JS on but a
         failed fetch (offline, missing file, CORS) sees the same prose
         as a reader with JS off. */
    });
}

initLiveMajority();
</script>"""


def _live_majority_script(language: Language) -> str:
    """`_LIVE_MAJORITY_SCRIPT` with its one reader-facing sentence localised.

    The sentence is split into a prefix and suffix around the seat count
    because BM puts the number in a different place than English does:
    "projected at 148 seats" against "diunjurkan pada 148 kerusi". Braces are
    substituted rather than `str.format`ed — the script is full of JS blocks,
    and every `function () {` would have to be doubled otherwise.
    """
    prefix = t(
        language,
        " Today, the Government Coalition is projected at ",
        " Hari ini, Gabungan Kerajaan diunjurkan pada ",
    )
    suffix = t(language, " seats.", " kerusi.")
    return _LIVE_MAJORITY_SCRIPT.replace("{prefix}", prefix).replace("{suffix}", suffix)


def build_glossary_page(language: Language, updated_at: date, status: ElectionStatus) -> str:
    body = t(language, _GLOSSARY_BODY_EN, _GLOSSARY_BODY_MS)
    return render_shell(
        title=t(
            language,
            "Core terms: reading this site | PolitikKu",
            "Istilah teras: membaca laman ini | PolitikKu",
        ),
        description=t(
            language,
            "A glossary of the terms this site's GE16 projection uses: Seat, Majority, Government, Sentiment, Swing, Projection and more, explained in plain prose for a reader with no prior background.",
            "Glosari istilah yang digunakan unjuran PRU16 laman ini: Kerusi, Majoriti, Kerajaan, Sentimen, Peralihan, Unjuran dan lain-lain, diterangkan dalam bahasa mudah untuk pembaca tanpa latar belakang terdahulu.",
        ),
        active_nav="glossary",
        language=language,
        page_path="learn/glossary.html",
        updated_at=updated_at,
        sources_count=0,
        status=status,
        body_html=f"<style>{_GLOSSARY_CSS}</style>\n{body}\n{_live_majority_script(language)}",
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

_COALITIONS_BODY_EN = """
<div class="pk-learn-container">
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
</div>

""".strip()


_COALITIONS_BODY_MS = """
<div class="pk-learn-container">
<section class="opening">
    <div class="pk-eyebrow">Siapa yang diunjurkan</div>
    <h1>Lima Gabungan</h1>
    <p class="lede">
      Setiap jumlah kerusi di laman ini dilaporkan mengikut Gabungan.
      Halaman ini menyatakan apa itu setiap satu daripada lima Gabungan
      tersebut dan bagaimana ia terbentuk: tarikh penubuhan, parti di
      dalamnya, serta perpecahan dan percantuman yang menghasilkannya. Ia
      catatan struktur semata-mata: ia merakam apa yang dibentuk, bila, dan
      daripada parti yang mana, dan ia menyerahkan persoalan
      <em>mengapa</em> kepada sumber yang dipetiknya.
    </p>
    <ul class="toc">
      <li><a href="#what-is-a-coalition">Apa itu Gabungan</a></li>
      <li><a href="#ph">PH</a></li>
      <li><a href="#bn">BN</a></li>
      <li><a href="#pn">PN</a></li>
      <li><a href="#gps">GPS</a></li>
      <li><a href="#grs">GRS</a></li>
      <li><a href="#why-five">Mengapa lima</a></li>
    </ul>
  </section>

  <section class="prose coalition" id="what-is-a-coalition">
    <h2>Apa itu Gabungan</h2>
    <p class="gloss">unit yang menjadi kiraan Kerusi di laman ini</p>
    <p>
      <span data-claim id="coalition-definition" data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Di laman ini, Gabungan bermaksud sekumpulan parti yang bertanding dan memerintah bersama.</span>
      <span data-claim id="coalition-five" data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Lima Gabungan yang dijejaki laman ini ialah PH, BN, PN, GPS dan GRS.</span>
      Gabungan bukan satu parti tunggal. Setiap satu daripada lima di bawah
      ialah persetujuan antara parti yang mengekalkan nama, keahlian dan
      pegawai masing-masing, dan profil di halaman ini menerangkan parti
      tersebut serta persetujuan yang mengikat mereka, bukan apa yang
      dipercayai atau dikehendaki oleh mana-mana daripadanya.
    </p>
    <p>
      Mengapa jumlahnya lima dan bukan tiga, dan apa yang memisahkan dua
      daripadanya daripada tiga yang lain, dihuraikan di bawah
      <a href="#why-five">Mengapa lima</a> di bawah.
    </p>
  </section>

  <section class="prose coalition" id="ph">
    <h2>Pakatan Harapan <span class="abbr">PH</span></h2>
    <p class="gloss">dibentuk 2015, bagi menggantikan gabungan terdahulu</p>
    <dl class="facts">
      <dt>Ditubuhkan</dt>
      <dd data-claim id="ph-founded" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan ditubuhkan pada 22 September 2015.</dd>
      <dt>Didaftarkan</dt>
      <dd data-claim id="ph-legalised" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan disahkan dari segi undang-undang pada 16 Mei 2018.</dd>
      <dt>Terbentuk daripada</dt>
      <dd data-claim id="ph-predecessor" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pendahulu Pakatan Harapan ialah gabungan Pakatan Rakyat, yang ia dibentuk untuk menggantikannya.</dd>
      <dt>Parti komponen</dt>
      <dd data-claim id="ph-members" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Parti anggota Pakatan Harapan ialah PKR, DAP dan AMANAH.</dd>
    </dl>
    <p>
      <span data-claim id="ph-succession" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan ialah gabungan politik Malaysia yang dibentuk pada 2015 bagi menggantikan gabungan Pakatan Rakyat.</span>
      <span data-claim id="ph-gov-2018" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan mengetuai kerajaan gabungan tunggal dari Mei 2018 hingga Februari 2020.</span>
      <span data-claim id="ph-gov-2022" data-cite="https://en.wikipedia.org/wiki/Pakatan_Harapan?action=raw">Pakatan Harapan mengetuai kerajaan gabungan besar sejak November 2022.</span>
    </p>
  </section>

  <section class="prose coalition" id="bn">
    <h2>Barisan Nasional <span class="abbr">BN</span></h2>
    <p class="gloss">dibentuk 1974, daripada gabungan dua dekad lebih tua</p>
    <dl class="facts">
      <dt>Ditubuhkan</dt>
      <dd data-claim id="bn-founded" data-cite="https://en.wikipedia.org/wiki/Barisan_Nasional?action=raw">Barisan Nasional ditubuhkan pada 1 Jun 1974.</dd>
      <dt>Terbentuk daripada</dt>
      <dd data-claim id="bn-predecessor" data-cite="https://en.wikipedia.org/wiki/Barisan_Nasional?action=raw">Pendahulu Barisan Nasional ialah Parti Perikatan (Alliance Party), bukan Perikatan Nasional.</dd>
      <dt>Parti komponen</dt>
      <dd data-claim id="bn-members" data-cite="https://en.wikipedia.org/wiki/Barisan_Nasional?action=raw">Parti anggota Barisan Nasional ialah UMNO, MCA, MIC, PBRS dan PPP.</dd>
      <dt>Perpecahan kemudian</dt>
      <dd data-claim id="bn-successor" data-cite="https://en.wikipedia.org/wiki/Barisan_Nasional?action=raw">Pengganti Barisan Nasional di Sarawak, mulai 2018, ialah Gabungan Parti Sarawak.</dd>
    </dl>
    <p>
      <span data-claim id="bn-founding" data-cite="https://en.wikipedia.org/wiki/Barisan_Nasional?action=raw">Barisan Nasional ditubuhkan pada 1974 bagi menggantikan Parti Perikatan (Alliance Party), dan mula bertanding dalam pilihan raya umum pada tahun itu juga.</span>
      Tidak seperti empat Gabungan lain di halaman ini, sumber bagi Barisan
      Nasional tidak memberikan tarikh pendaftaran yang berasingan daripada
      tarikh penubuhannya. Ia meneruskan pendaftaran Parti Perikatan itu
      sendiri dan tidak mendaftar semula, sebagaimana yang dilakukan oleh
      GPS, PN dan GRS. Itulah sebabnya jadual fakta di atas tiada baris
      Didaftarkan.
    </p>

    <div class="sub-term">
      <h3>Parti Perikatan (Alliance Party), 1952–1974</h3>
      <p>
        <span data-claim id="alliance-members" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">Keahlian Parti Perikatan (Alliance Party) terdiri daripada UMNO, MCA dan MIC.</span>
        <span data-claim id="alliance-origin" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">Parti Perikatan berasal daripada satu pengaturan pilihan raya sementara antara cawangan tempatan UMNO dan MCA untuk bertanding dalam pilihan raya perbandaran Kuala Lumpur pada 1952.</span>
        <span data-claim id="alliance-mic" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">MIC menyertai perikatan UMNO dan MCA pada 1954.</span>
        <span data-claim id="alliance-registered" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">Parti Perikatan ditubuhkan secara tidak rasmi pada 1952 dan didaftarkan secara rasmi sebagai pertubuhan politik pada 30 Oktober 1957.</span>
      </p>
      <p>
        <span data-claim id="alliance-1971" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">Rundingan dengan bekas parti pembangkang bermula selepas Parlimen Malaysia bersidang semula pada 1971.</span>
        <span data-claim id="alliance-expansion" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">Gerakan dan Parti Progresif Rakyat kedua-duanya menyertai Parti Perikatan pada 1972, diikuti tidak lama kemudian oleh PMIP.</span>
        <span data-claim id="alliance-to-bn" data-cite="https://en.wikipedia.org/wiki/Alliance_Party_(Malaysia)?action=raw">Parti Perikatan (Alliance Party) ialah gabungan pemerintah Malaya dari 1957 hingga 1963 dan Malaysia dari 1963 hingga 1974, dan dikenali sebagai Barisan Nasional pada 1974.</span>
      </p>
    </div>
  </section>

  <section class="prose coalition" id="pn">
    <h2>Perikatan Nasional <span class="abbr">PN</span></h2>
    <p class="gloss">dibentuk Februari 2020, didaftarkan Ogos tahun itu</p>
    <dl class="facts">
      <dt>Ditubuhkan</dt>
      <dd data-claim id="pn-founded" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional ditubuhkan pada 29 Februari 2020.</dd>
      <dt>Didaftarkan</dt>
      <dd data-claim id="pn-registered" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional didaftarkan pada 7 Ogos 2020.</dd>
      <dt>Berpecah daripada</dt>
      <dd data-claim id="pn-split" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional berpecah daripada Pakatan Harapan dan Gagasan Sejahtera.</dd>
      <dt>Ketika pendaftaran</dt>
      <dd data-claim id="pn-at-registration" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Sebagai gabungan rasmi, Perikatan Nasional terdiri daripada BERSATU, PAS dan STAR pada waktu pendaftarannya pada Ogos 2020.</dd>
    </dl>
    <p>
      <span data-claim id="pn-informal" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Menurut catatan Wikipedia, dan sebagai gabungan tidak rasmi, Perikatan Nasional dibentuk oleh BERSATU, PAS, Barisan Nasional, Gabungan Parti Sarawak dan STAR pada permulaan krisis politik Malaysia 2020–2022.</span>
      <span data-claim id="pn-muhyiddin" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Pemimpin de facto Perikatan Nasional, Muhyiddin Yassin, mengangkat sumpah sebagai Perdana Menteri Malaysia ke-8 pada 1 Mac 2020.</span>
      <span data-claim id="pn-govt" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional membentuk kerajaan gabungan bersama Barisan Nasional, Gabungan Parti Sarawak, Gabungan Rakyat Sabah dan parti politik lain, yang memerintah dari 2020 hingga 2022.</span>
    </p>
    <p>
      <span data-claim id="pn-accessions" data-cite="https://en.wikipedia.org/wiki/Perikatan_Nasional?action=raw">Perikatan Nasional diperluas untuk memasukkan SAPP pada Ogos 2020, GERAKAN pada Februari 2021, dan Parti Rakyat India Malaysia pada April 2024.</span>
      Penyertaan itu ialah yang dirakam oleh sumber yang dipetik; keahlian
      rasmi PN terus berubah sejak itu. Pembaca yang ingin menyemak parti
      mana yang berada dalam PN hari ini patut membaca sumber yang dipetik
      itu secara terus dan tidak menganggap halaman ini terkini pada perkara
      tersebut.
    </p>
  </section>

  <section class="prose coalition" id="gps">
    <h2>Gabungan Parti Sarawak <span class="abbr">GPS</span></h2>
    <p class="gloss">dibentuk 2018, apabila empat parti meninggalkan BN</p>
    <dl class="facts">
      <dt>Ditubuhkan</dt>
      <dd data-claim id="gps-founded" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak ditubuhkan pada 12 Jun 2018.</dd>
      <dt>Didaftarkan</dt>
      <dd data-claim id="gps-legalised" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak disahkan dari segi undang-undang pada 19 November 2018.</dd>
      <dt>Berpecah daripada</dt>
      <dd data-claim id="gps-split" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak berpecah daripada Barisan Nasional.</dd>
      <dt>Parti komponen</dt>
      <dd data-claim id="gps-members" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Parti anggota Gabungan Parti Sarawak ialah PBB, PDP, SUPP dan PRS.</dd>
    </dl>
    <p>
      <span data-claim id="gps-formation" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">GPS dibentuk pada 12 Jun 2018, terdiri daripada Parti Pesaka Bumiputera Bersatu, Parti Demokratik Progresif, Parti Rakyat Bersatu Sarawak dan Parti Rakyat Sarawak.</span>
      <span data-claim id="gps-from-bn" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Menurut catatan Wikipedia, Gabungan Parti Sarawak ditubuhkan pada 2018 oleh empat bekas parti komponen Barisan Nasional yang beroperasi semata-mata di Sarawak, berikutan kekalahan gabungan persekutuan itu dalam pilihan raya umum Malaysia 2018.</span>
      <span data-claim id="gps-sarawak-govt" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak membentuk kerajaan di negeri Sarawak.</span>
    </p>
  </section>

  <section class="prose coalition" id="grs">
    <h2>Gabungan Rakyat Sabah <span class="abbr">GRS</span></h2>
    <p class="gloss">dibentuk 2020 sebagai perikatan, didaftarkan sebagai gabungan pada 2022</p>
    <dl class="facts">
      <dt>Ditubuhkan</dt>
      <dd data-claim id="grs-founded" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah ditubuhkan pada September 2020, apabila Hajiji Noor membentuk satu perikatan tidak rasmi dengan nama tersebut.</dd>
      <dt>Didaftarkan</dt>
      <dd data-claim id="grs-legalised" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah disahkan dari segi undang-undang pada 11 Mac 2022.</dd>
      <dt>Terbentuk daripada</dt>
      <dd data-claim id="grs-predecessor" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Pendahulu Gabungan Rakyat Sabah ialah Gabungan Bersatu Sabah, iaitu United Alliance of Sabah.</dd>
      <dt>Parti komponen</dt>
      <dd data-claim id="grs-members" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Parti anggota Gabungan Rakyat Sabah ialah GAGASAN, PBS, UPKO, PHRS, LDP dan PCS.</dd>
    </dl>
    <p>
      <span data-claim id="grs-sabah-based" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah ialah gabungan Malaysia yang terdiri daripada parti berpangkalan di Sabah.</span>
      <span data-claim id="grs-established" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah ditubuhkan pada 2020 dan kemudian didaftarkan pada 2022 oleh bekas parti komponen Gabungan Bersatu Sabah dan United Borneo Alliance, yang beroperasi semata-mata di Sabah.</span>
      <span data-claim id="grs-gps-formula" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Menurut catatan Wikipedia, Gabungan Rakyat Sabah dibentuk dengan mengambil inspirasi daripada formula gabungan berpangkalan di Sarawak, Gabungan Parti Sarawak.</span>
    </p>
    <p>
      <span data-claim id="grs-upko" data-cite="https://www.malaymail.com/news/malaysia/2026/06/18/upko-joins-grs-expanding-sabah-ruling-coalition-to-six-parties/224325">Malay Mail melaporkan bahawa pada 18 Jun 2026 Gabungan Rakyat Sabah secara rasmi menerima Pertubuhan Kinabalu Progresif Bersatu sebagai parti komponen terbarunya, memperluas gabungan pemerintah Sabah itu kepada enam parti.</span>
      Penyertaan itulah sebabnya senarai parti komponen di atas berjumlah
      enam.
    </p>
  </section>

  <section class="prose coalition" id="why-five">
    <h2>Mengapa lima</h2>
    <p class="gloss">tiga Gabungan persekutuan, dua Gabungan Borneo</p>
    <p>
      Jumlahnya lima kerana dua daripada Gabungan itu dibentuk khusus bagi
      satu negeri setiap satu.
      <span data-claim id="why-gps-sarawak" data-cite="https://en.wikipedia.org/wiki/Gabungan_Parti_Sarawak?action=raw">Gabungan Parti Sarawak ialah perikatan politik berpangkalan di Sarawak yang empat parti pengasasnya beroperasi semata-mata di Sarawak.</span>
      <span data-claim id="why-grs-sabah" data-cite="https://en.wikipedia.org/wiki/Gabungan_Rakyat_Sabah?action=raw">Gabungan Rakyat Sabah ialah gabungan Malaysia yang terdiri daripada parti berpangkalan di Sabah.</span>
      Setiap satu dirakam di atas berserta tarikh pembentukannya dan parti
      yang membentuknya.
    </p>
    <p>
      Itu perbezaan struktur, bukan dakwaan tentang apa yang dikehendaki
      mana-mana parti ini. GPS dibentuk khusus bagi Sarawak dan GRS bagi
      Sabah; tiga yang lain tidak dibentuk khusus bagi satu negeri.
      <span data-claim id="why-222-seats" data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md">Dewan Rakyat mempunyai 222 Kerusi.</span>
      Sarawak dan Sabah masing-masing menyumbang bahagian mereka sendiri
      daripada 222 itu. Unjuran yang mengabaikan dua Gabungan Borneo itu
      bermakna mengunjurkan sebuah dewan yang tidak wujud, dan itulah
      sebabnya laman ini mengira lima dan bukan tiga.
    </p>
  </section>
</div>
""".strip()


def build_coalitions_page(language: Language, updated_at: date, status: ElectionStatus) -> str:
    return render_shell(
        title=t(
            language,
            "The five Coalitions: reading this site | PolitikKu",
            "Lima Gabungan: membaca laman ini | PolitikKu",
        ),
        description=t(
            language,
            "What a Coalition is in Malaysian politics, and how each of the five this site tracks, PH, BN, PN, GPS and GRS, was formed: founding dates, component parties, and the splits and mergers behind them, each traced to a cited source.",
            "Apa itu Gabungan dalam politik Malaysia, dan bagaimana setiap satu daripada lima yang dijejaki laman ini, iaitu PH, BN, PN, GPS dan GRS, terbentuk: tarikh penubuhan, parti komponen, serta perpecahan dan percantuman di sebaliknya, setiap satu dijejaki kepada sumber yang dipetik.",
        ),
        active_nav="coalitions",
        language=language,
        page_path="learn/coalitions.html",
        updated_at=updated_at,
        sources_count=0,
        status=status,
        body_html=(
            f"<style>{_COALITIONS_CSS}</style>\n"
            f"{t(language, _COALITIONS_BODY_EN, _COALITIONS_BODY_MS)}"
        ),
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
    font-size: 11px;
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

_PROCESS_BODY_EN = """
<div class="pk-learn-container">
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
    <p class="pk-learn-callout">
      For where GE16 stands right now — whether it has been called, the dates
      that are set, and how long is left — see
      <a href="/pru16/">the GE16 page</a>.
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
</div>

""".strip()


_PROCESS_BODY_MS = """
<div class="pk-learn-container">
<section class="opening">
    <div class="pk-eyebrow">Bagaimana pilihan raya sebenarnya berlangsung</div>
    <h1>Proses PRU16</h1>
    <p class="lede">
      Papan pemuka ini menjejaki tiga keadaan bagi PRU16: belum
      diisytiharkan, diisytiharkan tanpa tarikh mengundi lagi, dan
      diisytiharkan dengan tarikh mengundi ditetapkan. Halaman ini
      menerangkan urutan di sebalik keadaan tersebut, daripada pembubaran
      kepada penamaan calon kepada pengundian, dan mengapa keadaan
      pertengahan itu, iaitu diisytiharkan tetapi tanpa tarikh, ialah
      peringkat sebenar dalam proses dan bukan lompang dalam rekod.
    </p>
    <p class="pk-learn-callout">
      Untuk kedudukan PRU16 pada masa ini — sama ada ia telah
      diisytiharkan, tarikh yang telah ditetapkan, dan berapa lama lagi
      yang tinggal — lihat
      <a href="/ms/pru16/">halaman PRU16</a>.
    </p>
    <ul class="toc">
      <li><a href="#step-dissolution">Pembubaran</a></li>
      <li><a href="#step-nomination">Penamaan calon</a></li>
      <li><a href="#step-polling">Pengundian</a></li>
      <li><a href="#the-three-states">Tiga keadaan</a></li>
    </ul>
  </section>

  <section class="prose step" id="step-dissolution">
    <span class="step-index">01</span>
    <h2>Pembubaran</h2>
    <p class="gloss">tindakan yang memulakan pilihan raya umum Malaysia</p>
    <p>
      <span data-claim data-cite="https://www.malaysianbar.org.my/legal/general_news/royal_powers_after_dissolution.html" id="dissolution-starts-it">Pilihan raya umum Malaysia bermula dengan pembubaran Dewan Rakyat, iaitu dewan rendah Parlimen yang dipilih, peristiwa yang membuka tempoh interim sehingga pelantikan kerajaan pilihan yang seterusnya.</span>
      <span data-claim data-cite="https://www.malaysianbar.org.my/legal/general_news/royal_powers_after_dissolution.html" id="dissolution-two-routes">Melainkan pilihan raya diadakan lebih awal, penggal lima tahun Dewan Rakyat akan berjalan sehingga tamat dan pembubaran menyusul.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="dissolution-early-is-ordinary">Pembubaran awal ialah kes biasa yang digambarkan oleh nota data projek ini sendiri, bukan pengecualian.</span>
    </p>
    <p>
      <span data-claim data-cite="https://www.malaysianbar.org.my/legal/general_news/royal_powers_after_dissolution.html" id="deadline-60-days">Perkara 55(4) Perlembagaan Persekutuan menghendaki pilihan raya umum diadakan dalam tempoh 60 hari dari pembubaran Dewan Rakyat.</span>
      <span data-claim data-cite="https://www.malaysianbar.org.my/legal/general_news/by_elections_and_the_constitution.html" id="art-55-3">Mandat lima tahun Dewan Rakyat tamat di bawah Perkara 55(3) Perlembagaan Persekutuan.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="deadline-worked-example">Digabungkan, kedua-dua peruntukan itu menetapkan tarikh akhir PRU16 itu sendiri: persidangan pertama Dewan Rakyat semasa ialah pada 19 Disember 2022, jadi ia terbubar secara automatik lima tahun kemudian, pada 19 Disember 2027, jika tidak dibubarkan lebih awal, menjadikan tarikh terakhir yang mungkin bagi PRU16 ialah 17 Februari 2028.</span>
    </p>
  </section>

  <section class="prose step" id="step-nomination">
    <span class="step-index">02</span>
    <h2>Penamaan calon</h2>
    <p class="gloss">di mana Suruhanjaya Pilihan Raya menetapkan tarikh yang tidak ditetapkan oleh pembubaran</p>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="dissolution-doesnt-set-dates">Pembubaran itu sendiri tidak menetapkan bila hari penamaan calon atau hari mengundi akan jatuh. Suruhanjaya Pilihan Raya Malaysia menetapkan dan mengumumkan tarikh tersebut secara berasingan, selepas pembubaran berlaku.</span>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="gap-is-typical">Nota data projek ini sendiri merakam jurang itu sebagai lazimnya mengambil masa seminggu atau dua.</span>
    </p>
    <p>
      <span data-claim data-cite="https://www.malaysianbar.org.my/article/news/legal-and-general-news/members-opinions/ge13-abiding-by-the-nomination-process" id="nomination-centres">Pada hari penamaan calon, para calon mengemukakan kertas penamaan mereka kepada pegawai pengurus bagi kawasan pilihan raya masing-masing, dan kertas tersebut boleh ditolak jika ia tidak mematuhi Peraturan-Peraturan Pilihan Raya (Perjalanan Pilihan Raya).</span>
    </p>
  </section>

  <section class="prose step" id="step-polling">
    <span class="step-index">03</span>
    <h2>Pengundian</h2>
    <p class="gloss">di mana pengundi memutuskan, dalam tempoh yang dibuka oleh pembubaran</p>
    <p>
      Hari mengundi itu sendiri jatuh dalam tempoh 60 hari yang sama yang
      ditetapkan oleh Perkara 55(4) bermula dari pembubaran (lihat
      <a href="#step-dissolution">Pembubaran</a> di atas). Penamaan calon,
      kempen yang menyusul selepasnya, dan pengundian semuanya mesti jatuh
      dalam satu tarikh akhir perlembagaan itu. Untuk memahami apa itu
      Kerusi dan berapa banyak yang ada dalam Dewan Rakyat, lihat
      <a href="glossary.html#term-seat">glosari</a>.
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md" id="polling-not-model-input">Setelah tarikh mengundi ditetapkan, ia menjadi konteks untuk membaca Unjuran laman ini, bukan input yang digunakan oleh Model Peralihan.</span>
    </p>
  </section>

  <section class="prose step" id="the-three-states">
    <div class="pk-eyebrow">Apa yang sebenarnya dipaparkan papan pemuka</div>
    <h2>Tiga keadaan</h2>
    <p>
      <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="three-states-summary">Status Pilihan Raya papan pemuka ini dipacu oleh tiga tarikh, iaitu bila Dewan Rakyat dibubarkan, bila penamaan calon berlaku, dan bila pengundian ditetapkan, dan ia menentukan apa yang dipaparkan berdasarkan tarikh yang mana antara ketiga-tiga itu yang ada.</span>
    </p>

    <div class="states">
      <div class="state-block">
        <span class="state-tag">Belum diisytiharkan</span>
        <h3>Tiada tarikh pembubaran</h3>
        <p>
          <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="state-not-called">Sebelum Dewan Rakyat dibubarkan, PRU16 belum diisytiharkan, dan papan pemuka ini tidak merakam tarikh pembubaran mahupun tarikh mengundi.</span>
          <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="state-not-called-deadline">Dewan Rakyat terus bersidang, terikat hanya kepada tarikh akhir perlembagaan yang ditetapkan bersama oleh penggal lima tahun dan peraturan 60 hari itu.</span>
        </p>
      </div>
      <div class="state-block">
        <span class="state-tag">Diisytiharkan, tiada tarikh mengundi</span>
        <h3>Dibubarkan, tarikh belum diumumkan</h3>
        <p>
          <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="state-called-no-polling">Antara pembubaran dan pengumuman jadual oleh Suruhanjaya Pilihan Raya, papan pemuka ini merakam tarikh pembubaran dan tiada tarikh mengundi.</span>
          <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="state-called-no-polling-no-guess">Papan pemuka ini membiarkan medan pengundian kosong bagi tempoh itu dan tidak mengisinya dengan tekaan.</span>
        </p>
      </div>
      <div class="state-block">
        <span class="state-tag">Diisytiharkan, tarikh mengundi ditetapkan</span>
        <h3>Kedua-dua tarikh dalam rekod</h3>
        <p>
          <span data-claim data-cite="https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/data/election_status.json" id="state-called-with-polling">Setelah Suruhanjaya Pilihan Raya mengumumkan jadual, rekod papan pemuka ini mempunyai kedua-dua tarikh: tarikh pembubaran yang ditetapkan lebih awal, dan tarikh mengundi yang kini diumumkan oleh Suruhanjaya.</span>
        </p>
      </div>
    </div>
  </section>
</div>
""".strip()


def build_process_page(language: Language, updated_at: date, status: ElectionStatus) -> str:
    return render_shell(
        title=t(
            language,
            "The GE16 process: reading this site | PolitikKu",
            "Proses PRU16: membaca laman ini | PolitikKu",
        ),
        description=t(
            language,
            "How GE16 actually unfolds, from dissolution to nomination to polling, and why 'called, no polling date yet' is a real, distinct state this dashboard tracks, not a half-filled record.",
            "Bagaimana PRU16 sebenarnya berlangsung, daripada pembubaran kepada penamaan calon kepada pengundian, dan mengapa 'diisytiharkan, tiada tarikh mengundi lagi' ialah keadaan sebenar yang tersendiri yang dijejaki papan pemuka ini, bukan rekod yang terisi separuh.",
        ),
        active_nav="process",
        language=language,
        page_path="learn/ge16-process.html",
        updated_at=updated_at,
        sources_count=0,
        status=status,
        body_html=(
            f"<style>{_PROCESS_CSS}</style>\n{t(language, _PROCESS_BODY_EN, _PROCESS_BODY_MS)}"
        ),
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
