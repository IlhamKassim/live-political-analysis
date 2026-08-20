"""Composing and sending the Telegram post for a fired Return Trigger (#40).

`return_trigger.py` decides *whether* today is worth a push; this module
decides *what the push says and shows*, and does the one HTTPS call that
sends it. Kept separate the same way `render_aggregate_card_png` is
trigger-agnostic of `AggregateCardModel`'s copy: detection, composition, and
delivery are three different kinds of mistake to make, and mixing them
would make each harder to test in isolation.

Two templates, matching #40's own Scope section and the approved mockup
(`docs/design/telegram-post-samples.html`):

- **Seat-anchored** (Sample B's voice): used only when a Majority trigger
  traces to exactly one Seat crossing the Government/Non-government line —
  `MajorityTrigger.government_relevant_changed` of length 1. Any other
  Majority trigger (several Seats moved at once, or none did and only the
  Sentiment-driven totals shifted) has no single Seat to point at honestly,
  so it falls through to the aggregate template instead.
- **Aggregate** (Sample C's timeline-over-chamber-bar): used for the
  Election Status and State Election Signal triggers, and for every
  Majority trigger that isn't Seat-anchored. The mockup's own rationale
  text muses about swapping the timeline for a state-result panel on a
  State Election Signal post; #40's Scope section does not ask for that
  third layout — it describes one aggregate format for "triggers 1 and 2,
  or a chamber-wide Majority swing" — so this reuses the one built format
  with State-Signal-specific copy rather than inventing an unreviewed one.

Every composed post is logged to `trigger_post_log` regardless of whether
the Telegram send succeeds (`main`, below) — the log is what the RSS/Atom
feed (`build_feed`) reads, and a post that fired is a fact about the day
independent of one delivery channel's uptime.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from xml.sax.saxutils import escape as _xml_escape

import httpx

from lpa.domain import (
    Coalition,
    ElectionStatus,
    Projection,
    SeatBaseline,
    SwingModelConfig,
    government_seat_total,
)
from lpa.pipeline import today_in_malaysia
from lpa.public_page import Tier
from lpa.return_trigger import (
    ElectionStatusTrigger,
    ElectionStatusTriggerKind,
    MajorityTrigger,
    StateSignalTrigger,
    Trigger,
)
from lpa.seat_call_card import card_model
from lpa.telegram_card import (
    AggregateCardModel,
    election_status_aggregate_model,
    render_aggregate_card_png,
    render_seat_card_png,
)

TELEGRAM_API = "https://api.telegram.org"
SITE_URL = "https://ilhamkassim.github.io/live-political-analysis/"


def _escape_html(text: str) -> str:
    """Telegram's HTML parse mode only needs the three characters that
    could otherwise be read as markup — the same minimal escaping
    `seat_call_card.py` already applies to SVG text for the same reason."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _long_date(day: date) -> str:
    return f"{day.day} {day.strftime('%B %Y')}"


@dataclass(frozen=True)
class PostContent:
    """One composed post: the image, the Telegram caption beneath it, and a
    plain-text title for the RSS/Atom feed, which has no image of its own."""

    title: str
    caption: str
    photo: bytes


