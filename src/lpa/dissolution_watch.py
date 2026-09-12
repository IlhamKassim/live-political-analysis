"""Watch the day's coverage for a dissolution, and tell *us* — never the site.

`election_status.json` is maintained by hand on purpose: its own comments say
automatic detection of a dissolution is out of scope, and that is the right
call. Malaysian coverage speculates about early polls constantly, and
"analysts expect Parliament to be dissolved" reads almost identically to
"Parliament has been dissolved" to anything matching keywords. Publishing the
second when only the first happened would put a false claim on the front door
of the site, which is the one mistake here that people screenshot.

So this module never writes to the site and never posts to the public
channel. It reads the Articles the pipeline already fetched, and if any of
them look like the event has actually happened it sends one private message
to whoever maintains the data, with the headlines and links, so a human can
check the source and edit the file. Detection, composition and delivery stay
separate for the same reason `telegram_post` keeps them apart.

**It silences itself.** A signal is only reported for a fact the status file
does not already record: once `dissolved_on` is filled in, dissolution
signals stop. Until then it will nag on every run, which is the intended
behaviour — an unanswered alert means the site is still saying something
untrue.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from lpa.domain import Article, ElectionStatus

TELEGRAM_API = "https://api.telegram.org"


class SignalKind(StrEnum):
    """Which fact the coverage claims has happened."""

    DISSOLUTION = "dissolution"
    POLLING_DATE = "polling_date"


# Patterns that assert the event, English and Malay. Written as regexes
# rather than a list of literal phrases because outlets vary the tense freely
# — "has been dissolved", "was dissolved", "is dissolved" — and enumerating
# those by hand is how a watch quietly misses the one wording the day
# actually uses.
#
# Every pattern is anchored on the national chamber by name. "dissolved"
# alone catches dissolved marriages and dissolved companies, and a state
# assembly being dissolved ahead of a state election is a different and
# commonplace event that must not fire this.
_CHAMBER = r"(?:the\s+)?(?:dewan\s+rakyat|parliament|parlimen)"

_DISSOLUTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        # "the Dewan Rakyat has been / was / is dissolved"
        rf"{_CHAMBER}\s+(?:\w+\s+){{0,3}}?dissolved\b",
        # "dissolved Parliament", "dissolves the Dewan Rakyat"
        rf"dissolv(?:ed|es)\s+{_CHAMBER}",
        rf"dissolution\s+of\s+{_CHAMBER}",
        r"consent(?:ed|s)?\s+to\s+the\s+dissolution",
        # Malay: "Parlimen telah dibubarkan", "membubarkan Dewan Rakyat"
        rf"{_CHAMBER}\s+(?:telah\s+|sudah\s+)?dibubarkan\b",
        rf"membubarkan\s+{_CHAMBER}",
        rf"pembubaran\s+{_CHAMBER}",
        r"perkenan\s+pembubaran",
    )
)

_POLLING_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"(?:polling|nomination)\s+(?:day|date)\s+(?:is|will\s+be|has\s+been\s+set|set\s+for|falls\s+on)",
        r"(?:set|sets|fixed|gazetted)\s+(?:the\s+)?(?:polling|nomination)\s+(?:day|date)",
        r"(?:tarikh|hari)\s+(?:mengundi|pengundian)\s+(?:ialah|adalah|ditetapkan|pada)",
        r"(?:hari|tarikh)\s+penamaan\s+calon\s+(?:ialah|adalah|ditetapkan|pada)",
        r"menetapkan\s+(?:tarikh|hari)\s+(?:mengundi|pengundian|penamaan)",
    )
)

# Words that turn an assertion into a guess. Checked in the same sentence as
# the phrase, not the whole article: a report of a real dissolution will
# often also quote someone who predicted it, and a whole-document check would
# throw that report away.
# Stems, not whole words: "expect" has to cover expects, expected and
# expecting, and missing one inflection is how speculation gets through.
_HEDGES: tuple[str, ...] = (
    "expect",
    "speculat",
    "rumour",
    "rumor",
    "hint",
    "likely",
    "could ",
    "may be",
    "might",
    "if parliament",
    "if the dewan",
    "should parliament",
    # Every inflection spelled out. Stemming these to "call" or "urg" would
    # be worse, not better: "called an election" is the real event, and
    # "urgent" would suppress a genuine report that happened to use the word.
    "call for",
    "calls for",
    "called for",
    "calling for",
    "urge",
    "urges",
    "urged",
    "urging",
    "predict",
    "anticipat",
    "dijangka",
    "jangkaan",
    "spekulasi",
    "berkemungkinan",
    "mungkin",
    "sekiranya",
    "jika ",
    "gesa",
    "desak",
    "ramalan",
    "dijangkakan",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class Signal:
    """One Article that claims the event has happened, and the sentence that
    says so — the sentence is what a human reads to judge it in two seconds."""

    kind: SignalKind
    source: str
    title: str
    url: str
    sentence: str


def _sentences(text: str) -> list[str]:
    """Split on the original text, not a lowercased copy: the matching is
    case-insensitive, but the sentence goes into a message a human reads to
    judge the story, and all-lowercase prose is harder to read quickly."""
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _match(sentence: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    lowered = sentence.lower()
    if any(hedge in lowered for hedge in _HEDGES):
        return False
    return any(pattern.search(lowered) for pattern in patterns)


def scan(articles: Iterable[Article], status: ElectionStatus) -> tuple[Signal, ...]:
    """Every Article claiming a fact the status file does not already record.

    Passing `status` is what makes this self-silencing: there is no point
    alerting about a dissolution we have already written down, and every
    point in alerting about one we have not.
    """
    wanted: list[tuple[SignalKind, tuple[re.Pattern[str], ...]]] = []
    if status.dissolved_on is None:
        wanted.append((SignalKind.DISSOLUTION, _DISSOLUTION_PATTERNS))
    if status.polling_date is None:
        wanted.append((SignalKind.POLLING_DATE, _POLLING_PATTERNS))
    if not wanted:
        return ()

    signals: list[Signal] = []
    for article in articles:
        sentences = _sentences(f"{article.title}. {article.text}")
        for kind, phrases in wanted:
            hit = next((s for s in sentences if _match(s, phrases)), None)
            if hit is not None:
                signals.append(
                    Signal(
                        kind=kind,
                        source=article.source,
                        title=article.title.strip(),
                        url=article.url,
                        sentence=hit,
                    )
                )
    return tuple(signals)


def compose_alert(signals: Sequence[Signal]) -> str:
    """The private message. Plain and scannable: what we think happened, the
    headlines behind it, and the one action that clears it."""
    from html import escape

    kinds = {s.kind for s in signals}
    if SignalKind.DISSOLUTION in kinds:
        headline = "Coverage says the Dewan Rakyat has been dissolved."
        action = (
            "Check the source. If it is real, set <code>dissolved_on</code> in "
            "<code>data/election_status.json</code> and push — the site will keep "
            "saying GE16 has not been called until you do."
        )
    else:
        headline = "Coverage says the election dates have been set."
        action = (
            "Check the source. If it is real, set <code>nomination_date</code> and "
            "<code>polling_date</code> in <code>data/election_status.json</code> from "
            "the Election Commission's announcement, and push."
        )

    lines = [f"<b>{escape(headline)}</b>", ""]
    seen: set[str] = set()
    for signal in signals:
        if signal.url in seen:
            continue
        seen.add(signal.url)
        lines.append(f'• <a href="{escape(signal.url)}">{escape(signal.title)}</a>')
        lines.append(f"  <i>{escape(signal.source)}</i> — “{escape(signal.sentence)}”")
    lines.append("")
    lines.append(action)
    lines.append("")
    lines.append(
        "<i>This is a heads-up from the news scraper, not a verified fact. "
        "Nothing has been published.</i>"
    )
    return "\n".join(lines)


def write_signals(signals: Sequence[Signal], path: Path) -> None:
    """Hand what this run found to the step that sends it.

    Always written, empty list included: a file that is missing and a file
    that says "nothing today" look the same to a reader but mean very
    different things, and the alert step should be able to tell a quiet day
    from a pipeline that fell over before it got here.
    """
    payload = [
        {
            "kind": str(s.kind),
            "source": s.source,
            "title": s.title,
            "url": s.url,
            "sentence": s.sentence,
        }
        for s in signals
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_signals(path: Path) -> tuple[Signal, ...]:
    """The inverse of `write_signals`. A missing file is no signals."""
    if not path.exists():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        Signal(
            kind=SignalKind(item["kind"]),
            source=item["source"],
            title=item["title"],
            url=item["url"],
            sentence=item["sentence"],
        )
        for item in raw
    )


def send_alert(client: object, token: str, chat_id: str, text: str) -> None:
    """The one HTTPS call. `client` is always supplied by the caller, the same
    way `telegram_post.send_post` requires one, so a test never needs a real
    network."""
    response = client.post(  # type: ignore[attr-defined]
        f"{TELEGRAM_API}/bot{token}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        },
    )
    response.raise_for_status()


def main() -> None:
    """Send the alert the pipeline wrote down, if there is one.

    Separate from the pipeline so a Telegram outage, a missing token or a
    revoked bot can never fail the run that keeps the site up to date. It
    exits quietly on every one of those: an alert that did not send is worth
    a log line, not a red build.
    """
    import argparse
    import os

    import httpx

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--signals",
        type=Path,
        default=Path("dissolution-signals.json"),
        help="Where the pipeline wrote what it found.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the message instead of sending it.",
    )
    args = parser.parse_args()

    signals = read_signals(args.signals)
    if not signals:
        print("No status-change signals in today's coverage.")
        return

    message = compose_alert(signals)
    if args.dry_run:
        print(message)
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    # A separate chat from the public channel, and required: falling back to
    # TELEGRAM_CHANNEL_ID would broadcast an unverified rumour to readers,
    # which is the exact failure this whole module exists to avoid.
    chat_id = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
    if not token or not chat_id:
        print(
            "TELEGRAM_BOT_TOKEN or TELEGRAM_ALERT_CHAT_ID is unset — "
            "not sending. The message would have been:\n"
        )
        print(message)
        return

    with httpx.Client(timeout=15) as client:
        try:
            send_alert(client, token, chat_id, message)
        except httpx.HTTPError as error:
            print(f"Could not send the alert ({error}). The message was:\n")
            print(message)
            return
    print(f"Alerted on {len(signals)} Article(s).")


if __name__ == "__main__":
    main()
