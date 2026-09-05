"""Composing and sending the Telegram post (#40): pure composition tested
away from the network, the one HTTPS call tested against a fake transport.
"""

from datetime import date
from io import BytesIO

import httpx
from fixtures import PH, PN, government_config, two_coalition_seats
from PIL import Image
from pytest import raises

from lpa import telegram_post
from lpa.domain import ElectionStatus, Projection, SeatCall
from lpa.return_trigger import (
    ElectionStatusTrigger,
    ElectionStatusTriggerKind,
    MajorityTrigger,
    StateSignalTrigger,
)
from lpa.storage import LoggedTriggerPost, connect, load_trigger_posts, trigger_watch_exists
from lpa.telegram_card import AGGREGATE_CARD_H, CARD_SIZE
from lpa.telegram_post import (
    PostContent,
    build_feed,
    compose_election_status_post,
    compose_majority_post,
    compose_posts,
    compose_state_signal_post,
    seat_page_url,
    send_post,
)

DEADLINE = date(2028, 2, 17)
NAMES = {PH: "Pakatan Harapan", PN: "Perikatan Nasional"}


def status(**overrides) -> ElectionStatus:
    defaults = {"constitutional_deadline": DEADLINE, "source": "x"}
    defaults.update(overrides)
    return ElectionStatus(**defaults)


# ── compose_election_status_post ────────────────────────────────────────


def test_the_called_post_matches_the_approved_voice():
    called = status(dissolved_on=date(2026, 8, 14))
    trigger = ElectionStatusTrigger(kind=ElectionStatusTriggerKind.CALLED, status=called)

    post = compose_election_status_post(
        trigger, government_seats=118, total_seats=222, majority_threshold=112
    )

    assert post.title == "GE16 has been called."
    assert "GE16 has been called" in post.caption
    assert "has not set a polling date yet" in post.caption
    img = Image.open(BytesIO(post.photo))
    assert img.size == (CARD_SIZE, AGGREGATE_CARD_H)


def test_the_polling_date_set_post_states_the_date():
    dated = status(dissolved_on=date(2026, 8, 14), polling_date=date(2026, 9, 20))
    trigger = ElectionStatusTrigger(kind=ElectionStatusTriggerKind.POLLING_DATE_SET, status=dated)

    post = compose_election_status_post(
        trigger, government_seats=118, total_seats=222, majority_threshold=112
    )

    assert post.title == "Polling day is 20 September 2026."
    assert "20 September 2026" in post.caption


# ── compose_state_signal_post ───────────────────────────────────────────


def test_the_state_signal_post_names_the_state():
    trigger = StateSignalTrigger(states=("Johor",))

    post = compose_state_signal_post(
        trigger, status(), government_seats=118, total_seats=222, majority_threshold=112
    )

    assert "Johor" in post.title
    assert "State Election Signal" in post.caption
    img = Image.open(BytesIO(post.photo))
    assert img.size == (CARD_SIZE, AGGREGATE_CARD_H)


def test_the_state_signal_post_names_every_state_that_arrived():
    trigger = StateSignalTrigger(states=("Johor", "Selangor"))

    post = compose_state_signal_post(
        trigger, status(), government_seats=118, total_seats=222, majority_threshold=112
    )

    assert "Johor" in post.caption
    assert "Selangor" in post.caption


# ── compose_majority_post ───────────────────────────────────────────────


def _flip(code: str, older: str, newer: str, margin: float = 0.05) -> tuple[SeatCall, SeatCall]:
    return (
        SeatCall(code=code, coalition=older, margin=0.02),
        SeatCall(code=code, coalition=newer, margin=margin),
    )