def compose_election_status_post(
    trigger: ElectionStatusTrigger,
    government_seats: int,
    total_seats: int,
    majority_threshold: int,
) -> PostContent:
    """Trigger 1 (#40): GE16 called, or a polling date newly set.

    Caption voice matches Sample C's approved copy for the "called" case
    verbatim; "polling date set" follows the same voice, since the mockup
    has no sample for it.
    """
    model = election_status_aggregate_model(
        trigger.kind, trigger.status, government_seats, total_seats, majority_threshold
    )
    photo = render_aggregate_card_png(model)
    if trigger.kind == ElectionStatusTriggerKind.CALLED:
        title = "GE16 has been called."
        caption = (
            "<b>GE16 has been called.</b> The Dewan Rakyat was dissolved. The "
            "Election Commission has not set a polling date yet, so “called” "
            "really is all anyone knows so far.\n\n"
            "Nothing about the Projection changed today — dissolution starts "
            "the clock, it does not move the arithmetic. The site is where it "
            f"always is, worked out fresh once a day.\n\n{SITE_URL}"
        )
    else:
        assert trigger.status.polling_date is not None  # the trigger only fires once it is
        title = f"Polling day is {_long_date(trigger.status.polling_date)}."
        caption = (
            f"<b>{_escape_html(title)}</b> The Election Commission has set the date.\n\n"
            "Nothing about the Projection changed today — the date moves the "
            f"calendar, not the arithmetic.\n\n{SITE_URL}"
        )
    return PostContent(title=title, caption=caption, photo=photo)


def compose_state_signal_post(
    trigger: StateSignalTrigger,
    status: ElectionStatus,
    government_seats: int,
    total_seats: int,
    majority_threshold: int,
) -> PostContent:
    """Trigger 2 (#40): a new State Election Signal landed."""
    states = ", ".join(trigger.states)
    title = f"{states} reported a state election result."
    model = AggregateCardModel(
        eyebrow="State Election Signal · GE16",
        headline=title,
        gloss=f"the result now feeds {states}'s Swing in the Projection",
        caption=(
            "A State Election Signal is one input to the Swing, weighted "
            "alongside News/Poll Sentiment — not a replacement for either."
        ),
        dissolved_on=status.dissolved_on,
        nomination_date=status.nomination_date,
        polling_date=status.polling_date,
        government_seats=government_seats,
        total_seats=total_seats,
        majority_threshold=majority_threshold,
    )
    photo = render_aggregate_card_png(model)
    caption = (
        f"<b>A State Election Signal landed.</b> {_escape_html(states)} held a "
        "state election, and the result now feeds that state's Swing in the "
        "Projection — a leading indicator, weighted alongside News/Poll "
        f"Sentiment, not a replacement for it.\n\n{SITE_URL}"
    )
    return PostContent(title=title, caption=caption, photo=photo)


def compose_majority_post(
    trigger: MajorityTrigger,
    baseline_by_code: Mapping[str, SeatBaseline],
    names: Mapping[Coalition, str],
    status: ElectionStatus,
    config: SwingModelConfig,
    total_seats: int,
) -> PostContent:
    """Trigger 3 (#40): the Majority margin moved past the threshold, or flipped.

    Seat-anchored only when exactly one Seat crossed the Government/
    Non-government line — see the module docstring for why any other case
    falls through to the aggregate template.
    """
    if len(trigger.government_relevant_changed) == 1:
        _, newer_call = trigger.government_relevant_changed[0]
        seat = baseline_by_code[newer_call.code]
        model = card_model(newer_call, seat, names)
        photo = render_seat_card_png(model)
        tight_suffix = ", and inside the too-close band" if model.tier == Tier.TIGHT else ""
        title = f"{model.name} changed hands."
        caption = (
            "<b>A Seat Call changed.</b> The Projection now puts "
            f"{_escape_html(model.name)} with {_escape_html(model.coalition_name)} "
            f"by {model.margin_points} points — arithmetic against the 2022 result, "
            f"not calibrated{tight_suffix}.\n\n{SITE_URL}"
        )
        return PostContent(title=title, caption=caption, photo=photo)

    government_seats = government_seat_total(trigger.newer.coalition_seat_totals, config)
    if trigger.majority_flipped:
        holds = "holds" if trigger.newer.government_majority else "has lost"
        title = "The Majority flipped."
        gloss = f"the Government Coalition {holds} the {config.majority_threshold}-seat line"
    else:
        direction = "gained" if trigger.government_delta > 0 else "lost"
        title = f"The Government Coalition {direction} {abs(trigger.government_delta)} seats."
        gloss = "a swing large enough to be worth a look, not a change of Government"
    aggregate_model = AggregateCardModel(
        eyebrow="Majority · GE16",
        headline=title,
        gloss=gloss,
        caption=(
            "A Majority swing is the Seat-Level Projection's own daily arithmetic "
            "moving, not a new signal on its own — see the site for which "
            "Seats moved."
        ),
        dissolved_on=status.dissolved_on,
        nomination_date=status.nomination_date,
        polling_date=status.polling_date,
        government_seats=government_seats,
        total_seats=total_seats,
        majority_threshold=config.majority_threshold,
    )
    photo = render_aggregate_card_png(aggregate_model)
    caption = (
        f"<b>{_escape_html(title)}</b> {_escape_html(gloss.capitalize())}.\n\n"
        "That is the Seat-Level Projection's own arithmetic moving — not "
        f"calibrated, and not a new signal on its own.\n\n{SITE_URL}"
    )
    return PostContent(title=title, caption=caption, photo=photo)


