"""The Scraper's pure seam: a feed's XML -> Article records, plus the politeness
rules around fetching.

Parsing is tested against a fixture copy of Free Malaysia Today's real feed, so
CI never touches the network (issue #1's Testing Decisions).
"""

from datetime import datetime, timezone
from pathlib import Path

import httpx
from pytest import fixture, raises

from lpa.domain import Outlet
from lpa.scraper import (
    Disallowed,
    RateLimiter,
    RobotsPolicy,
    Scraper,
    UnreadableFeed,
    parse_feed,
    strip_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "fmt_feed.xml"


@fixture
def articles():
    return parse_feed(FIXTURE.read_bytes(), "Free Malaysia Today")


# --- parsing ---------------------------------------------------------------


def test_every_item_in_the_feed_becomes_an_article(articles):
    assert len(articles) == 3


def test_an_article_carries_source_url_published_at_title_and_text(articles):
    article = articles[0]

    assert article.source == "Free Malaysia Today"
    assert article.url.startswith("https://www.freemalaysiatoday.com/")
    assert article.published_at.tzinfo is not None
    assert article.title
    assert article.text


def test_published_at_is_the_feeds_own_timestamp():
    # Pinned to the exact value in the feed, so a published_at taken from the
    # clock instead could not pass.
    feed = """<rss><channel><item>
        <title>T</title><link>https://x/1</link>
        <pubDate>Wed, 05 Aug 2026 16:13:00 +0000</pubDate>
        <description>body</description>
    </item></channel></rss>"""

    assert parse_feed(feed, "X")[0].published_at == datetime(
        2026, 8, 5, 16, 13, tzinfo=timezone.utc
    )


def test_article_text_is_plain_text_with_no_markup_left(articles):
    for article in articles:
        assert "<" not in article.text
        assert "&nbsp;" not in article.text


def test_entities_are_decoded_and_markup_removed():
    markup = "<p>PH  said  it   was   <b>fine</b>&nbsp;&amp; fair&#8230;</p>"

    assert strip_html(markup) == "PH said it was fine & fair…"


def test_escaped_markup_does_not_survive_as_live_markup():
    # Decoding entities after stripping tags would turn this back into "<b>".
    assert "<" not in strip_html("&lt;b&gt;bold&lt;/b&gt;")


def test_an_item_without_a_date_is_kept_with_no_date_rather_than_guessed_at():
    # Bernama's feed dates nothing, and it is the national news agency. An
    # invented published_at would misdate a whole day of Sentiment and be
    # indistinguishable from a real one; None says plainly that it is unknown.
    feed = """<rss><channel>
      <item><title>Dated</title><link>https://x/1</link>
        <pubDate>Wed, 05 Aug 2026 16:13:00 +0000</pubDate>
        <description>body</description></item>
      <item><title>Undated</title><link>https://x/2</link>
        <description>body</description></item>
    </channel></rss>"""

    articles = parse_feed(feed, "X")

    assert [a.title for a in articles] == ["Dated", "Undated"]
    assert articles[1].published_at is None


def test_an_item_without_a_link_or_a_title_is_still_skipped():
    # There is no Article without them, dated or not.
    feed = """<rss><channel>
      <item><title>No link</title><description>body</description></item>
      <item><link>https://x/2</link><description>body</description></item>
      <item><title>Whole</title><link>https://x/3</link>
        <description>body</description></item>
    </channel></rss>"""

    assert [a.title for a in parse_feed(feed, "X")] == ["Whole"]


def test_an_atom_feed_is_read_too():
    feed = """<feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Atom piece</title>
        <link href="https://x/1"/>
        <published>2026-08-05T16:13:00+00:00</published>
        <content>&lt;p&gt;PH was praised.&lt;/p&gt;</content>
      </entry>
    </feed>"""

    article = parse_feed(feed, "X")[0]

    assert article.title == "Atom piece"
    assert article.url == "https://x/1"
    assert article.text == "PH was praised."


def test_a_document_that_is_not_a_feed_raises_rather_than_reading_as_no_news():
    # An outlet that quietly changed format would otherwise be indistinguishable
    # from an outlet with nothing to report.
    with raises(UnreadableFeed):
        parse_feed("<html><body>Not a feed</body></html>", "X")


# --- politeness ------------------------------------------------------------


class FakeClock:
    """A clock that only moves when something sleeps."""

    def __init__(self):
        self.now, self.slept = 0.0, []

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class StubResponse:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text


class RecordingClient:
    def __init__(self, response=None):
        self.response = response or StubResponse(200, "")
        self.requested = []

    def get(self, url):
        self.requested.append(url)
        return self.response


class StubRobots:
    def __init__(self, allowed, delay=None):
        self.allowed, self.delay = allowed, delay

    def is_allowed(self, url):
        return self.allowed

    def crawl_delay(self, url):
        return self.delay


def feed_response(content=b"<rss><channel/></rss>"):
    return type(
        "R", (), {"content": content, "raise_for_status": lambda self: None}
    )()


class FeedClient:
    def get(self, url):
        return feed_response()


def limiter_on(clock, min_interval=2.0):
    return RateLimiter(
        min_interval=min_interval, sleep=clock.sleep, now=lambda: clock.now
    )


def test_robots_txt_is_fetched_with_our_own_declared_user_agent():
    # An outlet's CDN may 403 urllib's stock agent, which RobotFileParser reads
    # as "everything is disallowed" — silently stopping the Scraper on a feed
    # that is in fact allowed. Observed against Free Malaysia Today.
    client = RecordingClient(StubResponse(200, "User-agent: *\nAllow: /\n"))
    policy = RobotsPolicy(user_agent="test-agent", client=client)

    assert policy.is_allowed("https://x/feed/") is True
    assert client.requested == ["https://x/robots.txt"]


def test_a_forbidden_robots_txt_is_treated_as_a_refusal():
    policy = RobotsPolicy(client=RecordingClient(StubResponse(403)))

    assert policy.is_allowed("https://x/feed/") is False


def test_an_outlet_erroring_on_robots_txt_is_left_alone():
    # A 503 means the outlet is unwell, not that it has no rules.
    policy = RobotsPolicy(client=RecordingClient(StubResponse(503)))

    assert policy.is_allowed("https://x/feed/") is False


def test_a_missing_robots_txt_means_there_are_no_rules_to_break():
    policy = RobotsPolicy(client=RecordingClient(StubResponse(404)))

    assert policy.is_allowed("https://x/feed/") is True


def test_a_disallowed_path_in_robots_txt_is_refused():
    client = RecordingClient(StubResponse(200, "User-agent: *\nDisallow: /private/\n"))
    policy = RobotsPolicy(user_agent="test-agent", client=client)

    assert policy.is_allowed("https://x/private/feed/") is False
    assert policy.is_allowed("https://x/feed/") is True


def test_the_robots_txt_request_is_itself_rate_limited():
    # Checking robots.txt and then fetching the feed is two requests to the
    # same host; skipping the spacing on the first defeats the point.
    clock = FakeClock()
    limiter = limiter_on(clock)
    robots = RobotsPolicy(
        user_agent="test-agent",
        client=RecordingClient(StubResponse(200, "User-agent: *\nAllow: /\n")),
        limiter=limiter,
    )

    Scraper(client=FeedClient(), robots=robots, limiter=limiter).fetch(
        Outlet("X", "https://x/feed/")
    )

    assert clock.slept == [2.0]  # robots.txt, then a full interval before the feed


def test_the_first_request_to_a_host_does_not_wait():
    clock = FakeClock()

    limiter_on(clock).wait_turn("https://x/feed/")

    assert clock.slept == []


def test_a_second_request_to_the_same_host_waits_out_the_interval():
    clock = FakeClock()
    limiter = limiter_on(clock)

    limiter.wait_turn("https://x/feed/")
    limiter.wait_turn("https://x/feed/")
    limiter.wait_turn("https://x/feed/")

    assert clock.slept == [2.0, 2.0]


def test_one_outlets_pace_is_not_imposed_on_another_host():
    clock = FakeClock()
    limiter = limiter_on(clock)

    limiter.wait_turn("https://x/feed/")
    limiter.wait_turn("https://y/feed/")

    assert clock.slept == []


def test_an_outlets_own_crawl_delay_wins_when_it_is_the_stricter_one():
    clock = FakeClock()
    limiter = limiter_on(clock)

    limiter.wait_turn("https://x/feed/", crawl_delay=10.0)
    limiter.wait_turn("https://x/feed/", crawl_delay=10.0)

    assert clock.slept == [10.0]


def test_a_feed_robots_txt_disallows_is_not_fetched():
    def explode(*args, **kwargs):
        raise AssertionError("fetched a URL robots.txt disallows")

    scraper = Scraper(client=type("C", (), {"get": explode})(), robots=StubRobots(False))

    with raises(Disallowed):
        scraper.fetch(Outlet("Blocked", "https://x/feed/"))


def test_a_refused_outlet_is_named_in_the_run_rather_than_dropped_quietly(capsys):
    # Issue #16: returning no Articles made a blocked outlet look exactly
    # like one that published no news. Berita Harian's robots.txt began
    # answering 403 two days after it was added and it left the run without
    # a word; nothing in the output said an outlet was missing.
    scraper = Scraper(client=FeedClient(), robots=StubRobots(False))

    articles = scraper.fetch_all([Outlet("Blocked", "https://x/feed/")])

    assert articles == []
    assert "Blocked" in capsys.readouterr().out


def test_a_refusal_reads_differently_from_a_breakage(capsys):
    # One is answered by asking the outlet or dropping it from
    # data/outlets.json, the other by waiting or fixing a parser. Folding
    # both into one message would lose that.
    class BrokenClient:
        def get(self, url):
            raise httpx.ConnectError("down")

    Scraper(client=FeedClient(), robots=StubRobots(False)).fetch_all(
        [Outlet("Refused", "https://x/feed/")]
    )
    Scraper(client=BrokenClient(), robots=StubRobots(True)).fetch_all(
        [Outlet("Broken", "https://y/feed/")]
    )

    printed = capsys.readouterr().out
    assert "not permitted" in printed
    assert "ConnectError" in printed


def test_a_refused_outlet_does_not_cost_the_run_the_others():
    # The refusal path has to carry on exactly as the failure path does —
    # this is what actually went wrong: half the Bahasa Malaysia coverage
    # vanished and the remaining outlets carried the day on their own.
    class Client:
        def get(self, url):
            return feed_response(FIXTURE.read_bytes())

    class RefuseOne:
        def is_allowed(self, url):
            return "refused" not in url

        def crawl_delay(self, url):
            return None

    scraper = Scraper(client=Client(), robots=RefuseOne())

    articles = scraper.fetch_all(
        [Outlet("Refused", "https://refused/feed/"), Outlet("Fine", "https://fine/feed/")]
    )

    assert [a.source for a in articles] == ["Fine"] * 3


def test_one_failing_outlet_does_not_cost_the_run_the_others():
    # The daily job is unattended: an outage at one outlet must not take the
    # whole day's coverage with it.
    class HalfBrokenClient:
        def get(self, url):
            if "broken" in url:
                raise httpx.ConnectError("down")
            return feed_response(FIXTURE.read_bytes())

    scraper = Scraper(client=HalfBrokenClient(), robots=StubRobots(True))

    articles = scraper.fetch_all(
        [Outlet("Broken", "https://broken/feed/"), Outlet("Fine", "https://fine/feed/")]
    )

    assert [a.source for a in articles] == ["Fine"] * 3