def test_a_single_seat_crossing_the_line_is_seat_anchored():
    baseline_by_code = {b.code: b for b in two_coalition_seats()}
    changed = (_flip("P001", PN, PH),)
    trigger = MajorityTrigger(
        older=Projection(
            coalition_seat_totals={PH: 3, PN: 3},
            government_majority=False,
            computed_at=date(2026, 8, 5),
        ),
        newer=Projection(
            coalition_seat_totals={PH: 4, PN: 2},
            government_majority=True,
            computed_at=date(2026, 8, 6),
        ),
        changed=changed,
        government_relevant_changed=changed,
        government_delta=1,
        majority_flipped=True,
    )

    post = compose_majority_post(
        trigger, baseline_by_code, NAMES, status(), government_config(), total_seats=6
    )

    assert "A Seat Call changed" in post.caption
    assert "P001" in post.title
    assert seat_page_url("P001") in post.caption
    img = Image.open(BytesIO(post.photo))
    assert img.size == (CARD_SIZE, CARD_SIZE)  # the square Seat card, not the aggregate


def test_seat_page_url_builds_mp_path():
    assert seat_page_url("P001") == "https://politikku.my/mp/P001/"


def test_more_than_one_seat_crossing_falls_through_to_aggregate():
    baseline_by_code = {b.code: b for b in two_coalition_seats()}
    changed = (_flip("P001", PN, PH), _flip("P002", PN, PH))
    trigger = MajorityTrigger(
        older=Projection(
            coalition_seat_totals={PH: 2, PN: 4},
            government_majority=False,
            computed_at=date(2026, 8, 5),
        ),
        newer=Projection(
            coalition_seat_totals={PH: 4, PN: 2},
            government_majority=True,
            computed_at=date(2026, 8, 6),
        ),
        changed=changed,
        government_relevant_changed=changed,
        government_delta=2,
        majority_flipped=True,
    )

    post = compose_majority_post(
        trigger, baseline_by_code, NAMES, status(), government_config(), total_seats=6
    )

    assert post.title == "The Majority flipped."
    img = Image.open(BytesIO(post.photo))
    assert img.size == (CARD_SIZE, AGGREGATE_CARD_H)


def test_no_seat_crossing_the_line_still_falls_through_to_aggregate():
    # A chamber-wide Sentiment swing can move the totals without any single
    # Seat crossing the Government/Non-government boundary.
    baseline_by_code = {b.code: b for b in two_coalition_seats()}
    trigger = MajorityTrigger(
        older=Projection(
            coalition_seat_totals={PH: 3, PN: 3},
            government_majority=False,
            computed_at=date(2026, 8, 5),
        ),
        newer=Projection(
            coalition_seat_totals={PH: 3, PN: 3},
            government_majority=False,
            computed_at=date(2026, 8, 6),
        ),
        changed=(),
        government_relevant_changed=(),
        government_delta=0,
        majority_flipped=False,
    )

    post = compose_majority_post(
        trigger, baseline_by_code, NAMES, status(), government_config(), total_seats=6
    )

    img = Image.open(BytesIO(post.photo))
    assert img.size == (CARD_SIZE, AGGREGATE_CARD_H)


def test_a_non_flip_aggregate_caption_reports_the_seat_delta():
    baseline_by_code = {b.code: b for b in two_coalition_seats()}
    changed = tuple(_flip(f"P00{i}", PN, PH) for i in range(1, 6))
    trigger = MajorityTrigger(
        older=Projection(
            coalition_seat_totals={PH: 2, PN: 4},
            government_majority=False,
            computed_at=date(2026, 8, 5),
        ),
        newer=Projection(
            coalition_seat_totals={PH: 4, PN: 2},
            government_majority=True,
            computed_at=date(2026, 8, 6),
        ),
        changed=changed,
        government_relevant_changed=changed,
        government_delta=5,
        majority_flipped=False,
    )

    post = compose_majority_post(
        trigger, baseline_by_code, NAMES, status(), government_config(), total_seats=6
    )

    assert post.title == "The Government Coalition gained 5 seats."


# ── compose_posts dispatch ──────────────────────────────────────────────