def compose_posts(
    triggers: Sequence[Trigger],
    *,
    status: ElectionStatus,
    baseline: Sequence[SeatBaseline],
    names: Mapping[Coalition, str],
    config: SwingModelConfig,
    total_seats: int,
    latest_projection: Projection,
) -> tuple[PostContent, ...]:
    """One post per fired trigger, in the order `detect_triggers` returned them."""
    baseline_by_code = {seat.code: seat for seat in baseline}
    government_seats = government_seat_total(latest_projection.coalition_seat_totals, config)
    posts = []
    for trigger in triggers:
        if isinstance(trigger, ElectionStatusTrigger):
            posts.append(
                compose_election_status_post(
                    trigger, government_seats, total_seats, config.majority_threshold
                )
            )
        elif isinstance(trigger, StateSignalTrigger):
            posts.append(
                compose_state_signal_post(
                    trigger, status, government_seats, total_seats, config.majority_threshold
                )
            )
        else:
            posts.append(
                compose_majority_post(trigger, baseline_by_code, names, status, config, total_seats)
            )
    return tuple(posts)


def send_post(client: httpx.Client, token: str, channel_id: str, content: PostContent) -> None:
    """The one HTTPS call: `sendPhoto` against the Telegram Bot API.

    `client` is always supplied by the caller (never defaulted, unlike
    `scraper.new_client`) — every test needs a fake transport, and there is
    no real caller here that would want a bare `httpx.Client()` default the
    way the Scraper's outbound requests do.
    """
    response = client.post(
        f"{TELEGRAM_API}/bot{token}/sendPhoto",
        data={"chat_id": channel_id, "caption": content.caption, "parse_mode": "HTML"},
        files={"photo": ("card.png", content.photo, "image/png")},
    )
    response.raise_for_status()


_ATOM_NS = "http://www.w3.org/2005/Atom"


class LoggedPost(Protocol):
    """The shape `build_feed` needs from a logged post — matches
    `storage.LoggedTriggerPost` structurally rather than importing it, so
    this module's only dependency on Storage stays in `main`, matching
    every other renderer in this package (`public_page.render_html`,
    `public_export.to_json`) taking plain data rather than reaching into
    Storage itself. Declared as read-only properties, not plain attributes
    — mypy treats a plain Protocol attribute as read-write, which a frozen
    dataclass's read-only fields (`LoggedTriggerPost`'s) then fail to
    structurally satisfy."""

    @property
    def id(self) -> int: ...
    @property
    def computed_at(self) -> date: ...
    @property
    def title(self) -> str: ...
    @property
    def caption(self) -> str: ...


