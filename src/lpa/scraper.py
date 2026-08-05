"""Scraper: recent coverage from Malaysian outlets, as Article records.

Reads each outlet's RSS feed rather than crawling article pages. The feed
carries title, canonical URL, publication time and the full body in one
request instead of one per article — kinder to the outlet, less to go wrong,
and no HTML layout to track.

Parsing is pure and tested against a fixture feed. The fetching half checks
robots.txt before every request and spaces requests out (issue #1, story 21).
"""

from __future__ import annotations

import re
import time
import urllib.robotparser
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import urljoin, urlparse

import httpx

from lpa.domain import Article

USER_AGENT = (
    "live-political-analysis/0.1 "
    "(+https://github.com/IlhamKassim/live-political-analysis)"
)
CONTENT_ENCODED = "{http://purl.org/rss/1.0/modules/content/}encoded"

# The second alternative catches a tag left unterminated by truncated or
# malformed markup, which would otherwise survive into the article text.
_TAG = re.compile(r"<[^>]*>|<[^>]*$")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Outlet:
    """An outlet and the feed to read it from."""

    name: str
    feed_url: str


def parse_feed(feed_xml: str | bytes, source: str) -> list[Article]:
    """Turn an RSS feed into Article records. Pure — no network.

    Items missing a link, a title or a usable date are skipped rather than
    guessed at: a wrong `published_at` would misdate a whole day's Sentiment.
    """
    channel = ElementTree.fromstring(feed_xml)
    articles = []
    for item in channel.iter("item"):
        url = _text(item, "link")
        title = _text(item, "title")
        published_at = _published_at(item)
        if not (url and title and published_at):
            continue
        articles.append(
            Article(
                source=source,
                url=url,
                published_at=published_at,
                title=title,
                text=strip_html(_text(item, CONTENT_ENCODED) or _text(item, "description")),
            )
        )
    return articles


def strip_html(html: str) -> str:
    """Reduce an article body to the plain text the Sentiment Scorer reads."""
    text = _TAG.sub(" ", html or "")
    for entity, character in (
        ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
        ("&gt;", ">"), ("&quot;", '"'), ("&#8217;", "'"), ("&#8216;", "'"),
    ):
        text = text.replace(entity, character)
    return _WHITESPACE.sub(" ", text).strip()


class RobotsPolicy:
    """What an outlet's robots.txt permits, fetched once per host.

    robots.txt is fetched with the same declared User-Agent as everything else
    rather than through `RobotFileParser.read()`, whose stock urllib agent some
    outlets' CDNs refuse. A 403 there would otherwise read as "everything is
    disallowed" and silently stop the Scraper on a feed that is in fact allowed.
    """

    def __init__(
        self, user_agent: str = USER_AGENT, client: httpx.Client | None = None
    ) -> None:
        self.user_agent = user_agent
        self.client = client or httpx.Client(
            headers={"User-Agent": user_agent}, timeout=30.0, follow_redirects=True
        )
        self._by_host: dict[str, urllib.robotparser.RobotFileParser] = {}

    def rules_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        host = urlparse(url).netloc
        if host not in self._by_host:
            self._by_host[host] = self._read(urljoin(url, "/robots.txt"))
        return self._by_host[host]

    def _read(self, robots_url: str) -> urllib.robotparser.RobotFileParser:
        rules = urllib.robotparser.RobotFileParser()
        try:
            response = self.client.get(robots_url)
        except httpx.HTTPError:
            # No answer is not permission: fail closed and try again next run.
            rules.disallow_all = True
            return rules
        if response.status_code in (401, 403):
            rules.disallow_all = True
        elif response.status_code >= 400:
            rules.allow_all = True  # No robots.txt published means no rules.
        else:
            rules.parse(response.text.splitlines())
        return rules

    def is_allowed(self, url: str) -> bool:
        return self.rules_for(url).can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        delay = self.rules_for(url).crawl_delay(self.user_agent)
        return float(delay) if delay is not None else None


class Scraper:
    """Fetches outlet feeds, obeying robots.txt and a minimum request spacing."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        robots: RobotsPolicy | None = None,
        min_interval: float = 2.0,
        sleep=time.sleep,
        now=time.monotonic,
    ) -> None:
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True
        )
        self.robots = robots or RobotsPolicy()
        self.min_interval = min_interval
        self._sleep = sleep
        self._now = now
        self._last_request: float | None = None

    def fetch(self, outlet: Outlet) -> list[Article]:
        """Fetch one outlet's recent Articles, or none if robots.txt forbids it."""
        if not self.robots.is_allowed(outlet.feed_url):
            return []
        self._wait_turn(outlet.feed_url)
        response = self.client.get(outlet.feed_url)
        response.raise_for_status()
        return parse_feed(response.content, outlet.name)

    def fetch_all(self, outlets: Iterable[Outlet]) -> list[Article]:
        return [article for outlet in outlets for article in self.fetch(outlet)]

    def _wait_turn(self, url: str) -> None:
        """Space requests out by the greater of our floor and the outlet's own."""
        interval = max(self.min_interval, self.robots.crawl_delay(url) or 0.0)
        if self._last_request is not None:
            remaining = interval - (self._now() - self._last_request)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request = self._now()


def _text(item: ElementTree.Element, tag: str) -> str:
    element = item.find(tag)
    return (element.text or "").strip() if element is not None else ""


def _published_at(item: ElementTree.Element) -> datetime | None:
    raw = _text(item, "pubDate")
    if not raw:
        return None
    try:
        published = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    return published if published.tzinfo else published.replace(tzinfo=timezone.utc)


def main() -> None:
    """Fetch the configured outlets and print the Articles for inspection."""
    import json

    from lpa.config import load_outlets

    articles = Scraper().fetch_all(load_outlets())
    for article in articles:
        print(
            json.dumps(
                {
                    "source": article.source,
                    "url": article.url,
                    "published_at": article.published_at.isoformat(),
                    "title": article.title,
                    "text": article.text[:200],
                },
                ensure_ascii=False,
            )
        )
    print(f"\n{len(articles)} Articles from {len({a.source for a in articles})} outlets.")


if __name__ == "__main__":
    main()