def test_compose_posts_produces_one_post_per_trigger_in_order():
    baseline = two_coalition_seats()
    called = status(dissolved_on=date(2026, 8, 14))
    triggers = (
        ElectionStatusTrigger(kind=ElectionStatusTriggerKind.CALLED, status=called),
        StateSignalTrigger(states=("Johor",)),
    )
    latest = Projection(
        coalition_seat_totals={PH: 4, PN: 2}, government_majority=True, computed_at=date(2026, 8, 6)
    )

    posts = compose_posts(
        triggers,
        status=called,
        baseline=baseline,
        names=NAMES,
        config=government_config(),
        total_seats=6,
        latest_projection=latest,
    )

    assert len(posts) == 2
    assert posts[0].title == "GE16 has been called."
    assert "Johor" in posts[1].title


# ── send_post ────────────────────────────────────────────────────────────


def test_send_post_posts_the_caption_and_photo_bytes_to_sendphoto():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    content = PostContent(title="t", caption="<b>hello</b>", photo=b"\x89PNGfakebytes")

    send_post(client, "TOKEN", "@channel", content)

    request = captured["request"]
    assert str(request.url) == "https://api.telegram.org/botTOKEN/sendPhoto"
    body = request.content
    assert b"<b>hello</b>" in body
    assert b"@channel" in body
    assert b"HTML" in body
    assert b"\x89PNGfakebytes" in body


def test_send_post_raises_on_an_error_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "bad request"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    content = PostContent(title="t", caption="c", photo=b"x")

    with raises(httpx.HTTPStatusError):
        send_post(client, "TOKEN", "@channel", content)


# ── _send_and_log ────────────────────────────────────────────────────────


def test_a_send_failure_still_logs_and_marks_the_day_before_raising(monkeypatch):
    # #40: a Telegram post can't be unsent, so even a partial failure (one
    # post of several) must not leave the day unmarked — a rerun would
    # otherwise re-detect and re-send the post that already succeeded.
    engine = connect("sqlite+pysqlite:///:memory:")
    posts = [
        PostContent(title="First", caption="one", photo=b"x"),
        PostContent(title="Second", caption="two", photo=b"y"),
    ]
    attempted = []

    def fake_send_post(client, token, channel_id, content):
        attempted.append(content.title)
        if content.title == "Second":
            raise httpx.HTTPError("boom")

    monkeypatch.setattr(telegram_post, "send_post", fake_send_post)

    with raises(SystemExit):
        telegram_post._send_and_log(
            engine, date(2026, 8, 6), status(), frozenset(), posts, "TOKEN", "@channel"
        )

    assert attempted == ["First", "Second"]
    assert [p.title for p in load_trigger_posts(engine)] == ["First", "Second"]
    assert trigger_watch_exists(engine, date(2026, 8, 6)) is True


def test_no_credentials_still_logs_and_marks_the_day_without_sending(monkeypatch):
    engine = connect("sqlite+pysqlite:///:memory:")
    posts = [PostContent(title="First", caption="one", photo=b"x")]
    sent = []
    monkeypatch.setattr(telegram_post, "send_post", lambda *a: sent.append(a))

    telegram_post._send_and_log(engine, date(2026, 8, 6), status(), frozenset(), posts, None, None)

    assert sent == []
    assert [p.title for p in load_trigger_posts(engine)] == ["First"]
    assert trigger_watch_exists(engine, date(2026, 8, 6)) is True


# ── build_feed ───────────────────────────────────────────────────────────


def test_build_feed_is_empty_but_valid_with_no_posts():
    xml = build_feed([])

    assert "<feed" in xml
    assert "<entry>" not in xml


def test_build_feed_lists_posts_newest_first():
    posts = [
        LoggedTriggerPost(id=1, computed_at=date(2026, 8, 6), title="First", caption="one"),
        LoggedTriggerPost(id=2, computed_at=date(2026, 8, 10), title="Second", caption="two"),
    ]

    xml = build_feed(posts)

    assert xml.index("Second") < xml.index("First")


def test_build_feed_escapes_markup_in_the_title_and_caption():
    posts = [LoggedTriggerPost(id=1, computed_at=date(2026, 8, 6), title="A & B < C", caption="x")]

    xml = build_feed(posts)

    assert "A &amp; B &lt; C" in xml
    assert "A & B < C" not in xml
