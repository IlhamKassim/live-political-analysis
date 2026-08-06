# Ingesting a Merdeka Center report

Poll Calibration is periodic and semi-manual by necessity: Merdeka Center
publishes PDFs, on no schedule, behind no API. This is the process for
turning a newly published report into a Poll Calibration point. It takes about
ten minutes and is run when a report drops, not on a timer.

Why leader approval is the number transcribed, and why the Coalition
attribution is recorded per report rather than derived, is
[ADR 0004](adr/0004-leader-approval-as-the-coalition-poll-signal.md). Read it
before transcribing your first one; the attribution rule is the only part of
this that takes judgement.

## 1. Find the report

Merdeka Center lists its reports at <https://merdeka.org/>, most recent first.
Take the political ones — titled around perceptions of the economy,
leadership and current issues. Topic surveys (tobacco, and such) carry no
leader approval and are not ingested.

Each listing links to a landing page that links to a PDF. The PDF is served by
WordPress Download Manager, so the direct link is of the form
`https://merdeka.org/?wpdmdl=<id>`; the id is in the landing page's HTML if
the download button is awkward to use.

## 2. Read the numbers off it

From the methodology page (usually page 3): fieldwork start and end dates,
sample size, margin of error.

From the "Leaders' Approval Ratings — Overall" chart (usually near the end):
each leader's satisfied and dissatisfied percentage. Take the **Overall**
chart, not the Malay/non-Malay breakdowns.

Copy the percentages exactly as printed. They will not sum to 100 — the
reports also carry neutral and unsure/refused answers, and rescaling to make
them sum would silently invent a number Merdeka Center did not publish.

## 3. Attribute each leader to a Coalition

For each rated leader, ask: **which party did this person belong to during the
fieldwork window, and which Coalition did that party sit in?**

Not at publication — reports appear two or three months after fieldwork
closes, and people cross the floor in between. Not today either. The window
is the question.

- The party maps to a Coalition through the component parties listed in
  `data/coalitions.json` under `coalition_aliases` — PKR and DAP are PH, UMNO
  is BN, PAS and Bersatu are PN, and so on.
- Where the report names no party, or where the person's standing during the
  window is genuinely contested, set both `party` and `coalition` to `null`
  and write a `note` saying why, with the dates. The rating is still recorded
  and the dashboard reports it as unattributed. Guessing is the one thing not
  allowed here.
- Where the attribution took any judgement at all, write the `note` even if
  you did attribute it.

## 4. Transcribe it

Add an entry to the `reports` array in `data/poll_calibration.json`, following
the one already there. Every field is required except `margin_of_error`,
`party` and `note`.

## 5. Ingest and check it

```sh
export DATABASE_URL="sqlite+pysqlite:///$PWD/lpa.db"
python -m lpa.poll_calibration
```

It prints the derived per-Coalition net approval, the leader count behind
each, and any unattributed leaders. Check those against the report before
going further — a transposed percentage shows up here as a Coalition sitting
somewhere implausible.

Ingestion is idempotent per publisher and fieldwork end date, so fixing a
transcription error is a matter of editing the file and running it again. It
does not delete reports that are no longer in the file: history already
ingested stays ingested.

Then open the dashboard and look at the Poll Calibration section:

```sh
streamlit run src/lpa/dashboard.py
```

The point appears on the Sentiment trend only if its fieldwork ended inside
the span of stored daily history — otherwise it would drag the chart's x axis
back months and flatten the trend it exists to show. The comparison table
below the chart always shows the latest report, and says how far the nearest
stored News Sentiment day is from the close of fieldwork.

## What the comparison is for

Sanity-checking, in the sense CONTEXT.md gives Poll Calibration — and nothing
more. The two numbers share a −1..+1 scale and measure different things: one
is the tone of coverage naming a Coalition, the other is how many people told
a pollster they approve of that Coalition's leaders. They are not expected to
match, and nothing in the pipeline reads Poll Calibration into a Projection. A
wide or a moving gap is a reason to go and look at the News Sentiment inputs;
it is not a correction to apply to them.