def build_feed(posts: Sequence[LoggedPost]) -> str:
    """The RSS byproduct #40 asks for, as an Atom feed — one entry per
    logged Return Trigger post, newest first.
    """
    updated = max((p.computed_at for p in posts), default=today_in_malaysia())
    entries = "\n".join(
        f"""  <entry>
    <id>{SITE_URL}feed#{p.id}</id>
    <title>{_xml_escape(p.title)}</title>
    <updated>{p.computed_at.isoformat()}T00:00:00Z</updated>
    <link href="{SITE_URL}"/>
    <content type="html">{_xml_escape(p.caption)}</content>
  </entry>"""
        for p in reversed(posts)
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="{_ATOM_NS}">
  <title>Live Political Analysis · Return Triggers</title>
  <subtitle>GE16 Return Trigger posts — an event fired, not a daily update.</subtitle>
  <id>{SITE_URL}feed</id>
  <link href="{SITE_URL}"/>
  <updated>{updated.isoformat()}T00:00:00Z</updated>
{entries}
</feed>
"""


def main() -> None:
    """Detect today's Return Triggers, compose and send their posts, log
    them, and rewrite the RSS/Atom feed from the full log (#40's own
    "byproduct of the same render step"). Reads Storage independently of
    `pipeline.py` and `public_page.py`, the same "each step reads what it
    needs" seam `public_export.py` and `seat_call_card.py --all` already
    follow — this runs as its own step in the daily Action, after the
    pipeline has stored the day's Projection.
    """
    import argparse
    import os
    from pathlib import Path

    from lpa.config import (
        coalition_names,
        load_coalition_config,
        load_election_status,
        load_state_election_signals,
        swing_model_config,
    )
    from lpa.return_trigger import detect_triggers
    from lpa.storage import (
        connect,
        load_previous_trigger_watch,
        load_projections,
        load_seat_baselines,
        load_trigger_posts,
        save_trigger_posts,
        save_trigger_watch,
        trigger_watch_exists,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("public"),
        help="directory to write feed.xml into (default: public)",
    )
    args = parser.parse_args()

    engine = connect()
    projections = load_projections(engine)
    if not projections:
        raise SystemExit("No Projection stored. Run `python -m lpa.pipeline` first.")
    latest = projections[-1]
    today = latest.computed_at

    if trigger_watch_exists(engine, today):
        print(
            f"Trigger watch already recorded for {today} — skipping. A same-day "
            "rerun does not re-evaluate or re-post (a Telegram post can't be unsent)."
        )
    else:
        status = load_election_status()
        signal_states = frozenset(s.state for s in load_state_election_signals() if s.vote_share)
        config_data = load_coalition_config()
        config = swing_model_config(config_data)
        baseline = load_seat_baselines(engine)
        names = coalition_names(config_data)
        total_seats = config_data["total_seats"]

        previous = load_previous_trigger_watch(engine, today)
        older = projections[-2] if len(projections) >= 2 else None
        triggers = detect_triggers(
            previous=previous,
            current_status=status,
            current_signal_states=signal_states,
            older_projection=older,
            newer_projection=latest,
            config=config,
        )

        posts = compose_posts(
            triggers,
            status=status,
            baseline=baseline,
            names=names,
            config=config,
            total_seats=total_seats,
            latest_projection=latest,
        )

        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
        if posts and token and channel_id:
            with httpx.Client(timeout=30.0) as client:
                for post in posts:
                    send_post(client, token, channel_id, post)
            print(f"Posted {len(posts)} Return Trigger post(s) to Telegram.")
        elif posts:
            print(
                f"{len(posts)} Return Trigger post(s) ready but TELEGRAM_BOT_TOKEN/"
                "TELEGRAM_CHANNEL_ID are not both set — not sent:"
            )
            for post in posts:
                print(f"  - {post.title}")
        else:
            print("No Return Trigger fired today.")

        save_trigger_posts(engine, today, [(post.title, post.caption) for post in posts])
        save_trigger_watch(engine, today, status, signal_states)

    feed = build_feed(load_trigger_posts(engine))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "feed.xml").write_text(feed, encoding="utf-8")
    print(f"Wrote feed.xml to {args.output_dir}")


if __name__ == "__main__":
    main()
