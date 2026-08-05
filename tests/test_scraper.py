"""The Scraper's pure seam: a feed's XML -> Article records.

Tested against a fixture copy of Free Malaysia Today's real feed, so CI never
touches the network (issue #1's Testing Decisions).
"""

from datetime import datetime, timezone
from pathlib import Path

from pytest import fixture, raises

from lpa.scraper import Outlet, RobotsPolicy, Scraper, parse_feed, strip_html

FIXTURE = Path(__file__).parent / "fixtures" / "fmt_feed.xml"


@fixture
def articles():
    return parse_feed(FIXTURE.read_bytes(), "Free Malaysia Today")


def test_every_item_in_the_feed_becomes_an_article(articles):
    assert len(articles) == 3


def test_an_article_carries_source_url_published_at_title_and_text(articles):
    article = articles[0]

    assert article.source == "Free Malaysia Today"
    assert article.url.startswith("https://www.freemalaysiatoday.com/")
    assert article.published_at.tzinfo is not None
    assert article.title
    assert article.text


def test_published_at_is_read_from_the_feed_not_the_clock(articles):
    # The fixture is a frozen copy, so its dates must not drift with today's.
    assert all(a.published_at < datetime.now(timezone.utc) for a in articles)
    assert all(a.published_at.year == 2026 for a in articles)


def test_article_text_is_plain_text_with_no_markup_left(articles):
    for article in articles:
        assert "<" not in article.text
        assert "&nbsp;" not in article.text


def test_strip_html_collapses_markup_and_entities_to_readable_text():
    html = "<p>PH  said  it   was   <b>fine</b>&nbsp;&amp; fair.</p>"

    assert strip_html(html) == 'PH said it was fine & fair.'


def test_an_item_without_a_date_is_skipped_rather_than_guessed_at():
    # A wrong published_at would misdate a whole day of Sentiment.
    feed = """<rss><channel>
      <item><title>Dated</title><link>https://x/1</link>
        <pubDate>Wed, 05 Aug 2026 16:13:00 +0000</pubDate>
        <description>body</description></item>
      <item><title>Undated</title><link>https://x/2</link>
        <description>body</description></item>
    </channel></rss>"""

    assert [a.title for a in parse_feed(feed, "X")] == ["Dated"]


class StubRobots:
    def __init__(self, allowed: bool, delay: float | None = None):
        self.allowed, self.delay = allowed, delay

    def is_allowed(self, url):
        return self.allowed

    def crawl_delay(self, url):
        return self.delay


def test_a_feed_robots_txt_disallows_is_not_fetched():
    def explode(*args, **kwargs):
        raise AssertionError("fetched a URL robots.txt disallows")

    scraper = Scraper(client=type("C", (), {"get": explode})(), robots=StubRobots(False))

    assert scraper.fetch(Outlet("Blocked", "https://x/feed/")) == []


def test_requests_are_spaced_out_by_the_configured_minimum():
    slept, clock = [], iter([0.0, 0.5, 0.5])

    class Client:
        def get(self, url):
            return type("R", (), {"content": b"<rss><channel/></rss>", "raise_for_status": lambda s: None})()

    scraper = Scraper(
        client=Client(), robots=StubRobots(True), min_interval=2.0,
        sleep=slept.append, now=lambda: next(clock),
    )
    outlet = Outlet("X", "https://x/feed/")

    scraper.fetch(outlet)
    scraper.fetch(outlet)

    assert slept == [1.5]  # 2.0s floor, 0.5s already elapsed


def test_an_outlets_own_crawl_delay_wins_when_it_is_the_stricter_one():
    slept, clock = [], iter([0.0, 0.0, 0.0])

    class Client:
        def get(self, url):
            return type("R", (), {"content": b"<rss><channel/></rss>", "raise_for_status": lambda s: None})()

    scraper = Scraper(
        client=Client(), robots=StubRobots(True, delay=10.0), min_interval=2.0,
        sleep=slept.append, now=lambda: next(clock),
    )
    outlet = Outlet("X", "https://x/feed/")

    scraper.fetch(outlet)
    scraper.fetch(outlet)

    assert slept == [10.0]


class StubResponse:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text


class RecordingClient:
    def __init__(self, response):
        self.response, self.requested = response, []

    def get(self, url):
        self.requested.append(url)
        return self.response


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


def test_a_missing_robots_txt_means_there_are_no_rules_to_break():
    policy = RobotsPolicy(client=RecordingClient(StubResponse(404)))

    assert policy.is_allowed("https://x/feed/") is True


def test_a_disallowed_path_in_robots_txt_is_refused():
    client = RecordingClient(
        StubResponse(200, "User-agent: *\nDisallow: /private/\n")
    )
    policy = RobotsPolicy(user_agent="test-agent", client=client)

    assert policy.is_allowed("https://x/private/feed/") is False
    assert policy.is_allowed("https://x/feed/") is True
